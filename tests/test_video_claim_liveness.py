"""Video queue survives SQLite contention without blocking request cleanup."""
import asyncio
import threading

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis, User
from app.admin_models import AdminLease
from app.services import admin_scheduling, worker
from tests.test_admin_auth import admin_app


@pytest.mark.parametrize('cancel_claim', [False, True])
def test_lifespan_video_worker_survives_real_sqlite_busy_timeout(tmp_path, monkeypatch, cancel_claim):
    settings = AppSettings(_env_file=None, database_url=f'sqlite:///{tmp_path / "video.db"}',
        runtime_root=tmp_path / 'runtime', sample_root=tmp_path / 'samples',
        worker_enabled=True, analyst_worker_enabled=False, simulation_mode=True,
        auto_create_schema=True, admin_password='isolated-admin-password',
        jwt_secret_key='isolated-test-secret-longer-than-thirty-two-characters')
    app = create_app(settings=settings)
    # No GPU model is needed to exercise the actual lifespan and queue/worker.
    monkeypatch.setattr(app.state.readiness, 'preflight', lambda: {'ready': True})
    armed, claim_started, busy_seen, loop_progress = (threading.Event() for _ in range(4))
    progress_before_timeout, errors = [], []
    row = Analysis(owner_id=2, title='after writer contention', status='queued',
                   mode='quick', source_type='upload', input_manifest_json='{}')
    analysis_id = row.id
    claim_video, run_analysis = admin_scheduling.claim_video, worker.run_analysis

    async def scenario():
        loop = asyncio.get_running_loop()
        initial_claim_done, completed = asyncio.Event(), asyncio.Event()
        stopping = []

        def cancel_while_sqlite_waits():
            if not stopping:
                stopping.append(asyncio.create_task(app.state.supervisor.stop()))

        def observed_claim(app):
            result = claim_video(app)
            if not armed.is_set():
                loop.call_soon_threadsafe(initial_claim_done.set)
            return result

        async def observed_run(app, analysis_id):
            await run_analysis(app, analysis_id)  # Real worker in its supported simulation mode.
            completed.set()

        @event.listens_for(app.state.engine, 'before_cursor_execute')
        def observe_claim(_connection, _cursor, statement, *_args):
            if armed.is_set() and statement == 'BEGIN IMMEDIATE':
                claim_started.set()
                loop.call_soon_threadsafe(loop_progress.set)
                if cancel_claim:
                    loop.call_soon_threadsafe(cancel_while_sqlite_waits)

        @event.listens_for(app.state.engine, 'handle_error')
        def observe_busy(context):
            if 'database is locked' in str(context.original_exception):
                progress_before_timeout.append(loop_progress.is_set())
                errors.append(type(context.sqlalchemy_exception).__name__)
                busy_seen.set()

        def hold_writer_until_claim_times_out():
            with Session(app.state.engine) as session:
                session.connection().exec_driver_sql('BEGIN IMMEDIATE')
                session.add(User(id=2, username='normal', hashed_password='unused'))
                session.flush()
                session.add(row); session.flush()
                armed.set()
                assert claim_started.wait(5), 'Video worker never attempted a claim'
                assert busy_seen.wait(8), 'Expected the real 5000ms SQLite busy boundary'
                session.commit()  # A runnable task becomes visible after contention ends.

        monkeypatch.setattr(admin_scheduling, 'claim_video', observed_claim)
        monkeypatch.setattr(worker, 'run_analysis', observed_run)
        died = False
        stopped_correctly = False
        try:
            async with app.router.lifespan_context(app):
                supervisor = app.state.supervisor
                assert app.state.settings.worker_enabled and app.state.gpu_queue_ready
                await asyncio.wait_for(initial_claim_done.wait(), 5)
                await asyncio.to_thread(hold_writer_until_claim_times_out)
                died = supervisor._task.done()
                if cancel_claim:
                    await asyncio.wait_for(asyncio.shield(stopping[0]), 5)
                    stopped_correctly = supervisor._task.cancelled()
                elif not died:
                    await asyncio.wait_for(completed.wait(), 5)
        except OperationalError:
            # Original code also rethrows its dead worker's claim error on shutdown.
            assert died
        return died, stopped_correctly

    died, stopped_correctly = asyncio.run(scenario())
    if cancel_claim:
        assert stopped_correctly, 'SQLite claim error replaced video shutdown cancellation'
    else:
        assert not died, 'SQLite busy exception permanently terminated the video supervisor'
    assert errors == ['OperationalError']
    assert progress_before_timeout == [True], 'Video claim blocked the event loop while SQLite waited'
    with Session(app.state.engine) as session:
        assert session.get(Analysis, analysis_id).status == ('queued' if cancel_claim else 'completed')
        assert session.get(AdminLease, ('video', analysis_id)) is None
    assert not getattr(app.state.engine, '_admin_lease_guards', {})
    assert not getattr(app.state.engine, '_video_worker_locks', {})


