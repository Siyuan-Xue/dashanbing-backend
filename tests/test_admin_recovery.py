"""Restart recovery keeps identities and actual-call accounting within finite limits."""
import asyncio
import os
import socket
from datetime import timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.admin_models import AdminAttempt, AdminJobControl, AdminLease, AdminPresetJob, AdminRepairDay
from app.analyst_models import AnalystConversation, AnalystJob, AnalystMessage, AnalystProviderState, AnalystReport
from app.analyst_schemas import AnalystFacts
from app.models import utc_now
from app.services.analyst import AnalystSupervisor, pack
from app.services.admin_presets import enqueue_preset, run_preset
from app.services.admin_scheduling import recover_dead_leases
from tests.test_admin_auth import admin_app


def seed_job(app, kind, *, attempts=0, status='queued', repair=False):
    payload = pack(dict(facts=AnalystFacts().model_dump(), memory={}, locale='zh', style='coach'))
    with Session(app.state.engine) as session:
        if kind == 'preset':
            row = AdminPresetJob(id=str(uuid4()), preset_id='quick-demo', payload_json=payload)
        else:
            if kind == 'report':
                target = AnalystReport(owner_id=2, cache_key=str(uuid4()), status=status)
            else:
                conversation = AnalystConversation(owner_id=2)
                session.add(conversation); session.flush()
                target = AnalystMessage(owner_id=2, conversation_id=conversation.id, role='assistant',
                                        status=status, content='incomplete', citations_json='["event-old"]')
            session.add(target); session.flush()
            row = AnalystJob(owner_id=2, kind=kind, request_id=str(uuid4()), payload_json=payload,
                             **{kind + '_id': target.id})
        row.attempts = attempts; row.status = status
        session.add(row); session.flush()
        pool_kind = 'preset' if kind == 'preset' else 'ai'
        if repair:
            session.add(AdminJobControl(kind=pool_kind, job_id=row.id, repair=True, admin_retries=1))
        session.commit(); session.refresh(row)
        return row


async def restart(app, monkeypatch):
    async def parked(self):
        await asyncio.Event().wait()
    monkeypatch.setattr(AnalystSupervisor, '_loop', parked)
    supervisor = AnalystSupervisor(app)
    await supervisor.start()
    await supervisor.stop()


@pytest.mark.parametrize('kind', ['report', 'message', 'preset'])
@pytest.mark.parametrize('repair', [False, True])
def test_cancellation_and_restart_never_reset_actual_attempt_limit(admin_app, monkeypatch, kind, repair):
    app, _ = admin_app
    if kind == 'preset':
        job_id = enqueue_preset(app, 'quick-demo', AnalystFacts().model_dump(), locale='zh', style='coach')
        if repair:
            with Session(app.state.engine) as session:
                session.add(AdminJobControl(kind='preset', job_id=job_id, repair=True, admin_retries=1))
                session.commit()
    else:
        job_id = seed_job(app, kind, repair=repair).id
    model = AdminPresetJob if kind == 'preset' else AnalystJob
    calls = []

    async def scenario():
        started = asyncio.Event()
        class Provider:
            async def complete_json(self, *_args, **kwargs):
                calls.append(kwargs['request_id']); started.set()
                await asyncio.Event().wait()

            async def stream(self, *_args, **kwargs):
                calls.append(kwargs['request_id'])
                yield SimpleNamespace(type='text', text='unfinished content')
                started.set()
                await asyncio.Event().wait()

        app.state.glm_client = Provider()
        for attempt in range(1, 2 if repair else 4):
            started.clear()
            running = asyncio.create_task(run_preset(app, job_id) if kind == 'preset' else AnalystSupervisor(app).run_once())
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
            finally:
                running.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await running
            with Session(app.state.engine) as session:
                row = session.get(model, job_id)
                assert row.attempts == attempt
                assert row.status == ('failed' if repair or attempt == 3 else 'running')
                assert session.get(AdminLease, ('preset' if kind == 'preset' else 'ai', job_id)) is None
            await restart(app, monkeypatch)
            with Session(app.state.engine) as session:
                row = session.get(model, job_id)
                assert row.status == ('failed' if repair or attempt == 3 else 'queued')
                if kind == 'message':
                    message = session.get(AnalystMessage, row.message_id)
                    assert 'unfinished' not in message.content
                    assert message.citations_json == '[]'
        assert await AnalystSupervisor(app).run_once() is False
        if kind == 'preset':
            assert await run_preset(app, job_id) is False

    asyncio.run(scenario())
    expected = 1 if repair else 3
    assert len(calls) == expected and len(set(calls)) == 1
    with Session(app.state.engine) as session:
        assert len(session.exec(select(model)).all()) == 1
        attempts = session.exec(select(AdminAttempt).where(AdminAttempt.job_id == job_id)).all()
        assert len(attempts) == expected and all(row.repair == repair for row in attempts)
        budget = session.get(AdminRepairDay, utc_now().date().isoformat())
        assert (budget.ai_used if budget else 0) == (1 if repair else 0)


