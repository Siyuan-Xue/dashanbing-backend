import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.routes import analyses as analyses_routes
from app.config import AppSettings
from app.main import create_app
from app.models import Analysis
from app.services.retention import RetentionService


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_sample_root(root: Path) -> None:
    group = root / "outputs" / "v3" / "group_04"
    _write_json(
        group / "report.json",
        {
            "clips": [{"clip_id": "stu_00:1", "action_type": "jump_shot", "start_ms": 1, "end_ms": 2, "release_ms": 2}],
            "shot_outcomes": [{"clip_id": "stu_00:1", "made": True}],
            "shot_stats": {"attempts": 1, "makes": 1, "misses": 0, "undetermined": 0},
        },
    )
    _write_json(group / "summary.json", {"student_ids": ["stu_00"], "clip_count": 1, "action_type_hist": {"jump_shot": 1}})
    _write_json(group / "eval_vs_gt.json", {"precision": 1.0, "recall": 1.0})
    viz = group / "viz"
    viz.mkdir()
    for name in (
        "cam_01_annotated.mp4",
        "cam_02_annotated.mp4",
        "cam_03_annotated.mp4",
        "cam_04_ball.mp4",
        "phases.mp4",
    ):
        (viz / name).write_bytes(b"0123456789")
    inputs = root / "test_data_v3"
    inputs.mkdir(parents=True)
    for name in ("0-2.mkv", "4-1.mkv", "4-2.mkv", "4-3.mkv", "4-4.mkv"):
        (inputs / name).write_bytes(b"video")
    (inputs / "sync").mkdir()
    (inputs / "sync" / "group_04.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path):
    sample_root = tmp_path / "samples"
    _build_sample_root(sample_root)
    sync = tmp_path / "sync.json"
    sync.write_text("{}", encoding="utf-8")
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
    )
    with TestClient(create_app(settings=settings), raise_server_exceptions=False) as test_client:
        test_client.app.state.readiness.require_ready = lambda: None
        yield test_client


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "correct-password"},
    )
    assert response.status_code == 200
    assert response.cookies.get("access_token")


def test_bootstrap_login_uses_http_only_cookie_and_has_no_public_registration(client: TestClient):
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "correct-password"},
    )
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/users/me").json()["username"] == "admin"
    assert client.post("/auth/register", json={"username": "new", "password": "password"}).status_code in {404, 405}


def test_oversized_upload_is_rejected_before_multipart_parsing(client: TestClient):
    _login(client)
    response = client.post(
        "/api/v1/analyses/upload",
        content=b"not-a-multipart-body",
        headers={"Content-Length": str(31 * 1024**3)},
    )

    assert response.status_code == 413


def test_unauthenticated_upload_is_rejected_before_multipart_parsing(client: TestClient):
    response = client.post(
        "/api/v1/analyses/upload",
        content=b"not-a-multipart-body",
        headers={"Content-Length": "20"},
    )

    assert response.status_code == 401


def test_upload_reserves_declared_size_before_parsing(client: TestClient, monkeypatch):
    _login(client)
    monkeypatch.setattr(
        "app.main.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 0})(),
    )

    response = client.post(
        "/api/v1/analyses/upload",
        content=b"not-a-multipart-body",
        headers={"Content-Length": "20"},
    )

    assert response.status_code == 507


def test_preset_result_is_protected_and_media_supports_range(client: TestClient):
    assert client.get("/api/v1/presets/quick-demo/result").status_code == 401
    _login(client)

    result = client.get("/api/v1/presets/quick-demo/result")
    media = client.get(
        "/api/v1/presets/quick-demo/media/phases",
        headers={"Range": "bytes=2-5"},
    )

    assert result.status_code == 200
    assert result.json()["action_counts"]["jump_shot"] == 1
    assert "stu_" not in result.text
    assert media.status_code == 206
    assert media.content == b"2345"


