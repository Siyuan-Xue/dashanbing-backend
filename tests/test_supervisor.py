import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis
from app.services.supervisor import AnalysisSupervisor


def test_startup_marks_active_jobs_interrupted_but_preserves_queue(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'supervisor.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    with TestClient(app):
        active = Analysis(title="active", status="perception", input_manifest_json="{}")
        queued = Analysis(title="queued", status="queued", input_manifest_json="{}")
        with Session(app.state.engine) as session:
            session.add(active)
            session.add(queued)
            session.commit()
            active_id, queued_id = active.id, queued.id
        AnalysisSupervisor(app)._mark_interrupted()
        with Session(app.state.engine) as session:
            active = session.get(Analysis, active_id)
            queued = session.get(Analysis, queued_id)
        assert active.status == "interrupted"
        assert "重启" in active.stage_message
        assert queued.status == "queued"


def test_idle_supervisor_continues_after_asyncio_timeout(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'idle.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    with TestClient(app):
        supervisor = AnalysisSupervisor(app)
        calls = 0

        async def fake_wait_for(awaitable, timeout):
            nonlocal calls
            awaitable.close()
            calls += 1
            if calls == 1:
                raise asyncio.TimeoutError
            supervisor._stop.set()
            return True

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        asyncio.run(supervisor._loop())

    assert calls == 2


def test_supervisor_contains_one_job_exception_and_keeps_loop_alive(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'errors.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    with TestClient(app):
        supervisor = AnalysisSupervisor(app)
        supervisor._last_retention_run = time.monotonic()
        calls = 0

        async def fake_run_one(_analysis_id: str):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic worker failure")
            supervisor._stop.set()

        monkeypatch.setattr(supervisor, "_next_queued_id", lambda: "analysis-id")
        monkeypatch.setattr(supervisor, "_run_one", fake_run_one)
        asyncio.run(supervisor._loop())

    assert calls == 2


def test_failed_startup_preflight_keeps_restored_queue_blocked(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'gated.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=True,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    monkeypatch.setattr(
        app.state.readiness,
        "preflight",
        lambda: {"ready": False, "mode": "gpu", "checks": []},
    )

    with TestClient(app):
        queued = Analysis(title="blocked", status="queued", input_manifest_json="{}")
        with Session(app.state.engine) as session:
            session.add(queued)
            session.commit()
            queued_id = queued.id
        time.sleep(0.1)
        with Session(app.state.engine) as session:
            stored = session.get(Analysis, queued_id)

    assert stored.status == "queued"
