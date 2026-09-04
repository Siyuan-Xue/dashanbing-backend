import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis
from app.services.analysis_state import ACTIVE_STATUSES, AnalysisStatus, transition_status
from app.services.worker import _run_subprocess, _set_stage, _simulate, _terminate_process_group, run_analysis


def test_simulation_worker_completes_without_exposing_research_ids(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        model_root=tmp_path / "models",
        sync_config=tmp_path / "sync.json",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    settings.sync_config.write_text("{}", encoding="utf-8")
    app = create_app(settings=settings)
    with TestClient(app):
        analysis = Analysis(
            title="模拟上传",
            mode="quick",
            source_type="upload",
            input_manifest_json=json.dumps({}),
        )
        app.state.storage.prepare(analysis.id)
        with Session(app.state.engine) as session:
            session.add(analysis)
            session.commit()
            analysis_id = analysis.id

        asyncio.run(run_analysis(app, analysis_id))

        with Session(app.state.engine) as session:
            finished = session.get(Analysis, analysis_id)
        assert finished.status == "completed"
        assert finished.progress == 100
        output = app.state.storage.analysis_root(analysis_id) / "output"
        assert json.loads((output / "report.json").read_text())["clips"] == []
        assert json.loads((output / "summary.json").read_text())["student_ids"] == []


def test_preset_simulation_exports_only_five_public_review_videos(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'preset-worker.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        model_root=tmp_path / "models",
        sync_config=tmp_path / "sync.json",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    source = settings.sample_root / "outputs" / "v3" / "group_04"
    viz = source / "viz"
    viz.mkdir(parents=True)
    for name in ("report.json", "summary.json", "motion.json"):
        (source / name).write_text("{}", encoding="utf-8")
    (viz / "phases.mp4").write_bytes(b"processed-mosaic")
    (viz / "cam_01_annotated.mp4").write_bytes(b"private-annotated")

    def install_originals(target: Path, _sources: dict):
        target.mkdir(parents=True, exist_ok=True)
        for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
            (target / f"{camera}_original.mp4").write_bytes(camera.encode())

    monkeypatch.setattr("app.services.worker.install_original_camera_videos", install_originals)
    app = create_app(settings=settings)
    analysis = Analysis(
        title="预置模拟",
        source_type="preset",
        preset_id="quick-demo",
        input_manifest_json="{}",
    )

    _simulate(app, analysis)

    public_viz = app.state.storage.analysis_root(analysis.id) / "output" / "viz"
    assert {path.name for path in public_viz.iterdir()} == {
        "cam_01_original.mp4",
        "cam_02_original.mp4",
        "cam_03_original.mp4",
        "cam_04_original.mp4",
        "phases.mp4",
    }


def test_late_cancel_after_success_becomes_canceled(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'late-cancel.db'}",
        runtime_root=tmp_path / "runtime",
        model_root=tmp_path / "models",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=False,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    analysis = Analysis(title="late cancel", input_manifest_json="{}")
    analysis_id = analysis.id
    app.state.storage.prepare(analysis_id)

    async def engine_finishes_as_cancel_is_committed(application, detached):
        with Session(application.state.engine) as session:
            running = session.get(Analysis, detached.id)
            running.status = "cancel_requested"
            session.add(running)
            session.commit()

    monkeypatch.setattr("app.services.worker._run_subprocess", engine_finishes_as_cancel_is_committed)

    with TestClient(app):
        with Session(app.state.engine) as session:
            session.add(analysis)
            session.commit()

        asyncio.run(run_analysis(app, analysis_id))

        with Session(app.state.engine) as session:
            finished = session.get(Analysis, analysis_id)
        assert finished.status == "canceled"
        assert finished.completed_at is not None


def test_cancel_cannot_be_overwritten_by_stale_stage_update(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'stage-cancel-race.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    analysis = Analysis(title="stage cancel race", input_manifest_json="{}")
    analysis_id = analysis.id
    worker_has_read = threading.Event()
    release_worker = threading.Event()
    cancel_has_lock = threading.Event()
    cancel_committed = threading.Event()
    thread_errors: list[BaseException] = []
    original_transition = transition_status

    def pause_stage_after_read(current, target):
        if target == AnalysisStatus.registering:
            worker_has_read.set()
            assert release_worker.wait(timeout=2)
        return original_transition(current, target)

    def run_stage():
        try:
            _set_stage(app, analysis_id, AnalysisStatus.registering)
        except BaseException as error:
            thread_errors.append(error)

    def run_cancel():
        try:
            with Session(app.state.engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                cancel_has_lock.set()
                current = session.get(Analysis, analysis_id)
                current_status = AnalysisStatus(current.status)
                target = (
                    AnalysisStatus.cancel_requested
                    if current_status in ACTIVE_STATUSES
                    else AnalysisStatus.canceled
                )
                current.status = original_transition(current_status, target).value
                session.add(current)
                session.commit()
                cancel_committed.set()
        except BaseException as error:
            thread_errors.append(error)

    monkeypatch.setattr("app.services.worker.transition_status", pause_stage_after_read)

    with TestClient(app):
        with Session(app.state.engine) as session:
            session.add(analysis)
            session.commit()

        stage_thread = threading.Thread(target=run_stage)
        cancel_thread = threading.Thread(target=run_cancel)
        stage_thread.start()
        assert worker_has_read.wait(timeout=2)
        cancel_thread.start()

        if cancel_has_lock.wait(timeout=0.2):
            assert cancel_committed.wait(timeout=2)
        release_worker.set()
        stage_thread.join(timeout=2)
        cancel_thread.join(timeout=2)

        assert not stage_thread.is_alive()
        assert not cancel_thread.is_alive()
        assert thread_errors == []
        with Session(app.state.engine) as session:
            finished = session.get(Analysis, analysis_id)
        assert finished.status in {"cancel_requested", "canceled"}


@pytest.mark.skipif(os.name != "posix", reason="Product deployment uses POSIX process groups")
def test_engine_cancellation_terminates_descendant_process_group():
    async def scenario() -> int:
        script = (
            "import subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "print(child.pid, flush=True); time.sleep(60)"
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None
        child_pid = int((await process.stdout.readline()).decode().strip())
        await _terminate_process_group(process, grace_seconds=0.2)
        return child_pid

    child_pid = asyncio.run(scenario())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("engine descendant survived process-group cancellation")


@pytest.mark.skipif(os.name != "posix", reason="Product deployment uses POSIX process groups")
def test_subprocess_finally_cleans_group_when_status_poll_raises(tmp_path: Path, monkeypatch):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'cleanup.db'}",
        runtime_root=tmp_path / "runtime",
        model_root=tmp_path / "models",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    pid_file = tmp_path / "child.pid"
    original_create = asyncio.create_subprocess_exec

    async def fake_create(*_args, **_kwargs):
        script = (
            "import pathlib,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep(60)"
        )
        process = await original_create(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        for _ in range(100):
            if pid_file.is_file():
                return process
            await asyncio.sleep(0.01)
        pytest.fail("synthetic engine did not start")

    def broken_poll(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr("app.services.worker._cancel_requested", broken_poll)
    analysis = Analysis(title="cleanup", input_manifest_json="{}")
    app.state.storage.prepare(analysis.id)

    with TestClient(app):
        with pytest.raises(RuntimeError, match="database unavailable"):
            asyncio.run(_run_subprocess(app, analysis))

    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("engine descendant survived exceptional cleanup")
