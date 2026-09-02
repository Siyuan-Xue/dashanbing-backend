import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis
from app.services.worker import _run_subprocess, _terminate_process_group, run_analysis


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
