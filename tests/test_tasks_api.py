import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis, TaskInput
from app.services.retention import RetentionService


MKV_HEADER = b"\x1a\x45\xdf\xa3"
SLOTS = ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04")


def _mkv(payload: bytes) -> bytes:
    return MKV_HEADER + payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_sample_root(root: Path) -> None:
    group = root / "outputs" / "v3" / "group_04"
    _write_json(
        group / "report.json",
        {
            "clips": [],
            "shot_outcomes": [],
            "shot_stats": {"attempts": 0, "makes": 0, "misses": 0, "undetermined": 0},
        },
    )
    _write_json(group / "summary.json", {"student_ids": [], "clip_count": 0})
    viz = group / "viz"
    viz.mkdir()
    (viz / "phases.mp4").write_bytes(b"preset-phases")
    inputs = root / "test_data_v3"
    inputs.mkdir(parents=True)
    for name in ("0-2.mkv", "4-1.mkv", "4-2.mkv", "4-3.mkv", "4-4.mkv"):
        (inputs / name).write_bytes(_mkv(name.encode()))
    (inputs / "sync").mkdir()
    (inputs / "sync" / "group_04.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path):
    sample_root = tmp_path / "samples"
    _build_sample_root(sample_root)
    sync = tmp_path / "sync.json"
    sync.write_text('{"offset": 17}', encoding="utf-8")
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=sample_root,
        model_root=tmp_path / "models",
        sync_config=sync,
        admin_username="admin",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
        min_free_storage_gb=0,
    )
    with TestClient(create_app(settings=settings), raise_server_exceptions=False) as test_client:
        test_client.app.state.readiness.require_ready = lambda: None
        test_client.app.state.storage.video_probe = lambda _path, _title: None
        _login(test_client)
        yield test_client


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "correct-password"},
    )
    assert response.status_code == 200


def _register(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "new-password",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": "new-password"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create(client: TestClient, title: str = "训练任务", **kwargs):
    return client.post(
        "/api/v1/tasks",
        json={"title": title, "mode": "quick"},
        **kwargs,
    )


def _upload(client: TestClient, task_id: str, slot: str, payload: bytes, filename: str | None = None):
    return client.put(
        f"/api/v1/tasks/{task_id}/inputs/{slot}",
        files={"file": (filename or f"{slot}.mkv", payload, "video/x-matroska")},
    )


def test_create_draft_and_list_with_paging_filters_and_tenant_isolation(client: TestClient):
    first = _create(client, "Alpha session")
    second = _create(client, "Beta session")
    assert first.status_code == 201
    assert first.json()["status"] == "draft"
    assert first.json()["submitted_at"] is None
    assert first.json()["inputs"] == []

    page = client.get("/api/v1/tasks", params={"q": "session", "mode": "quick", "status": "draft", "page": 1, "page_size": 1})
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["page"] == 1
    assert page.json()["page_size"] == 1
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0]["id"] == second.json()["id"]

    other_headers = _register(client, "othercoach")
    assert client.get("/api/v1/tasks", headers=other_headers).json()["items"] == []
    assert client.get(f"/api/v1/tasks/{first.json()['id']}", headers=other_headers).status_code == 404


def test_per_user_draft_and_unfinished_quotas(client: TestClient):
    for index in range(3):
        assert _create(client, f"draft-{index}").status_code == 201
    draft_limit = _create(client, "too-many-drafts")
    assert draft_limit.status_code == 429
    assert "draft" in draft_limit.json()["detail"].lower()

    headers = _register(client, "unfinishedcoach")
    with Session(client.app.state.engine) as session:
        owner_id = client.get("/api/v1/users/me", headers=headers).json()["id"]
        for index in range(5):
            session.add(
                Analysis(
                    title=f"queued-{index}",
                    status="queued",
                    input_manifest_json="{}",
                    owner_id=owner_id,
                    created_via="tasks_api",
                )
            )
        session.commit()
    unfinished_limit = _create(client, "sixth unfinished", headers=headers)
    assert unfinished_limit.status_code == 429
    assert "unfinished" in unfinished_limit.json()["detail"].lower()