@pytest.mark.parametrize('kind', ['report', 'message', 'preset'])
@pytest.mark.parametrize('attempts,repair,expected', [(1, False, 'queued'), (3, False, 'failed'), (1, True, 'failed')])
def test_dead_leases_use_bounded_recovery_and_preserve_provider_backoff(admin_app, monkeypatch, kind, attempts, repair, expected):
    app, _ = admin_app
    row = seed_job(app, kind, attempts=attempts, status='running', repair=repair)
    pool_kind = 'preset' if kind == 'preset' else 'ai'
    deadline = utc_now() + timedelta(minutes=5)
    # PID liveness is the sole external boundary mocked; every recovery write uses SQLite.
    monkeypatch.setattr('app.services.admin_scheduling.lease_alive', lambda lease: False)
    with Session(app.state.engine) as session:
        session.add(AdminLease(kind=pool_kind, job_id=row.id, pool='ai', pid=987654, hostname=socket.gethostname()))
        session.add(AnalystProviderState(provider='glm', available_at=deadline))
        session.commit()
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        recover_dead_leases(session); session.commit()
        current = session.get(type(row), row.id)
        assert current.status == expected
        assert current.attempts == attempts and current.payload_json == row.payload_json
        if expected == 'queued':
            assert current.available_at.replace(tzinfo=timezone.utc) >= deadline
        if kind != 'preset':
            assert current.request_id == row.request_id
            target = session.get(AnalystReport, row.report_id) if kind == 'report' else session.get(AnalystMessage, row.message_id)
            assert target.status == expected
            if kind == 'message':
                assert 'incomplete' not in target.content and target.citations_json == '[]'
        assert session.get(AdminLease, (pool_kind, row.id)) is None
        assert session.exec(select(AdminAttempt)).all() == []


@pytest.mark.parametrize('hostname', [socket.gethostname(), 'foreign-host'])
def test_recovery_skips_live_or_foreign_leases(admin_app, monkeypatch, hostname):
    app, _ = admin_app
    rows = [seed_job(app, kind, attempts=1, status='running') for kind in ('report', 'message', 'preset')]
    with Session(app.state.engine) as session:
        for row in rows:
            session.add(AdminLease(kind='preset' if isinstance(row, AdminPresetJob) else 'ai', job_id=row.id,
                                   pool='ai', pid=os.getpid(), hostname=hostname))
        session.commit()
    asyncio.run(restart(app, monkeypatch))
    with Session(app.state.engine) as session:
        assert len(session.exec(select(AdminLease)).all()) == 3
        for row in rows:
            assert session.get(type(row), row.id).status == 'running'
            assert session.get(type(row), row.id).attempts == 1


def test_standalone_preset_recovers_canceled_job_without_new_identity(admin_app):
    app, _ = admin_app
    job_id = enqueue_preset(app, 'quick-demo', AnalystFacts().model_dump(), locale='zh', style='coach')
    with Session(app.state.engine) as session:
        job = session.get(AdminPresetJob, job_id)
        job.status = 'running'; job.attempts = 1
        session.add(job); session.add(AdminAttempt(kind='preset', job_id=job_id, repair=False)); session.commit()
    calls = []
    class Provider:
        async def complete_json(self, *_args, **kwargs):
            calls.append(kwargs['request_id'])
            return SimpleNamespace(data=dict(summary='complete', highlights=[], players=[], comparison=None, suggestions=[]), usage={})
    app.state.glm_client = Provider()
    assert asyncio.run(run_preset(app, job_id)) is True
    assert calls == ['preset-' + job_id]
    with Session(app.state.engine) as session:
        job = session.get(AdminPresetJob, job_id)
        assert job.status == 'completed' and job.attempts == 2
        assert len(session.exec(select(AdminAttempt)).all()) == 2
