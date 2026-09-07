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
from app.services.worker import STAGE_PROGRESS, _run_subprocess, _set_stage, _simulate, _terminate_process_group, run_analysis


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
            owner_id=1,
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
        owner_id=1,
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
    analysis = Analysis(title="late cancel", input_manifest_json="{}", owner_id=1)
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
    analysis = Analysis(title="stage cancel race", input_manifest_json="{}", owner_id=1)
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
    analysis = Analysis(title="cleanup", input_manifest_json="{}", owner_id=1)
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


@pytest.fixture
def registration_worker(tmp_path):
    """Real SQLite and worker lifecycle; only the external research child is replaced."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'registration-worker.db'}",
        runtime_root=tmp_path / 'runtime', sample_root=tmp_path / 'samples',
        model_root=tmp_path / 'models', worker_enabled=False, analyst_worker_enabled=False,
        auto_create_schema=True, simulation_mode=False, admin_password='correct-password',
        jwt_secret_key='test-secret-with-at-least-thirty-two-characters',
    )
    app = create_app(settings=settings)
    with TestClient(app):
        task = Analysis(title='registration test', owner_id=1, input_manifest_json='{}', expected_persons=3)
        root = app.state.storage.prepare(task.id)
        with Session(app.state.engine) as session:
            session.add(task)
            session.commit()
            task_id = task.id
        yield app, task_id, root


def replace_research_child(monkeypatch, script):
    original_create = asyncio.create_subprocess_exec

    async def spawn(*_args, **kwargs):
        return await original_create(sys.executable, '-c', script, **kwargs)

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)


def diagnostic_child(root, payload):
    return (
        'import pathlib,sys; '
        f'path=pathlib.Path({str(root / "logs" / "registration_error.json")!r}); '
        'path.parent.mkdir(parents=True,exist_ok=True); '
        f'path.write_bytes({payload!r}); '
        'print("private raw log /home/private/video.mp4 stu_03",flush=True); sys.exit(2)'
    )


@pytest.mark.parametrize('code', [
    'registration_count_mismatch', 'registration_quality_failed', 'registration_config_required',
])
def test_registration_diagnostic_is_allowlisted_and_safe(registration_worker, monkeypatch, code):
    app, task_id, root = registration_worker
    payload = json.dumps({'code': code, 'message': 'PRIVATE /home/private/video.mp4 stu_03',
                          'expected_persons': 3, 'detected_persons': 7,
                          'student_id': 'stu_03', 'log_path': '/home/private/secret.log'}).encode()
    replace_research_child(monkeypatch, diagnostic_child(root, payload))

    asyncio.run(run_analysis(app, task_id))

    with Session(app.state.engine) as session:
        failed = session.get(Analysis, task_id)
        assert failed.status == 'failed'
        assert failed.error_code == code
        assert failed.stage_message == '注册失败'
        assert failed.progress == STAGE_PROGRESS[AnalysisStatus.registering]
        assert failed.completed_at is not None
        public_error = failed.error_message + failed.stage_message
        assert all(private not in public_error for private in ('PRIVATE', '/home/', 'stu_03', 'secret.log'))
        if code == 'registration_count_mismatch':
            assert '预期 3 人' in failed.error_message
            assert '检测到 7 人' in failed.error_message


@pytest.mark.parametrize('payload', [
    b'{broken', b'[]', b'null', b'"text"', b'\xff',
    b'{"code":"arbitrary_error","message":"/home/private"}',
    b'{"code":["registration_count_mismatch"]}',
    b'{"code":"registration_count_mismatch","message":"' + b'x' * 5000 + b'"}',
])
def test_malformed_registration_diagnostic_falls_back_without_raw_details(registration_worker, monkeypatch, payload):
    app, task_id, root = registration_worker
    replace_research_child(monkeypatch, diagnostic_child(root, payload))

    asyncio.run(run_analysis(app, task_id))

    with Session(app.state.engine) as session:
        failed = session.get(Analysis, task_id)
        assert failed.status == 'failed'
        assert failed.error_code == 'ENGINE_FAILED'
        assert failed.stage_message == '分析失败'
        assert '/home/' not in failed.error_message
        assert 'raw log' not in failed.error_message


@pytest.mark.parametrize('detected', [True, -1, 2.5, '2', '/home/private/video.mp4', 10**30, None])
def test_registration_diagnostic_omits_invalid_counts(registration_worker, monkeypatch, detected):
    app, task_id, root = registration_worker
    payload = json.dumps({'code': 'registration_count_mismatch', 'expected_persons': False,
                          'detected_persons': detected}).encode()
    replace_research_child(monkeypatch, diagnostic_child(root, payload))

    asyncio.run(run_analysis(app, task_id))

    with Session(app.state.engine) as session:
        failed = session.get(Analysis, task_id)
        assert failed.error_code == 'registration_count_mismatch'
        # The persisted task configuration supplies the expected count when diagnostics omit it.
        assert '预期 3 人' in failed.error_message
        assert '检测到' not in failed.error_message
        assert '/home/' not in failed.error_message


def test_stale_registration_diagnostic_is_removed_before_new_child(registration_worker, monkeypatch):
    app, task_id, root = registration_worker
    diagnostic = root / 'logs' / 'registration_error.json'
    diagnostic.parent.mkdir(parents=True, exist_ok=True)
    diagnostic.write_text(json.dumps({'code': 'registration_count_mismatch', 'detected_persons': 2}))
    replace_research_child(monkeypatch, 'import sys; print("unrelated child failure",flush=True); sys.exit(2)')

    asyncio.run(run_analysis(app, task_id))

    assert not diagnostic.exists()
    with Session(app.state.engine) as session:
        assert session.get(Analysis, task_id).error_code == 'ENGINE_FAILED'


def test_unknown_engine_failure_keeps_raw_paths_only_in_server_logs(registration_worker, monkeypatch):
    app, task_id, root = registration_worker
    private = 'Traceback: /home/private/runtime/video.mp4 stu_03 /Users/operator/secret.json'
    replace_research_child(monkeypatch, f'import sys; print({private!r},flush=True); sys.exit(2)')

    asyncio.run(run_analysis(app, task_id))

    with Session(app.state.engine) as session:
        failed = session.get(Analysis, task_id)
        assert failed.error_code == 'ENGINE_FAILED'
        assert failed.stage_message == '分析失败'
        assert failed.error_message == '科研引擎执行失败，详情已写入本地任务日志。'
        assert all(value not in failed.error_message for value in ('Traceback', '/home/', '/Users/', 'stu_03'))
    assert private in (root / 'logs' / 'engine.log').read_text()
    assert private in (root / 'logs' / 'worker.log').read_text()


def test_registration_diagnostic_symlink_is_not_read(registration_worker, monkeypatch, tmp_path):
    app, task_id, root = registration_worker
    private = tmp_path / 'private.json'
    private.write_text(json.dumps({'code': 'registration_count_mismatch', 'detected_persons': 2}))
    script = (
        'import pathlib,sys; '
        f'path=pathlib.Path({str(root / "logs" / "registration_error.json")!r}); '
        'path.parent.mkdir(parents=True,exist_ok=True); '
        f'path.symlink_to({str(private)!r}); sys.exit(2)'
    )
    replace_research_child(monkeypatch, script)

    asyncio.run(run_analysis(app, task_id))

    with Session(app.state.engine) as session:
        assert session.get(Analysis, task_id).error_code == 'ENGINE_FAILED'
    assert private.is_file()


@pytest.mark.skipif(os.name != 'posix', reason='Deployment uses POSIX inherited file locks')
def test_worker_subprocess_inherits_gpu_lock_after_parent_closes_descriptor(registration_worker, monkeypatch, tmp_path):
    import fcntl
    app, task_id, root = registration_worker
    lock = tmp_path / 'gpu.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    app.state.video_worker_lock_fds = (fd,)
    ready, release = tmp_path / 'ready', tmp_path / 'release'
    script = '\n'.join([
        'import os,pathlib,time', f'os.fstat({fd})',
        f'pathlib.Path({str(ready)!r}).write_text("inherited")',
        f'while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)',
        f'output=pathlib.Path({str(root / "output")!r})',
        'output.mkdir(parents=True,exist_ok=True)',
        'for name in ("report.json","summary.json","media_manifest.json"): (output/name).write_text("{}")',
    ])
    original_create = asyncio.create_subprocess_exec
    parent_closed = False
    lock_blocked = False

    async def spawn(*_args, **kwargs):
        nonlocal parent_closed, lock_blocked
        child = await original_create(sys.executable, '-c', script, **kwargs)
        try:
            for _ in range(200):
                if ready.exists() or child.returncode is not None:
                    break
                await asyncio.sleep(0.01)
            if ready.exists():
                os.close(fd)
                parent_closed = True
                contender = os.open(lock, os.O_RDWR)
                try:
                    try:
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        lock_blocked = True
                finally:
                    os.close(contender)
        finally:
            release.write_text('continue')
        return child

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    try:
        asyncio.run(run_analysis(app, task_id))
        assert ready.exists(), 'Worker child did not inherit the GPU lock descriptor'
        assert lock_blocked, 'Inherited child must keep the lock after the parent closes its copy'
        with Session(app.state.engine) as session:
            assert session.get(Analysis, task_id).status == 'completed'
    finally:
        if not parent_closed:
            os.close(fd)
