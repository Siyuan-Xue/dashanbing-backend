import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis, StorageDeletion


def _settings(tmp_path: Path) -> AppSettings:
    sync = tmp_path / "sync.json"
    sync.write_text("{}", encoding="utf-8")
    return AppSettings(
        database_url=f"sqlite:///{tmp_path / 'deletions.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
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


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(settings=_settings(tmp_path)), raise_server_exceptions=False) as test_client:
        login = test_client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "correct-password"},
        )
        assert login.status_code == 200
        yield test_client


def _draft_with_storage(client: TestClient) -> tuple[str, Path]:
    response = client.post(
        "/api/v1/tasks",
        json={"title": "deletion target", "mode": "quick"},
    )
    assert response.status_code == 201
    task_id = response.json()["id"]
    root = client.app.state.storage.prepare(task_id)
    (root / "input" / "payload.mkv").write_bytes(b"payload")
    return task_id, root


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/tasks/{task_id}",
        "/api/v1/analyses/{task_id}",
    ],
)
def test_logical_delete_commits_outbox_before_task_or_legacy_cleanup(
    client: TestClient,
    monkeypatch,
    endpoint: str,
):
    """Catches either DELETE removing storage before its logical transaction commits."""
    task_id, root = _draft_with_storage(client)
    observed: dict[str, object] = {}

    def fail_cleanup(analysis_id: str, target: str) -> None:
        with Session(client.app.state.engine) as session:
            observed["analysis"] = session.get(Analysis, analysis_id)
            observed["deletion"] = session.get(StorageDeletion, (analysis_id, target))
        raise OSError("filesystem temporarily unavailable")

    monkeypatch.setattr(
        client.app.state.storage,
        "remove_deletion_target",
        fail_cleanup,
        raising=False,
    )

    response = client.delete(endpoint.format(task_id=task_id))

    assert response.status_code == 204
    assert observed["analysis"] is None
    assert isinstance(observed["deletion"], StorageDeletion)
    assert root.is_dir()
    with Session(client.app.state.engine) as session:
        pending = session.get(StorageDeletion, (task_id, "analysis_root"))
        assert pending is not None
        assert pending.attempts == 1
        assert "temporarily unavailable" in (pending.last_error or "")


def test_failed_logical_commit_never_starts_filesystem_cleanup(
    client: TestClient,
    monkeypatch,
):
    """Catches deleting bytes for a task whose database deletion rolls back."""
    task_id, root = _draft_with_storage(client)
    original_commit = Session.commit

    def fail_outbox_commit(session: Session) -> None:
        pending_count = session.connection().exec_driver_sql(
            "SELECT COUNT(*) FROM storage_deletion"
        ).scalar_one()
        if pending_count:
            raise RuntimeError("injected commit failure")
        original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_outbox_commit)

    response = client.delete(f"/api/v1/tasks/{task_id}")

    assert response.status_code == 500
    assert root.is_dir()
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, task_id) is not None
        assert session.get(StorageDeletion, (task_id, "analysis_root")) is None


def test_slow_cleanup_releases_sqlite_writer_for_api_key_authentication(
    client: TestClient,
    monkeypatch,
):
    """Catches recursive deletion starving API-key audit writes after logical commit."""
    key_response = client.post("/api/v1/api-keys", json={"name": "cleanup probe"})
    assert key_response.status_code == 201
    secret = key_response.json()["secret"]
    task_id, _root = _draft_with_storage(client)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {secret}"}
    cleanup_started = threading.Event()
    release_cleanup = threading.Event()
    auth_finished = threading.Event()
    responses: dict[str, object] = {}
    original_cleanup = client.app.state.storage.remove_deletion_target

    def slow_cleanup(analysis_id: str, _target: str) -> None:
        cleanup_started.set()
        assert release_cleanup.wait(timeout=3)
        original_cleanup(analysis_id, "analysis_root")

    monkeypatch.setattr(
        client.app.state.storage,
        "remove_deletion_target",
        slow_cleanup,
        raising=False,
    )

    def delete_task() -> None:
        responses["delete"] = client.delete(f"/api/v1/tasks/{task_id}", headers=headers)

    def authenticate() -> None:
        responses["auth"] = client.get("/api/v1/users/me", headers=headers)
        auth_finished.set()

    delete_thread = threading.Thread(target=delete_task)
    delete_thread.start()
    assert cleanup_started.wait(timeout=3)
    auth_thread = threading.Thread(target=authenticate)
    auth_thread.start()
    writer_was_not_blocked = auth_finished.wait(timeout=0.5)
    release_cleanup.set()
    delete_thread.join(timeout=3)
    auth_thread.join(timeout=3)

    assert writer_was_not_blocked
    assert not delete_thread.is_alive()
    assert not auth_thread.is_alive()
    assert responses["delete"].status_code == 204
    assert responses["auth"].status_code == 200
    assert not _root.exists()
    with Session(client.app.state.engine) as session:
        assert session.get(StorageDeletion, (task_id, "analysis_root")) is None