def test_upload_creates_isolated_queued_job_and_supports_cancel_retry_delete(client: TestClient):
    _login(client)
    files = {
        "enrollment_video": ("enroll.mkv", b"enroll", "video/x-matroska"),
        "cam_01": ("one.mkv", b"one", "video/x-matroska"),
        "cam_02": ("two.mkv", b"two", "video/x-matroska"),
        "cam_03": ("three.mkv", b"three", "video/x-matroska"),
        "cam_04": ("four.mkv", b"four", "video/x-matroska"),
    }
    created = client.post(
        "/api/v1/analyses/upload",
        data={"title": "训练一", "mode": "quick"},
        files=files,
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "queued"
    assert payload["created_at"].endswith("Z")
    assert payload["updated_at"].endswith("Z")
    analysis_id = payload["id"]

    job_root = Path(client.app.state.settings.runtime_root) / "analyses" / analysis_id
    assert (job_root / "input" / "enrollment.mkv").read_bytes() == b"enroll"
    assert (job_root / "input" / "cam_04.mkv").read_bytes() == b"four"
    assert (job_root / "input" / "sync.json").is_file()

    canceled = client.post(f"/api/v1/analyses/{analysis_id}/cancel")
    retried = client.post(f"/api/v1/analyses/{analysis_id}/retry")
    deleted = client.delete(f"/api/v1/analyses/{analysis_id}")

    assert canceled.json()["status"] == "canceled"
    assert retried.json()["status"] == "queued"
    assert deleted.status_code == 204
    assert not job_root.exists()


def test_running_cancel_request_is_idempotent_until_worker_stops(client: TestClient):
    _login(client)
    analysis = Analysis(
        title="running",
        status="perception",
        input_manifest_json="{}",
    )
    with Session(client.app.state.engine) as session:
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id

    first = client.post(f"/api/v1/analyses/{analysis_id}/cancel")
    second = client.post(f"/api/v1/analyses/{analysis_id}/cancel")

    assert first.json()["status"] == "cancel_requested"
    assert second.json()["status"] == "cancel_requested"


def test_retry_rejects_expired_input_manifest(client: TestClient):
    _login(client)
    missing = Path(client.app.state.settings.runtime_root) / "expired.mkv"
    analysis = Analysis(
        title="expired",
        status="failed",
        input_manifest_json=json.dumps(
            {
                name: str(missing)
                for name in ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04", "sync")
            }
        ),
    )
    with Session(client.app.state.engine) as session:
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id

    response = client.post(f"/api/v1/analyses/{analysis_id}/retry")

    assert response.status_code == 409
    assert "原输入" in response.json()["detail"]


def test_retry_transaction_wins_race_with_retention_cleanup(client: TestClient, monkeypatch):
    _login(client)
    now = datetime.now(timezone.utc)
    analysis = Analysis(
        title="retry-race",
        status="failed",
        input_manifest_json="{}",
        completed_at=now - timedelta(days=40),
    )
    root = client.app.state.storage.prepare(analysis.id)
    input_paths = {}
    for name in ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04", "sync"):
        path = root / "input" / f"{name}.bin"
        path.write_bytes(b"retained")
        input_paths[name] = str(path)
    analysis.input_manifest_json = json.dumps(input_paths)
    with Session(client.app.state.engine) as session:
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id

    validation_started = threading.Event()
    allow_retry_commit = threading.Event()
    original_validator = analyses_routes._manifest_inputs_available

    def gated_validator(manifest: dict) -> bool:
        validation_started.set()
        assert allow_retry_commit.wait(timeout=3)
        return original_validator(manifest)

    monkeypatch.setattr("app.api.routes.analyses._manifest_inputs_available", gated_validator)
    retry_result = {}

    def run_retry() -> None:
        retry_result["response"] = client.post(f"/api/v1/analyses/{analysis_id}/retry")

    retry_thread = threading.Thread(target=run_retry)
    retry_thread.start()
    assert validation_started.wait(timeout=3)

    retention = RetentionService(
        client.app.state.settings,
        client.app.state.engine,
        client.app.state.storage,
    )
    retention_thread = threading.Thread(target=lambda: retention.run_once(now=now))
    retention_thread.start()
    time.sleep(0.1)
    assert retention_thread.is_alive()

    allow_retry_commit.set()
    retry_thread.join(timeout=3)
    retention_thread.join(timeout=3)

    assert not retry_thread.is_alive()
    assert not retention_thread.is_alive()
    assert retry_result["response"].status_code == 200
    assert retry_result["response"].json()["status"] == "queued"
    assert all(Path(path).is_file() for path in input_paths.values())


def test_preset_rerun_creates_job_without_copying_read_only_sample_inputs(client: TestClient):
    _login(client)
    response = client.post("/api/v1/analyses/preset", json={"preset_id": "quick-demo", "mode": "full"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_type"] == "preset"
    with Session(client.app.state.engine) as session:
        analysis = session.get(Analysis, payload["id"])
    manifest = json.loads(analysis.input_manifest_json)
    assert manifest["cam_02"].endswith("test_data_v3/4-2.mkv")


def test_logout_clears_cookie(client: TestClient):
    _login(client)
    response = client.post("/api/v1/logout")
    assert response.status_code == 204
    assert client.get("/api/v1/users/me").status_code == 401


def test_completed_analysis_media_uses_manifest_and_supports_range(client: TestClient):
    _login(client)
    analysis = Analysis(
        title="完成任务",
        mode="full",
        source_type="upload",
        status="completed",
        progress=100,
        input_manifest_json="{}",
    )
    with Session(client.app.state.engine) as session:
        session.add(analysis)
        session.commit()
        analysis_id = analysis.id
    output = client.app.state.storage.prepare(analysis_id) / "output"
    _write_json(
        output / "report.json",
        {"clips": [], "shot_outcomes": [], "shot_stats": {"attempts": 0, "makes": 0, "misses": 0, "undetermined": 0}},
    )
    _write_json(output / "summary.json", {"student_ids": []})
    _write_json(output / "media_manifest.json", {"phases": "phases.mp4", "evil": "../../secret"})
    (output / "viz").mkdir()
    (output / "viz" / "phases.mp4").write_bytes(b"abcdefghij")

    result = client.get(f"/api/v1/analyses/{analysis_id}/result")
    media = client.get(
        f"/api/v1/analyses/{analysis_id}/media/phases",
        headers={"Range": "bytes=3-6"},
    )

    assert result.status_code == 200
    assert result.json()["media"] == {"phases": f"/api/v1/analyses/{analysis_id}/media/phases"}
    assert media.status_code == 206
    assert media.content == b"defg"
    assert client.get(f"/api/v1/analyses/{analysis_id}/media/evil").status_code == 404


def test_real_upload_is_blocked_before_saving_when_runtime_is_not_ready(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'blocked.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "missing-samples",
        model_root=tmp_path / "missing-models",
        sync_config=tmp_path / "missing-sync.json",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        min_free_storage_gb=0,
        simulation_mode=False,
        worker_enabled=False,
        auto_create_schema=True,
    )
    with TestClient(create_app(settings=settings)) as blocked_client:
        _login(blocked_client)
        response = blocked_client.post(
            "/api/v1/analyses/upload",
            data={"title": "should not save", "mode": "full"},
            files={
                name: (f"{name}.mkv", b"video", "video/x-matroska")
                for name in ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04")
            },
        )
    assert response.status_code == 503
    assert "cuda" in response.json()["detail"]
    assert not any((settings.runtime_root / "analyses").iterdir())


def test_disabled_worker_rejects_new_analysis(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'disabled-worker.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )

    with TestClient(create_app(settings=settings)) as disabled_client:
        _login(disabled_client)
        response = disabled_client.post(
            "/api/v1/analyses/preset",
            json={"preset_id": "quick-demo", "mode": "quick"},
        )

    assert response.status_code == 503
    assert "worker" in response.json()["detail"]