def test_daily_submission_quota_is_per_user_and_uses_utc_day(client: TestClient):
    now = datetime.now(timezone.utc)
    with Session(client.app.state.engine) as session:
        for index in range(20):
            session.add(
                Analysis(
                    title=f"done-{index}",
                    status="completed",
                    progress=100,
                    input_manifest_json="{}",
                    owner_id=1,
                    submitted_at=now,
                    completed_at=now,
                    created_via="tasks_preset",
                )
            )
        session.add(
            Analysis(
                title="yesterday",
                status="completed",
                input_manifest_json="{}",
                owner_id=1,
                submitted_at=now - timedelta(days=1),
                created_via="tasks_preset",
            )
        )
        session.commit()

    limited = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    assert limited.status_code == 429
    assert "daily" in limited.json()["detail"].lower()

    headers = _register(client, "freshcoach")
    allowed = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
        headers=headers,
    )
    assert allowed.status_code == 201


def test_slot_upload_validates_and_failed_replacement_preserves_prior_file(client: TestClient):
    task_id = _create(client).json()["id"]
    accepted = _upload(client, task_id, "cam_01", _mkv(b"original"), "original.mkv")
    assert accepted.status_code == 200
    assert accepted.json()["inputs"][0]["slot"] == "cam_01"
    assert accepted.json()["inputs"][0]["original_filename"] == "original.mkv"
    assert accepted.json()["inputs"][0]["validation_state"] == "valid"
    stored_path = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input" / "cam_01.mkv"
    assert stored_path.read_bytes() == _mkv(b"original")

    rejected = _upload(client, task_id, "cam_01", b"%PDF-1.7", "fake.mkv")
    assert rejected.status_code == 400
    detail = client.get(f"/api/v1/tasks/{task_id}").json()
    assert detail["status"] == "draft"
    assert detail["inputs"][0]["original_filename"] == "original.mkv"
    assert stored_path.read_bytes() == _mkv(b"original")
    assert list(stored_path.parent.glob("*.tmp")) == []

    assert _upload(client, task_id, "unknown", _mkv(b"x")).status_code == 422


def test_task_reports_uploading_while_server_validates_a_complete_slot(
    client: TestClient,
    monkeypatch,
):
    task_id = _create(client).json()["id"]
    validation_started = threading.Event()
    allow_validation = threading.Event()

    def gated_probe(_path: Path, _title: str) -> None:
        validation_started.set()
        assert allow_validation.wait(timeout=3)

    monkeypatch.setattr(client.app.state.storage, "video_probe", gated_probe)
    result = {}

    def upload() -> None:
        result["response"] = _upload(client, task_id, "cam_01", _mkv(b"video"))

    thread = threading.Thread(target=upload)
    thread.start()
    assert validation_started.wait(timeout=3)
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "uploading"
    allow_validation.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert result["response"].status_code == 200
    assert result["response"].json()["status"] == "draft"


def test_submit_requires_all_slots_and_injects_sync_only_at_submit(client: TestClient):
    task_id = _create(client).json()["id"]
    job_input = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    assert not (job_input / "sync.json").exists()
    for slot in SLOTS[:-1]:
        assert _upload(client, task_id, slot, _mkv(slot.encode())).status_code == 200

    incomplete = client.post(f"/api/v1/tasks/{task_id}/submit")
    assert incomplete.status_code == 409
    assert "cam_04" in incomplete.json()["detail"]
    assert not (job_input / "sync.json").exists()

    assert _upload(client, task_id, "cam_04", _mkv(b"four")).status_code == 200
    submitted = client.post(f"/api/v1/tasks/{task_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "queued"
    assert submitted.json()["submitted_at"].endswith("Z")
    assert json.loads((job_input / "sync.json").read_text()) == {"offset": 17}
    manifest = json.loads((job_input.parent / "input_manifest.json").read_text())
    assert set(manifest) == set(SLOTS) | {"sync"}


def test_preset_creation_and_public_status_mapping(client: TestClient):
    created = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "full"},
    )
    assert created.status_code == 201
    assert created.json()["source_type"] == "preset"
    assert created.json()["status"] == "queued"
    assert {item["slot"] for item in created.json()["inputs"]} == set(SLOTS)

    task_id = created.json()["id"]
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "perception"
        session.add(task)
        session.commit()
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "running"
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "interrupted"
        session.add(task)
        session.commit()
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "failed"


