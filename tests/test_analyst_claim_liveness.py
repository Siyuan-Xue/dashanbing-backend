"""Real SQLite/request cleanup must progress while the empty AI pool claims work."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_admin_auth import admin_app


def _request_rollback_probe(root, video_enabled=False):
    import asyncio
    import threading
    import time

    import httpx
    from fastapi import HTTPException
    from pydantic import SecretStr
    from sqlalchemy import event
    from sqlmodel import Session, select

    from app.config import AppSettings
    AppSettings.model_config['env_file'] = None
    from app.main import create_app
    from app.api.routes import tasks as routes
    from app.models import Analysis, TaskInput, User
    from app.security import create_access_token
    from app.services.admin_presets import enqueue_preset
    from app.services import admin_scheduling
    from app.analyst_schemas import AnalystFacts
    from app.services.glm import GlmJsonResult

    root = Path(root)
    settings = AppSettings(
        _env_file=None, database_url=f'sqlite:///{root / "api.db"}',
        runtime_root=root / 'runtime', sample_root=root / 'samples',
        worker_enabled=video_enabled, analyst_worker_enabled=True, auto_create_schema=True,
        simulation_mode=True, min_free_storage_gb=0,
        admin_password='isolated-admin-password',
        jwt_secret_key='isolated-test-secret-longer-than-thirty-two-characters',
        glm_api_key=SecretStr('synthetic-provider-key'),
    )
    inputs = settings.sample_root / 'test_data_v3'
    (inputs / 'sync').mkdir(parents=True)
    for name in ('0-2.mkv', '4-1.mkv', '4-2.mkv', '4-3.mkv', '4-4.mkv'):
        (inputs / name).write_bytes(b'isolated-video-placeholder')
    # Real preset sync validation fails after the route has flushed its task,
    # before video inspection. No media/model/provider work can explain a stall.
    (inputs / 'sync' / 'group_04.json').write_text('{"anchor_camera":"cam_02"}')
    app = create_app(settings=settings)
    app.state.readiness.require_ready = lambda: None  # Isolate the GPU gate only.
    if video_enabled:
        app.state.readiness.preflight = lambda: {'ready': True}

    class Provider:
        async def complete_json(self, *args, **kwargs):
            return GlmJsonResult(data={'summary': 'isolated report'}, usage={})
    app.state.glm_client = Provider()
    armed, claim_started = threading.Event(), threading.Event()
    initial_claims_done = threading.Event()
    initial_claims = []
    claim_ai = admin_scheduling.claim_ai

    def observed_claim(app):
        result = claim_ai(app)
        if not armed.is_set():
            initial_claims.append(result)
            if len(initial_claims) == 8:
                initial_claims_done.set()
        return result

    admin_scheduling.claim_ai = observed_claim
    timeline, lock_errors, route_connection = [], [], []
    started = time.monotonic()

    def record(name):
        timeline.append({'event': name, 'seconds': round(time.monotonic() - started, 3),
                         'thread': threading.current_thread().name})

    @event.listens_for(app.state.engine, 'before_cursor_execute')
    def observe_begin(connection, _cursor, statement, *_args):
        if statement.startswith('INSERT INTO analysis '):
            route_connection[:] = [connection]
        if armed.is_set() and statement == 'BEGIN IMMEDIATE':
            record('claim_begin')
            claim_started.set()

    @event.listens_for(app.state.engine, 'handle_error')
    def observe_error(context):
        if 'database is locked' in str(context.original_exception):
            lock_errors.append('database is locked')
            record('busy_timeout')

    @event.listens_for(app.state.engine, 'rollback')
    def observe_rollback(connection):
        if route_connection and connection is route_connection[0]:
            record('request_rollback')

    prepare = routes.prepare_preset_config

    def failed_preset(*args, **kwargs):
        record('request_holds_writer')
        armed.set()
        assert claim_started.wait(5), 'The actual lifespan workers did not attempt a claim'
        try:
            return prepare(*args, **kwargs)
        except HTTPException as error:
            assert error.detail['code'] == 'sync_invalid'
            record('request_raised')
            raise

    routes.prepare_preset_config = failed_preset

    async def scenario():
        async with app.router.lifespan_context(app):
            assert len(app.state.analyst_supervisor.tasks) == 9  # Eight claims plus reconciliation.
            assert await asyncio.to_thread(initial_claims_done.wait, 5)
            with Session(app.state.engine) as session:
                session.add(User(id=2, username='normal', hashed_password='unused'))
                session.commit()
            token = create_access_token('normal', secret_key=settings.jwt_secret_key, role='user')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                        headers={'Authorization': 'Bearer ' + token}) as client:
                pending = asyncio.create_task(client.post('/api/v1/tasks/from-preset',
                    json={'preset_id': 'quick-demo', 'mode': 'full'}))
                assert await asyncio.to_thread(armed.wait, 5)
                # A separate read request must remain serviceable, and the
                # failed writer must reach the real dependency Session.close.
                read = await client.get('/api/v1/account/limits')
                response = await pending
                assert response.status_code == 422, response.text
                assert read.status_code == 200
                assert response.json()['detail']['code'] == 'sync_invalid'
                with Session(app.state.engine) as session:
                    assert session.exec(select(Analysis)).all() == []
                    assert session.exec(select(TaskInput)).all() == []
                preset_id = await asyncio.to_thread(enqueue_preset, app, 'quick-demo',
                    AnalystFacts().model_dump(), locale='zh', style='coach')
                assert len(preset_id) == 64
                if video_enabled:
                    assert not app.state.supervisor._task.done()
        assert any(item['event'] == 'request_rollback' for item in timeline)
        print(json.dumps({'timeline': timeline, 'busy_timeouts': len(lock_errors)}), flush=True)
        names = [item['event'] for item in timeline]
        assert names.index('request_raised') < names.index('request_rollback')
        # Keep the real five-second SQLite busy boundary. The failure is the
        # dependency rollback waiting for claims to time out, not a latency SLA.
        if 'busy_timeout' in names:
            assert names.index('request_rollback') < names.index('busy_timeout'), (
                'Empty AI claims prevented request rollback until SQLite busy-timeout')

    asyncio.run(scenario())


@pytest.mark.parametrize('video_enabled', [False, True])
def test_failed_preset_rolls_back_with_real_lifespan_and_eight_empty_ai_workers(tmp_path, video_enabled):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('BASKETBALL_') and key != 'GLM_API_KEY'}
    result = subprocess.run(
        [sys.executable, '-c',
         'import runpy,sys; from app.config import AppSettings; AppSettings.model_config["env_file"]=None; '
         'runpy.run_path(sys.argv[1])["_request_rollback_probe"](sys.argv[2], sys.argv[3] == "True")',
         str(Path(__file__).resolve()), str(tmp_path), str(video_enabled)],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')


def test_cancel_during_claim_releases_persisted_and_kernel_lease(admin_app, monkeypatch):
    import asyncio
    import threading
    from types import SimpleNamespace

    from sqlmodel import Session, select
    from app.admin_models import AdminAttempt, AdminLease
    from app.analyst_models import AnalystJob, AnalystReport
    from app.services.analyst import AnalystSupervisor
    from app.services import admin_scheduling
    from tests.test_admin_recovery import seed_job

    app, _ = admin_app
    row = seed_job(app, 'report')
    started, finished = threading.Event(), threading.Event()
    calls = []
    claimed_leases = []
    claim_ai = admin_scheduling.claim_ai

    def observed_claim(app):
        started.set()
        try:
            job_id = claim_ai(app)
            if job_id:
                with Session(app.state.engine) as session:
                    lease = session.get(AdminLease, ('ai', job_id))
                    assert admin_scheduling.lease_alive(lease)
                    claimed_leases.append(lease)
            return job_id
        finally:
            finished.set()

    monkeypatch.setattr(admin_scheduling, 'claim_ai', observed_claim)

    class Provider:
        async def complete_json(self, *_args, **kwargs):
            calls.append(kwargs['request_id'])
            return SimpleNamespace(data=dict(summary='complete', highlights=[], players=[],
                                             comparison=None, suggestions=[]), usage={})

    app.state.glm_client = Provider()

    async def scenario():
        supervisor = AnalystSupervisor(app)
        with Session(app.state.engine) as writer:
            writer.connection().exec_driver_sql('BEGIN IMMEDIATE')
            pending = asyncio.create_task(supervisor.run_once())
            try:
                assert await asyncio.to_thread(started.wait, 2)
                pending.cancel()
            finally:
                writer.rollback()
            with pytest.raises(asyncio.CancelledError):
                await pending
        assert await asyncio.to_thread(finished.wait, 2)
        with Session(app.state.engine) as session:
            current = session.get(AnalystJob, row.id)
            assert current.request_id == row.request_id and current.attempts == 0
            assert current.status == 'running'  # Existing bounded restart recovery owns requeueing.
            assert session.get(AdminLease, ('ai', row.id)) is None
            assert session.exec(select(AdminAttempt)).all() == []
            assert calls == []
            assert not getattr(app.state.engine, '_admin_lease_guards', {})
            from app.services.admin_leases import guard_alive
            assert len(claimed_leases) == 1
            assert guard_alive(app.state.engine, claimed_leases[0]) is False
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            admin_scheduling.recover_unleased_jobs(session)
            session.commit()
            session.refresh(current)
            assert current.status == 'queued'
        assert await supervisor.run_once() is True

    asyncio.run(scenario())
    with Session(app.state.engine) as session:
        current = session.get(AnalystJob, row.id)
        assert current.status == 'completed' and current.attempts == 1
        assert session.get(AnalystReport, row.report_id).status == 'completed'
        assert len(session.exec(select(AdminAttempt)).all()) == 1
        assert session.get(AdminLease, ('ai', row.id)) is None
        assert not getattr(app.state.engine, '_admin_lease_guards', {})
    assert calls == [row.request_id]


@pytest.mark.parametrize('failure_stage', ['claim', 'mark_interrupted'])
def test_stop_preserves_cancellation_when_claim_or_cleanup_fails(admin_app, monkeypatch, caplog, failure_stage):
    import asyncio
    import logging
    import threading

    from sqlalchemy.exc import OperationalError
    from sqlmodel import Session, select
    from app.admin_models import AdminAttempt, AdminLease
    from app.analyst_models import AnalystJob
    from app.services.analyst import AnalystSupervisor
    from app.services import admin_scheduling
    from app.services.admin_leases import guard_alive
    from tests.test_admin_recovery import seed_job

    # Earlier Alembic fileConfig tests disable already-created loggers. Restore
    # this observer locally; monkeypatch/caplog restore the prior state afterward.
    monkeypatch.setattr(logging.getLogger('app.services.analyst'), 'disabled', False)
    caplog.set_level(logging.ERROR, logger='app.services.analyst')
    app, _ = admin_app
    row = seed_job(app, 'report')
    allow_claim = threading.Event()
    claim_calls, claim_errors, claimed_leases, provider_calls = [], [], [], []
    claim_ai, mark_interrupted = admin_scheduling.claim_ai, admin_scheduling.mark_interrupted

    class Provider:
        async def complete_json(self, *_args, **_kwargs):
            provider_calls.append('called after cancellation')
            raise AssertionError('Provider must not start during shutdown')
    app.state.glm_client = Provider()

    async def scenario():
        loop = asyncio.get_running_loop()
        entered, resumed, failed = asyncio.Event(), asyncio.Event(), asyncio.Event()

        def observed_claim(app):
            claim_calls.append('claim')
            loop.call_soon_threadsafe(entered.set if len(claim_calls) == 1 else resumed.set)
            assert allow_claim.wait(10)
            try:
                job_id = claim_ai(app)
            except OperationalError as error:
                claim_errors.append(error)
                loop.call_soon_threadsafe(failed.set)
                raise
            if job_id:
                with Session(app.state.engine) as session:
                    claimed_leases.append(session.get(AdminLease, ('ai', job_id)))
            return job_id

        def failing_mark(*args):
            mark_interrupted(*args)
            loop.call_soon_threadsafe(failed.set)
            raise RuntimeError('synthetic interruption bookkeeping failure')

        monkeypatch.setattr(admin_scheduling, 'claim_ai', observed_claim)
        if failure_stage == 'mark_interrupted':
            monkeypatch.setattr(admin_scheduling, 'mark_interrupted', failing_mark)
        supervisor = AnalystSupervisor(app)
        with Session(app.state.engine) as writer:
            if failure_stage == 'claim':
                # Use the real production 5000ms busy timeout to make claim fail.
                writer.connection().exec_driver_sql('BEGIN IMMEDIATE')
            worker = asyncio.create_task(supervisor._loop())
            supervisor.tasks = [worker]
            stopping = resumed_waiter = None
            try:
                await asyncio.wait_for(entered.wait(), 5)
                stopping = asyncio.create_task(supervisor.stop())
                await asyncio.sleep(0)  # stop sends the first cancellation.
                allow_claim.set()
                await asyncio.wait_for(failed.wait(), 8)
                writer.rollback()
                resumed_waiter = asyncio.create_task(resumed.wait())
                await asyncio.wait({stopping, resumed_waiter}, timeout=5,
                                   return_when=asyncio.FIRST_COMPLETED)
                assert stopping.done(), 'stop did not terminate after a canceled claim/cleanup failed'
                await stopping
                assert worker.cancelled()
                assert not resumed.is_set(), 'Canceled worker resumed claiming after stop'
            finally:
                allow_claim.set()
                writer.rollback()
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                if stopping is not None:
                    await stopping
                if resumed_waiter is not None:
                    resumed_waiter.cancel()
                    await asyncio.gather(resumed_waiter, return_exceptions=True)

    try:
        asyncio.run(scenario())
        assert claim_calls == ['claim'] and provider_calls == []
        with Session(app.state.engine) as session:
            current = session.get(AnalystJob, row.id)
            assert current.request_id == row.request_id and current.attempts == 0
            assert session.get(AdminLease, ('ai', row.id)) is None
            assert session.exec(select(AdminAttempt)).all() == []
        assert not getattr(app.state.engine, '_admin_lease_guards', {})
        if failure_stage == 'claim':
            assert len(claim_errors) == 1 and 'database is locked' in str(claim_errors[0])
        else:
            assert len(claimed_leases) == 1
            assert guard_alive(app.state.engine, claimed_leases[0]) is False
        # Cleanup errors remain visible, but must never become a normal loop retry.
        assert any(record.exc_info for record in caplog.records)
    finally:
        admin_scheduling.release_lease(app.state.engine, 'ai', row.id)


@pytest.mark.parametrize('paused_stage', ['claim', 'cleanup'])
def test_canceling_stop_again_waits_for_claim_and_kernel_lease_cleanup(admin_app, monkeypatch, paused_stage):
    import asyncio
    import threading

    from sqlmodel import Session, select
    from app.admin_models import AdminAttempt, AdminLease
    from app.analyst_models import AnalystJob
    from app.services.analyst import AnalystSupervisor
    from app.services import admin_scheduling
    from app.services.admin_leases import guard_alive
    from tests.test_admin_recovery import seed_job

    app, _ = admin_app
    row = seed_job(app, 'report')
    allow_claim, allow_finish, thread_finished = threading.Event(), threading.Event(), threading.Event()
    claimed_leases, provider_calls = [], []
    claim_ai, mark_interrupted = admin_scheduling.claim_ai, admin_scheduling.mark_interrupted

    class Provider:
        async def complete_json(self, *_args, **_kwargs):
            provider_calls.append('called after cancellation')
            raise AssertionError('Provider must not start during shutdown')
    app.state.glm_client = Provider()

    async def scenario():
        loop = asyncio.get_running_loop()
        entered, paused = asyncio.Event(), asyncio.Event()

        def pause():
            loop.call_soon_threadsafe(paused.set)
            try:
                assert allow_finish.wait(10)
            finally:
                thread_finished.set()

        def observed_claim(app):
            loop.call_soon_threadsafe(entered.set)
            assert allow_claim.wait(10)
            job_id = claim_ai(app)
            with Session(app.state.engine) as session:
                claimed_leases.append(session.get(AdminLease, ('ai', job_id)))
            if paused_stage == 'claim':
                pause()  # Committed real lease, thread has not returned its ID.
            return job_id

        def observed_mark(*args):
            mark_interrupted(*args)
            if paused_stage == 'cleanup':
                pause()  # Cleanup still owns the kernel guard until release_lease.

        monkeypatch.setattr(admin_scheduling, 'claim_ai', observed_claim)
        monkeypatch.setattr(admin_scheduling, 'mark_interrupted', observed_mark)
        supervisor = AnalystSupervisor(app)
        worker = asyncio.create_task(supervisor._loop())
        supervisor.tasks = [worker]
        stopping = None
        try:
            await asyncio.wait_for(entered.wait(), 5)
            stopping = asyncio.create_task(supervisor.stop())
            await asyncio.sleep(0)
            allow_claim.set()
            await asyncio.wait_for(paused.wait(), 5)
            assert guard_alive(app.state.engine, claimed_leases[0]) is True
            stopping.cancel()  # Propagates the second cancel to the worker it awaits.
            # Drain ready cancellation callbacks; no wall-clock latency threshold.
            for _ in range(3):
                await asyncio.sleep(0)
            assert not stopping.done() and not worker.done(), 'stop returned before lease cleanup finished'
            allow_finish.set()
            done, _ = await asyncio.wait({stopping}, timeout=5)
            assert done, 'stop failed to terminate after cleanup finished'
            await stopping
            assert worker.cancelled()
        finally:
            allow_claim.set(); allow_finish.set()
            assert await asyncio.to_thread(thread_finished.wait, 5)
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            if stopping is not None:
                await asyncio.gather(stopping, return_exceptions=True)

    try:
        asyncio.run(scenario())
        with Session(app.state.engine) as session:
            current = session.get(AnalystJob, row.id)
            assert current.request_id == row.request_id and current.attempts == 0
            assert current.status == 'running'
            assert session.get(AdminLease, ('ai', row.id)) is None
            assert session.exec(select(AdminAttempt)).all() == []
        assert provider_calls == []
        assert not getattr(app.state.engine, '_admin_lease_guards', {})
        assert len(claimed_leases) == 1 and guard_alive(app.state.engine, claimed_leases[0]) is False
    finally:
        admin_scheduling.release_lease(app.state.engine, 'ai', row.id)
