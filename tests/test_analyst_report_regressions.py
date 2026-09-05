"""Collection lifecycle, restart and migration regressions from independent review."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from conftest import isolated_server_settings
from test_analyst_jobs import (job_client, facts, report_body, all_rows, run_once,
    create_conversation, submit, ScriptedProvider)
from app.analyst_models import AnalystJob, AnalystReport
from app.models import Analysis
from app.services import analyst
from app.services.analyst_collections import preset_report_path, preset_reports
from app.services.glm import GlmJsonResult, GlmTextDelta


@pytest.fixture(autouse=True)
def forbid_real_provider(monkeypatch):
    from app.services.glm import GlmClient
    async def forbidden(*args, **kwargs):
        raise AssertionError('Review must not contact a real provider')
    monkeypatch.setattr(GlmClient, 'complete_json', forbidden)
    monkeypatch.setattr(GlmClient, 'stream', forbidden)


@pytest.mark.parametrize('status', ['queued', 'running', 'failed'])
def test_collection_exposes_preparation_state(job_client, status):
    client = job_client
    with Session(client.app.state.engine) as session:
        analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
        session.flush()
        job = session.exec(select(AnalystJob)).one()
        job.status = status
        job.error = 'Preparation failed' if status == 'failed' else None
        session.add(job)
        session.commit()
    url = f'/api/v1/tasks/{client.task_id}/analyst/report'
    single = client.get(url).json()
    collection = client.get(url + 's').json()
    assert single['status'] == status
    assert {item['status'] for item in collection['items']} == {status}
    assert {item['status'] for item in client.get(url+'s', params={'locale':'en'}).json()['items']} == {'waiting'}


def test_initial_pending_auto_collection_does_not_charge_on_ensure(job_client):
    client = job_client
    with Session(client.app.state.engine) as session:
        analyst.enqueue_completed(session, session.get(Analysis, client.task_id), enabled=True)
        session.commit()
    url = f'/api/v1/tasks/{client.task_id}/analyst/reports'
    collection = client.get(url).json()
    if any(item['status'] == 'waiting' for item in collection['items']):
        assert client.post(url, json={'locale': 'zh'}).status_code == 202
    jobs = all_rows(client, AnalystJob)
    assert sum(not json.loads(job.payload_json).get('automatic') for job in jobs) == 0


def test_concurrent_collection_posts_charge_once(job_client):
    client = job_client
    client.app.state.settings.analyst_daily_limit = 1
    url = f'/api/v1/tasks/{client.task_id}/analyst/reports'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json={'locale': 'en'}), range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    jobs = all_rows(client, AnalystJob)
    assert len(jobs) == len(all_rows(client, AnalystReport)) == 6
    assert sum(not json.loads(job.payload_json).get('automatic') for job in jobs) == 1


def test_eight_slots_are_shared_between_chat_and_reports(job_client):
    client = job_client
    for index in range(4):
        conversation = create_conversation(client)
        assert submit(client, conversation, request_id=f'chat-{index}').status_code == 202
    url = f'/api/v1/tasks/{client.task_id}/analyst/reports'
    for locale in ('zh', 'en'):
        assert client.post(url, json={'locale': locale}).status_code == 202
    async def scenario():
        class Provider:
            def __init__(self):
                self.active = 0
                self.peak = 0
                self.kinds = []
                self.started = asyncio.Event()
                self.release = asyncio.Event()
            async def enter(self, kind):
                self.active += 1
                self.peak = max(self.active, self.peak)
                self.kinds.append(kind)
                if self.active == 8:
                    self.started.set()
                await self.release.wait()
            async def complete_json(self, messages, *, request_id):
                try:
                    await self.enter('report')
                    return GlmJsonResult(data={'summary': 'Recorded facts only'}, usage={})
                finally:
                    self.active -= 1
            async def stream(self, messages, *, request_id):
                try:
                    await self.enter('message')
                    yield GlmTextDelta(text='Recorded facts only')
                finally:
                    self.active -= 1
        provider = Provider()
        client.app.state.glm_client = provider
        supervisor = analyst.AnalystSupervisor(client.app)
        await supervisor.start()
        try:
            await asyncio.wait_for(provider.started.wait(), 5)
            assert provider.active == provider.peak == 8
            assert provider.kinds.count('report') == provider.kinds.count('message') == 4
            assert sum(job.status == 'running' for job in all_rows(client, AnalystJob)) == 8
        finally:
            await supervisor.stop()
    asyncio.run(scenario())


def test_generator_reuses_legacy_preset_and_fills_both_styles(job_client, facts, monkeypatch):
    from scripts import generate_analyst_presets as generator
    client = job_client
    saved = {
        'verified': True,
        'facts_hash': analyst.digest(facts.model_dump()),
        'report': {'summary': 'Verified legacy body', 'id': 'old-report', 'model': 'glm-5.3',
                   'locale': 'zh', 'style': 'coach', 'created_at': '2026-09-01T00:00:00Z'},
    }
    path = preset_report_path(client.app.state.settings, 'quick-demo', 'zh', 'coach')
    path.parent.mkdir(parents=True)
    original = json.dumps(saved).encode()
    path.write_bytes(original)
    calls = []
    class Provider:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def complete_json(self, messages, *, request_id):
            calls.append(json.loads(messages[1]['content']))
            return GlmJsonResult(data={'summary': 'Recorded facts only'}, usage={})
    monkeypatch.setattr(generator, 'GlmClient', Provider)
    monkeypatch.setattr(generator, 'create_app', lambda: client.app)
    monkeypatch.setattr(generator, 'load_preset_facts', lambda *args: facts)
    monkeypatch.setattr('app.services.analyst_facts.load_preset_facts', lambda *args: facts)
    asyncio.run(generator.generate(['quick-demo'], ['zh', 'en'], ['coach', 'roast']))
    assert len(calls) == 11
    assert path.read_bytes() == original
    for locale in ('zh', 'en'):
        collection = preset_reports(client.app, 'quick-demo', locale)
        assert len(collection.items) == 6
        assert all(item.status == 'completed' for item in collection.items)
        assert collection.provenance['verified'] is True
    for payload in calls:
        assert payload['memory'] == {}
        if len(payload['facts']['subjects']) == 1:
            subject = payload['facts']['subjects'][0]['id']
            assert all(event['subject_id'] == subject for event in payload['facts']['evidence'])


def test_personal_refresh_failure_preserves_original_and_siblings(job_client, facts):
    from app.services.glm import GlmError
    client = job_client
    url = f'/api/v1/tasks/{client.task_id}/analyst/report'
    client.app.state.glm_client = ScriptedProvider(reports=[{'summary': 'Original body'}] * 2)
    for subject in ('player_1', 'player_2'):
        assert client.post(url, json={'subject_id': subject}).status_code == 202
        assert run_once(client)
    before = {row.id: row.model_dump() for row in all_rows(client, AnalystReport)}
    assert client.post(url, json={'subject_id': 'player_1', 'regenerate': True}).status_code == 202
    client.app.state.glm_client = ScriptedProvider(reports=[GlmError('upstream_error', retryable=False)])
    assert run_once(client)
    for row in all_rows(client, AnalystReport):
        if row.subject_id == 'player_1':
            assert row.body_json == before[row.id]['body_json']
            result = client.get(url, params={'subject_id': 'player_1'}).json()
            assert result['status'] == 'failed'
            assert result['report']['summary'] == 'Original body'
        else:
            assert row.model_dump() == before[row.id]


def test_provider_cooldown_survives_restart_for_newly_queued_jobs(job_client, monkeypatch):
    from app.services.glm import GlmError
    client = job_client
    url = f'/api/v1/tasks/{client.task_id}/analyst/report'
    assert client.post(url, json={'style': 'coach'}).status_code == 202
    provider = ScriptedProvider(reports=[
        GlmError('rate_limited', retryable=True, status_code=429, retry_after_seconds=120),
        {'summary': 'Unexpected early provider call'},
    ])
    client.app.state.glm_client = provider
    original = analyst.AnalystSupervisor(client.app)
    assert asyncio.run(original.run_once())
    assert len(provider.calls) == 1
    assert client.post(url, json={'style': 'roast'}).status_code == 202
    async def parked(self):
        await asyncio.Event().wait()
    monkeypatch.setattr(analyst.AnalystSupervisor, '_loop', parked)
    async def scenario():
        restarted = analyst.AnalystSupervisor(client.app)
        await restarted.start()
        try:
            worked = await restarted.run_once()
            assert (worked, len(provider.calls)) == (False, 1)
        finally:
            await restarted.stop()
    asyncio.run(scenario())


def test_additive_migration_defaults_language_and_preserves_legacy_rows(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    database_url = f'sqlite:///{tmp_path / "review-migration.db"}'
    monkeypatch.setenv('BASKETBALL_DATABASE_URL', database_url)
    config = Config(str(ROOT / 'alembic.ini'))
    command.upgrade(config, '20260905_0010')
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO user (id, username, hashed_password) VALUES (1, 'old', 'hash')"))
        connection.execute(text("""INSERT INTO analysis
            (id, title, owner_id, mode, source_type, status, progress, stage_message,
             input_manifest_json, created_at, updated_at)
            VALUES ('old-task', 'Old task', 1, 'full', 'upload', 'completed', 100, 'Done',
             '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
        connection.execute(text("""INSERT INTO analyst_report
            (id, owner_id, task_id, cache_key, status, body_json)
            VALUES ('old-report', 1, 'old-task', 'old-key', 'completed', '{ "summary": "Original bytes" }')"""))
        before_task = dict(connection.execute(text('SELECT * FROM analysis')).mappings().one())
        before_report = dict(connection.execute(text('SELECT * FROM analyst_report')).mappings().one())
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        task = dict(connection.execute(text('SELECT * FROM analysis')).mappings().one())
        report = dict(connection.execute(text('SELECT * FROM analyst_report')).mappings().one())
        assert task.pop('analyst_locale') == 'zh'
        assert report.pop('subject_id') is None
        assert task == before_task
        assert report == before_report