@pytest.mark.parametrize('paused_stage', ['claim', 'cleanup'])
def test_video_repeated_stop_cancellation_waits_for_both_kernel_locks(admin_app, monkeypatch, paused_stage):
    import fcntl
    from sqlmodel import select
    from app.admin_models import AdminAttempt
    from app.services.supervisor import AnalysisSupervisor
    from app.services.admin_leases import guard_alive

    app, _ = admin_app
    row = Analysis(owner_id=2, title='cancel before worker', status='queued', input_manifest_json='{}')
    with Session(app.state.engine) as session:
        session.add(row); session.commit(); session.refresh(row)
    allow_claim, allow_finish, finished = (threading.Event() for _ in range(3))
    leases, ran = [], []
    claim_video, release_lease = admin_scheduling.claim_video, admin_scheduling.release_lease

    async def scenario():
        loop = asyncio.get_running_loop()
        entered, paused = asyncio.Event(), asyncio.Event()

        def pause():
            loop.call_soon_threadsafe(paused.set)
            try:
                assert allow_finish.wait(10)
            finally:
                finished.set()

        def observed_claim(app):
            loop.call_soon_threadsafe(entered.set)
            assert allow_claim.wait(10)
            job_id = claim_video(app)
            with Session(app.state.engine) as session:
                leases.append(session.get(AdminLease, ('video', job_id)))
            if paused_stage == 'claim':
                pause()
            return job_id

        def observed_release(*args):
            if paused_stage == 'cleanup':
                pause()
            release_lease(*args)

        async def forbidden_run(*args):
            ran.append('started after stop')
            raise AssertionError('Video execution must not start during cancellation')

        monkeypatch.setattr(admin_scheduling, 'claim_video', observed_claim)
        monkeypatch.setattr(admin_scheduling, 'release_lease', observed_release)
        monkeypatch.setattr(worker, 'run_analysis', forbidden_run)
        supervisor = AnalysisSupervisor(app)
        supervisor._last_retention_run = float('inf')  # Retention is unrelated to this claim boundary.
        supervisor._task = asyncio.create_task(supervisor._loop())
        stopping = None
        try:
            await asyncio.wait_for(entered.wait(), 5)
            stopping = asyncio.create_task(supervisor.stop())
            await asyncio.sleep(0)
            allow_claim.set()
            await asyncio.wait_for(paused.wait(), 5)
            assert guard_alive(app.state.engine, leases[0]) is True
            stopping.cancel()
            for _ in range(3):
                await asyncio.sleep(0)
            assert not stopping.done() and not supervisor._task.done()
            allow_finish.set()
            done, _ = await asyncio.wait({stopping}, timeout=5)
            assert done, 'Video stop did not finish after its claim cleanup'
            await stopping
            assert supervisor._task.cancelled()
        finally:
            allow_claim.set(); allow_finish.set()
            assert await asyncio.to_thread(finished.wait, 5)
            supervisor._task.cancel()
            await asyncio.gather(supervisor._task, return_exceptions=True)
            if stopping is not None:
                await asyncio.gather(stopping, return_exceptions=True)

    try:
        asyncio.run(scenario())
        assert not ran and len(leases) == 1
        with Session(app.state.engine) as session:
            assert session.get(Analysis, row.id).status == 'queued'
            assert session.get(AdminLease, ('video', row.id)) is None
            assert session.exec(select(AdminAttempt)).all() == []
        assert guard_alive(app.state.engine, leases[0]) is False
        assert not getattr(app.state.engine, '_admin_lease_guards', {})
        assert not getattr(app.state.engine, '_video_worker_locks', {})
        with (app.state.settings.runtime_root / 'tmp' / 'video-worker.lock').open('rb') as mutex:
            fcntl.flock(mutex.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        release_lease(app.state.engine, 'video', row.id)
