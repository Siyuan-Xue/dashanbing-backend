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
from app.api.routes import analyses as analyses_routes
from app.api.routes import tasks as task_routes
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


def test_deleting_submitted_tasks_does_not_refund_the_daily_quota(client: TestClient):
    for index in range(20):
        created = client.post(
            "/api/v1/tasks/from-preset",
            json={"preset_id": "quick-demo", "mode": "quick"},
        )
        assert created.status_code == 201, index
        task_id = created.json()["id"]
        with Session(client.app.state.engine) as session:
            task = session.get(Analysis, task_id)
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            session.add(task)
            session.commit()
        assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204

    limited = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    assert limited.status_code == 429


def test_retry_consumes_a_new_daily_submission_at_the_limit(client: TestClient):
    now = datetime.now(timezone.utc)
    with Session(client.app.state.engine) as session:
        for index in range(19):
            session.add(
                Analysis(
                    title=f"prior-{index}",
                    status="completed",
                    input_manifest_json="{}",
                    owner_id=1,
                    submitted_at=now,
                    completed_at=now,
                )
            )
        session.commit()
    created = client.post(
        "/api/v1/tasks/from-preset",
        json={"preset_id": "quick-demo", "mode": "quick"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert client.post(f"/api/v1/tasks/{task_id}/cancel").status_code == 200

    retried = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert retried.status_code == 429


def test_post_install_database_failure_restores_the_prior_slot(client: TestClient, monkeypatch):
    task_id = _create(client).json()["id"]
    assert _upload(client, task_id, "cam_01", _mkv(b"old"), "old.mkv").status_code == 200
    destination = (
        Path(client.app.state.settings.runtime_root)
        / "analyses"
        / task_id
        / "input"
        / "cam_01.mkv"
    )
    original_begin = task_routes.begin_write
    calls = 0

    def fail_after_install(session: Session) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("database unavailable after install")
        original_begin(session)

    monkeypatch.setattr(task_routes, "begin_write", fail_after_install)
    failed = _upload(client, task_id, "cam_01", _mkv(b"new"), "new.mkv")
    assert failed.status_code == 500
    assert destination.read_bytes() == _mkv(b"old")
    detail = client.get(f"/api/v1/tasks/{task_id}").json()
    assert detail["status"] == "draft"
    assert detail["inputs"][0]["original_filename"] == "old.mkv"
    assert [path for path in destination.parent.iterdir() if path.name.startswith(".cam_01")] == []


def test_supervisor_recovers_an_interrupted_replacement_and_cleans_artifacts(client: TestClient):
    task_id = _create(client).json()["id"]
    assert _upload(client, task_id, "cam_01", _mkv(b"old"), "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"
    backup = input_root / ".cam_01-crash.bak"
    temporary = input_root / ".cam_01-crash.tmp"
    destination.replace(backup)
    destination.write_bytes(_mkv(b"new"))
    temporary.write_bytes(b"partial")
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "uploading"
        session.add(task)
        session.commit()

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == _mkv(b"old")
    assert not backup.exists()
    assert not temporary.exists()
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "draft"
    assert item.original_filename == "old.mkv"


def test_restart_keeps_committed_replacement_after_finalize_interruption_and_cancel(
    client: TestClient,
    monkeypatch,
):
    task_id = _create(client).json()["id"]
    assert _upload(client, task_id, "cam_01", _mkv(b"old"), "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"

    def interrupt_finalize(_installed) -> None:
        raise OSError("simulated process interruption during finalization")

    monkeypatch.setattr(client.app.state.storage, "finalize_task_input", interrupt_finalize)
    replaced = _upload(client, task_id, "cam_01", _mkv(b"new"), "new.mkv")
    assert replaced.status_code == 200
    assert destination.read_bytes() == _mkv(b"new")
    assert [path for path in input_root.iterdir() if path.name.startswith(".cam_01")]

    canceled = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == _mkv(b"new")
    assert [path for path in input_root.iterdir() if path.name.startswith(".cam_01")] == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "canceled"
    assert item.original_filename == "new.mkv"
    assert item.byte_size == len(_mkv(b"new"))


def test_restart_uses_committed_metadata_when_marker_publication_fails(
    client: TestClient,
    monkeypatch,
):
    task_id = _create(client).json()["id"]
    assert _upload(client, task_id, "cam_01", _mkv(b"old"), "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"

    def fail_commit_marker(_installed) -> None:
        raise OSError("simulated committed-marker rename failure")

    monkeypatch.setattr(
        client.app.state.storage,
        "mark_task_input_committed",
        fail_commit_marker,
    )
    replaced = _upload(client, task_id, "cam_01", _mkv(b"new"), "new.mkv")
    assert replaced.status_code == 200
    assert destination.read_bytes() == _mkv(b"new")
    assert list(input_root.glob(".cam_01-*.pending"))

    canceled = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert canceled.status_code == 200

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == _mkv(b"new")
    assert [path for path in input_root.iterdir() if path.name.startswith(".cam_01")] == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "canceled"
    assert item.original_filename == "new.mkv"
    assert item.byte_size == len(_mkv(b"new"))
    assert item.upload_operation_id is not None


def test_successful_replacement_supersedes_stale_pending_operation(
    client: TestClient,
    monkeypatch,
):
    task_id = _create(client).json()["id"]
    old_bytes = _mkv(b"old")
    first_bytes = _mkv(b"first")
    final_bytes = _mkv(b"final")
    assert _upload(client, task_id, "cam_01", old_bytes, "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"
    original_mark_committed = client.app.state.storage.mark_task_input_committed
    failed_operation_id = None

    def fail_first_commit_marker(installed):
        nonlocal failed_operation_id
        if failed_operation_id is None:
            failed_operation_id = installed.operation_id
            raise OSError("simulated first marker-publication failure")
        return original_mark_committed(installed)

    monkeypatch.setattr(
        client.app.state.storage,
        "mark_task_input_committed",
        fail_first_commit_marker,
    )
    first = _upload(client, task_id, "cam_01", first_bytes, "first.mkv")
    assert first.status_code == 200
    assert failed_operation_id is not None
    assert list(input_root.glob(f".cam_01-{failed_operation_id}.*"))

    final = _upload(client, task_id, "cam_01", final_bytes, "final.mkv")
    assert final.status_code == 200
    assert destination.read_bytes() == final_bytes
    with Session(client.app.state.engine) as session:
        final_item = session.get(TaskInput, (task_id, "cam_01"))
        final_operation_id = final_item.upload_operation_id
    assert final_operation_id is not None
    assert final_operation_id != failed_operation_id

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == final_bytes
    assert list(input_root.glob(".cam_01-*")) == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "draft"
    assert item.original_filename == "final.mkv"
    assert item.byte_size == len(final_bytes)
    assert item.upload_operation_id == final_operation_id


def test_restart_rolls_back_unmatched_pending_replacement_for_draft(
    client: TestClient,
):
    task_id = _create(client).json()["id"]
    old_bytes = _mkv(b"old")
    new_bytes = _mkv(b"new")
    assert _upload(client, task_id, "cam_01", old_bytes, "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"
    operation_id = "uncommitted-replacement"
    backup = input_root / f".cam_01-{operation_id}.bak"
    pending = input_root / f".cam_01-{operation_id}.pending"
    destination.replace(backup)
    destination.write_bytes(new_bytes)
    pending.write_text("cam_01", encoding="utf-8")
    with Session(client.app.state.engine) as session:
        item = session.get(TaskInput, (task_id, "cam_01"))
        prior_operation_id = item.upload_operation_id
        task = session.get(Analysis, task_id)
    assert task.status == "draft"
    assert prior_operation_id is not None
    assert prior_operation_id != operation_id

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == old_bytes
    assert list(input_root.glob(".cam_01-*")) == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "draft"
    assert item.original_filename == "old.mkv"
    assert item.byte_size == len(old_bytes)
    assert item.upload_operation_id == prior_operation_id


def test_restart_rolls_back_unmatched_pending_first_upload_for_draft(
    client: TestClient,
):
    task_id = _create(client).json()["id"]
    input_root = client.app.state.storage.prepare(task_id) / "input"
    destination = input_root / "cam_01.mkv"
    destination.write_bytes(_mkv(b"uncommitted"))
    (input_root / ".cam_01-first-upload.pending").write_text(
        "cam_01",
        encoding="utf-8",
    )

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert not destination.exists()
    assert list(input_root.glob(".cam_01-*")) == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "draft"
    assert item is None


def test_restart_keeps_pending_replacement_for_legacy_null_operation_id(
    client: TestClient,
):
    task_id = _create(client).json()["id"]
    old_bytes = _mkv(b"old")
    new_bytes = _mkv(b"new")
    assert _upload(client, task_id, "cam_01", old_bytes, "old.mkv").status_code == 200
    input_root = Path(client.app.state.settings.runtime_root) / "analyses" / task_id / "input"
    destination = input_root / "cam_01.mkv"
    operation_id = "legacy-replacement"
    backup = input_root / f".cam_01-{operation_id}.bak"
    pending = input_root / f".cam_01-{operation_id}.pending"
    destination.replace(backup)
    destination.write_bytes(new_bytes)
    pending.write_text("cam_01", encoding="utf-8")
    with Session(client.app.state.engine) as session:
        item = session.get(TaskInput, (task_id, "cam_01"))
        item.original_filename = "new.mkv"
        item.byte_size = len(new_bytes)
        item.upload_operation_id = None
        session.add(item)
        session.commit()

    from app.services.supervisor import AnalysisSupervisor

    AnalysisSupervisor(client.app)._mark_interrupted()

    assert destination.read_bytes() == new_bytes
    assert list(input_root.glob(".cam_01-*")) == []
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        item = session.get(TaskInput, (task_id, "cam_01"))
    assert task.status == "draft"
    assert item.original_filename == "new.mkv"
    assert item.byte_size == len(new_bytes)
    assert item.upload_operation_id is None


def test_legacy_upload_does_not_hold_the_database_writer_during_media_io(
    client: TestClient,
    monkeypatch,
):
    entered_media_io = threading.Event()
    release_media_io = threading.Event()
    writer_finished = threading.Event()
    original_save = client.app.state.storage.save_uploads

    def gated_save(*args, **kwargs):
        entered_media_io.set()
        assert release_media_io.wait(timeout=3)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(client.app.state.storage, "save_uploads", gated_save)
    result = {}

    def upload() -> None:
        result["response"] = client.post(
            "/api/v1/analyses/upload",
            data={"title": "legacy", "mode": "quick"},
            files={
                slot: (f"{slot}.mkv", _mkv(slot.encode()), "video/x-matroska")
                for slot in SLOTS
            },
        )

    def write_database() -> None:
        with Session(client.app.state.engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            session.connection().exec_driver_sql("UPDATE user SET is_active = is_active")
            session.commit()
        writer_finished.set()

    upload_thread = threading.Thread(target=upload)
    upload_thread.start()
    assert entered_media_io.wait(timeout=3)
    writer_thread = threading.Thread(target=write_database)
    writer_thread.start()
    writer_was_not_blocked = writer_finished.wait(timeout=0.5)
    release_media_io.set()
    upload_thread.join(timeout=3)
    writer_thread.join(timeout=3)
    assert writer_was_not_blocked
    assert result["response"].status_code == 201


def test_legacy_delete_obeys_staged_task_lifecycle_rules(client: TestClient):
    task_id = _create(client).json()["id"]
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "uploading"
        session.add(task)
        session.commit()
    uploading = client.delete(f"/api/v1/analyses/{task_id}")
    assert uploading.status_code == 409

    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = "queued"
        session.add(task)
        session.commit()
    queued = client.delete(f"/api/v1/analyses/{task_id}")
    assert queued.status_code == 409
    assert queued.headers["Deprecation"] == "true"


def test_legacy_delete_serializes_lifecycle_check_against_upload_transition(
    client: TestClient,
    monkeypatch,
):
    task_id = _create(client).json()["id"]
    delete_checked = threading.Event()
    allow_delete = threading.Event()
    upload_reached_media_io = threading.Event()
    allow_media_io = threading.Event()
    original_predicate = analyses_routes.task_can_be_deleted

    def gated_predicate(status: str) -> bool:
        delete_checked.set()
        assert allow_delete.wait(timeout=3)
        return original_predicate(status)

    def gated_probe(_path: Path, _title: str) -> None:
        upload_reached_media_io.set()
        assert allow_media_io.wait(timeout=3)

    monkeypatch.setattr(analyses_routes, "task_can_be_deleted", gated_predicate)
    monkeypatch.setattr(client.app.state.storage, "video_probe", gated_probe)
    results = {}

    def delete() -> None:
        results["delete"] = client.delete(f"/api/v1/analyses/{task_id}")

    def upload() -> None:
        results["upload"] = _upload(client, task_id, "cam_01", _mkv(b"new"), "new.mkv")

    delete_thread = threading.Thread(target=delete)
    delete_thread.start()
    assert delete_checked.wait(timeout=3)
    upload_thread = threading.Thread(target=upload)
    upload_thread.start()
    upload_transitioned_before_delete = upload_reached_media_io.wait(timeout=0.5)
    allow_delete.set()
    delete_thread.join(timeout=3)
    allow_media_io.set()
    upload_thread.join(timeout=3)

    assert not delete_thread.is_alive()
    assert not upload_thread.is_alive()
    assert not upload_transitioned_before_delete
    assert results["delete"].status_code == 204
    assert results["upload"].status_code == 404
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 404


def test_task_status_schema_is_closed_and_unknown_internal_states_fail(client: TestClient):
    allowed = {
        "draft",
        "uploading",
        "queued",
        "running",
        "completed",
        "failed",
        "canceled",
        "expired",
    }
    schema = client.app.openapi()["components"]["schemas"]["TaskPublic"]["properties"]["status"]
    assert set(schema["enum"]) == allowed

    task = Analysis(
        title="unknown state",
        status="mystery",
        input_manifest_json="{}",
        owner_id=1,
        submitted_at=None,
    )
    task_id = task.id
    with Session(client.app.state.engine) as session:
        session.add(task)
        session.commit()
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 500


def test_workspace_contract_schema_closes_task_mode_slot_and_required_timestamps(
    client: TestClient,
):
    schemas = client.app.openapi()["components"]["schemas"]

    assert set(schemas["TaskPublic"]["properties"]["mode"]["enum"]) == {
        "quick",
        "full",
    }
    assert set(schemas["TaskInputPublic"]["properties"]["slot"]["enum"]) == {
        "enrollment_video",
        "cam_01",
        "cam_02",
        "cam_03",
        "cam_04",
    }
    assert schemas["TaskPublic"]["properties"]["created_at"]["type"] == "string"
    assert schemas["TaskPublic"]["properties"]["updated_at"]["type"] == "string"