def test_draft_expiry_cleanup_failure_is_retried_during_restart(
    client: TestClient,
    monkeypatch,
):
    """Catches expired draft storage becoming an untracked permanent orphan."""
    task_id, root = _draft_with_storage(client)
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        assert task is not None
        task.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        task.updated_at = task.created_at
        session.add(task)
        session.commit()

    def fail_cleanup(_analysis_id: str, _target: str) -> None:
        raise OSError("draft cleanup interrupted")

    monkeypatch.setattr(
        client.app.state.storage,
        "remove_deletion_target",
        fail_cleanup,
        raising=False,
    )
    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    assert root.is_dir()
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        pending = session.get(StorageDeletion, (task_id, "analysis_root"))
        assert task is not None and task.status == "expired"
        assert pending is not None and pending.attempts == 1

    restarted = create_app(settings=client.app.state.settings)
    with TestClient(restarted, raise_server_exceptions=False):
        pass

    assert not root.exists()
    with Session(restarted.state.engine) as session:
        assert session.get(StorageDeletion, (task_id, "analysis_root")) is None


def test_restart_acknowledges_cleanup_completed_before_outbox_ack(
    client: TestClient,
):
    """Catches a crash after filesystem removal but before deleting the outbox row."""
    task_id, root = _draft_with_storage(client)
    with Session(client.app.state.engine) as session:
        session.add(StorageDeletion(analysis_id=task_id, target="analysis_root"))
        task = session.get(Analysis, task_id)
        assert task is not None
        session.delete(task)
        session.commit()
    client.app.state.storage.delete(task_id)
    assert not root.exists()

    restarted = create_app(settings=client.app.state.settings)
    with TestClient(restarted, raise_server_exceptions=False):
        pass

    with Session(restarted.state.engine) as session:
        assert session.get(StorageDeletion, (task_id, "analysis_root")) is None


def test_restart_rejects_untrusted_deletion_paths_without_touching_outside_files(
    client: TestClient,
):
    """Catches a corrupted outbox escaping the allow-listed analysis storage root."""
    protected = client.app.state.settings.runtime_root / "protected.txt"
    protected.write_text("keep", encoding="utf-8")
    with Session(client.app.state.engine) as session:
        session.add(
            StorageDeletion(analysis_id="../protected", target="analysis_root")
        )
        session.add(
            StorageDeletion(analysis_id="safe-id", target="../../protected")
        )
        session.commit()

    restarted = create_app(settings=client.app.state.settings)
    with TestClient(restarted, raise_server_exceptions=False):
        pass

    assert protected.read_text(encoding="utf-8") == "keep"
    with Session(restarted.state.engine) as session:
        pending = list(session.exec(select(StorageDeletion)).all())
    assert len(pending) == 2
    assert all(item.attempts == 1 for item in pending)
    assert all(item.last_error for item in pending)


def test_fixed_tier_cleanup_refuses_symlink_redirection_within_analysis_root(
    client: TestClient,
):
    """Catches an allow-listed tier symlink redirecting cleanup to another tier."""
    task_id, root = _draft_with_storage(client)
    protected = root / "output" / "keep.txt"
    protected.write_text("keep", encoding="utf-8")
    (root / "input" / "payload.mkv").unlink()
    (root / "input").rmdir()
    (root / "input").symlink_to(root / "output", target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        client.app.state.storage.remove_deletion_target(task_id, "input")

    assert protected.read_text(encoding="utf-8") == "keep"
    assert (root / "input").is_symlink()