def test_cancel_retry_delete_and_expire_drafts(client: TestClient):
    task_id = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    ).json()["id"]
    canceled = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    retried = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["retry_count"] == 1
    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 409
    assert client.post(f"/api/v1/tasks/{task_id}/cancel").status_code == 200
    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 404

    expired_id = _create(client, "old draft").json()["id"]
    root = client.app.state.storage.prepare(expired_id)
    (root / "input" / "orphan.mkv").write_bytes(_mkv(b"old"))
    with Session(client.app.state.engine) as session:
        draft = session.get(Analysis, expired_id)
        draft.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        draft.updated_at = draft.created_at
        session.add(draft)
        session.commit()
    RetentionService(
        client.app.state.settings,
        client.app.state.engine,
        client.app.state.storage,
    ).run_once()
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, expired_id).status == "expired"
    assert not root.exists()
    expired = client.get(f"/api/v1/tasks/{expired_id}")
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"


def test_task_result_and_media_keep_existing_shapes_with_task_urls(client: TestClient):
    created = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    ).json()
    task_id = created["id"]
    root = client.app.state.storage.analysis_root(task_id)
    output = root / "output"
    _write_json(
        output / "report.json",
        {
            "clips": [],
            "shot_outcomes": [],
            "shot_stats": {"attempts": 0, "makes": 0, "misses": 0, "undetermined": 0},
        },
    )
    _write_json(output / "summary.json", {"student_ids": []})
    _write_json(output / "media_manifest.json", {"phases": "phases.mp4"})
    (output / "viz").mkdir()
    (output / "viz" / "phases.mp4").write_bytes(b"abcdefghij")
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "completed"
        task.progress = 100
        session.add(task)
        session.commit()

    result = client.get(f"/api/v1/tasks/{task_id}/result")
    media = client.get(f"/api/v1/tasks/{task_id}/media/phases", headers={"Range": "bytes=2-5"})
    assert result.status_code == 200
    assert result.json()["media"] == {"phases": f"/api/v1/tasks/{task_id}/media/phases"}
    assert media.status_code == 206
    assert media.content == b"cdef"


def test_legacy_analysis_routes_remain_compatible_and_are_deprecated(client: TestClient):
    response = client.get("/api/v1/analyses")
    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert "GMT" in response.headers["Sunset"]

    created = client.post(
        "/api/v1/analyses/preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    assert created.status_code == 201
    assert created.headers["Deprecation"] == "true"
    assert created.json()["status"] == "queued"

    with Session(client.app.state.engine) as session:
        inputs = session.exec(
            select(TaskInput).where(TaskInput.task_id == created.json()["id"])
        ).all()
    assert {item.slot for item in inputs} == set(SLOTS)


def test_legacy_submission_cannot_bypass_the_daily_task_quota(client: TestClient):
    now = datetime.now(timezone.utc)
    with Session(client.app.state.engine) as session:
        for index in range(20):
            session.add(
                Analysis(
                    title=f"submitted-{index}",
                    status="completed",
                    input_manifest_json="{}",
                    owner_id=1,
                    submitted_at=now,
                    completed_at=now,
                )
            )
        session.commit()

    response = client.post(
        "/api/v1/analyses/preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    assert response.status_code == 429
    assert response.headers["Deprecation"] == "true"


def test_legacy_retry_cannot_bypass_the_unfinished_task_quota(client: TestClient):
    created = client.post(
        "/api/v1/analyses/preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    task_id = created.json()["id"]
    assert client.post(f"/api/v1/analyses/{task_id}/cancel").status_code == 200
    with Session(client.app.state.engine) as session:
        for index in range(5):
            session.add(
                Analysis(
                    title=f"unfinished-{index}",
                    status="queued",
                    input_manifest_json="{}",
                    owner_id=1,
                    submitted_at=datetime.now(timezone.utc),
                )
            )
        session.commit()

    response = client.post(f"/api/v1/analyses/{task_id}/retry")
    assert response.status_code == 429
    assert response.headers["Deprecation"] == "true"


def test_new_retry_supports_a_migrated_legacy_task_without_task_input_rows(client: TestClient):
    task = Analysis(
        title="migrated legacy task",
        status="failed",
        input_manifest_json="{}",
        owner_id=1,
        submitted_at=datetime.now(timezone.utc) - timedelta(days=1),
        created_via="legacy",
    )
    task_id = task.id
    root = client.app.state.storage.prepare(task_id)
    manifest = {}
    for name in (*SLOTS, "sync"):
        path = root / "input" / f"{name}.bin"
        path.write_bytes(b"retained")
        manifest[name] = str(path)
    task.input_manifest_json = json.dumps(manifest)
    with Session(client.app.state.engine) as session:
        session.add(task)
        session.commit()

    retried = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["retry_count"] == 1
