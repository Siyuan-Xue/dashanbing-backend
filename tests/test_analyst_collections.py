"""Full scoped reports are prepared once, with isolated facts and quota accounting."""
import asyncio
import json

from sqlmodel import Session, select

from app.analyst_models import AnalystJob, AnalystReport
from app.models import Analysis
from app.services import analyst
from test_analyst_jobs import job_client, facts, report_body, ScriptedProvider, all_rows, run_once


def collection_url(client):
    return f"/api/v1/tasks/{client.task_id}/analyst/reports"


def test_collection_queues_full_reports_for_both_styles_once_and_charges_once(job_client, report_body):
    client = job_client
    client.app.state.settings.analyst_daily_limit = 1
    response = client.post(collection_url(client), json={"locale": "en"})
    assert response.status_code == 202, response.text
    items = response.json()['items']
    assert {(x['subject_id'], x['style']) for x in items} == {
        (None, 'coach'), (None, 'roast'), ('player_1', 'coach'), ('player_1', 'roast'), ('player_2', 'coach'), ('player_2', 'roast')}
    assert all(x['status'] == 'queued' and x['locale'] == 'en' for x in items)
    assert client.post(collection_url(client), json={'locale': 'en'}).status_code == 202
    assert len(all_rows(client, AnalystJob)) == 6
    # Initial task-language variants remain covered by the task quota.
    assert client.post(collection_url(client), json={'locale': 'zh'}).status_code == 202
    assert len(all_rows(client, AnalystJob)) == 12
    jobs = sorted(all_rows(client, AnalystJob), key=lambda x: x.created_at)
    assert [json.loads(x.payload_json).get('subject_id') for x in jobs[:2]] == [None, None]
    assert sum(not json.loads(x.payload_json).get('automatic') for x in jobs) == 1
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    run_once(client)
    assert client.post(f'/api/v1/tasks/{client.task_id}/analyst/report', json={'locale':'en','regenerate':True}).status_code == 429


def test_personal_report_provider_input_excludes_other_players(job_client, facts):
    client = job_client
    response = client.post(f"/api/v1/tasks/{client.task_id}/analyst/report", json={'locale': 'en', 'subject_id': 'player_2'})
    assert response.status_code == 202, response.text
    payload = json.loads(all_rows(client, AnalystJob)[0].payload_json)
    assert payload['subject_id'] == 'player_2'
    assert payload['facts']['subjects'] == [{'id': 'player_2', 'label': '球员 2'}]
    assert payload['facts']['metrics']['shots'] == {'attempts': 1, 'makes': 0, 'misses': 1, 'undetermined': 0, 'make_rate': 0.0, 'unlinked_outcomes': 0}
    assert {x['subject_id'] for x in payload['facts']['evidence']} == {'player_2'}
    assert payload['memory'] == {}
    assert client.post(f"/api/v1/tasks/{client.task_id}/analyst/report", json={'subject_id': 'someone-else'}).status_code == 422
    assert len(all_rows(client, AnalystJob)) == 1


def test_report_refresh_keeps_original_body_until_replacement_completes(job_client, report_body):
    client = job_client
    url = f"/api/v1/tasks/{client.task_id}/analyst/report"
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    assert client.post(url, json={'locale': 'en'}).status_code == 202
    run_once(client)
    original = client.get(url, params={'locale': 'en'}).json()['report']
    response = client.post(url, json={'locale': 'en', 'regenerate': True})
    assert response.json()['status'] == 'queued'
    assert response.json()['report'] == original
    assert client.get(url, params={'locale': 'en'}).json()['report'] == original


def test_automatic_prepare_uses_saved_task_language_and_fills_missing_only(job_client, report_body):
    client = job_client
    url = f"/api/v1/tasks/{client.task_id}/analyst/report"
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    client.post(url, json={'locale': 'en'})
    run_once(client)
    original = client.get(url, params={'locale': 'en'}).json()['report']
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        task.analyst_locale = 'en'
        session.add(task)
        session.commit()
    supervisor = analyst.AnalystSupervisor(client.app)
    assert supervisor.reconcile_completed() == 1
    run_once(client)
    rows = all_rows(client, AnalystReport)
    assert len(rows) == 6 and {x.locale for x in rows} == {'en'}
    assert client.get(url, params={'locale': 'en'}).json()['report'] == original
    assert supervisor.reconcile_completed() == 0


def test_task_language_is_saved_and_legacy_requests_default_to_chinese(job_client):
    client = job_client
    created = client.post('/api/v1/tasks', json={'title': 'English practice', 'mode': 'quick', 'analyst_locale': 'en'})
    assert created.status_code == 201, created.text
    tid = created.json()['id']
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, tid).analyst_locale == 'en'
    changed = client.patch('/api/v1/tasks/' + tid, json={'title': 'Updated', 'mode': 'quick', 'analyst_locale': 'zh'})
    assert changed.status_code == 200, changed.text
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, tid).analyst_locale == 'zh'
    legacy = client.post('/api/v1/tasks', json={'title': 'Legacy', 'mode': 'quick'})
    with Session(client.app.state.engine) as session:
        assert session.get(Analysis, legacy.json()['id']).analyst_locale == 'zh'


def test_reading_collections_never_queues_and_foreign_tasks_are_hidden(job_client):
    from app.models import User
    client = job_client
    response = client.get(collection_url(client))
    assert response.status_code == 200
    assert len(response.json()['items']) == 6
    assert all_rows(client, AnalystJob) == []
    with Session(client.app.state.engine) as session:
        other = User(username='other', hashed_password='unused')
        session.add(other); session.flush()
        task = Analysis(title='Private', owner_id=other.id, status='completed', input_manifest_json='{}')
        session.add(task); session.commit(); session.refresh(task)
        path = f'/api/v1/tasks/{task.id}/analyst/reports'
    assert client.get(path).status_code == 404
    assert client.post(path, json={'locale':'zh'}).status_code == 404
    assert all_rows(client, AnalystJob) == []


def test_eight_workers_run_in_parallel_without_starting_a_ninth_request(job_client):
    from app.services.glm import GlmJsonResult
    client = job_client
    client.post(collection_url(client), json={'locale':'zh'})
    client.post(collection_url(client), json={'locale':'en'})

    async def scenario():
        class Provider:
            def __init__(self):
                self.active = 0; self.peak = 0; self.started = asyncio.Event(); self.release = asyncio.Event()

            async def complete_json(self, messages, *, request_id):
                self.active += 1; self.peak = max(self.peak, self.active)
                if self.active == 8: self.started.set()
                try:
                    await self.release.wait()
                    return GlmJsonResult(data={'summary':'Only recorded facts', 'highlights':[], 'players':[], 'suggestions':[]}, usage={})
                finally:
                    self.active -= 1

        provider = Provider(); client.app.state.glm_client = provider
        supervisor = analyst.AnalystSupervisor(client.app)
        await supervisor.start()
        try:
            await asyncio.wait_for(provider.started.wait(), timeout=5)
            assert provider.active == 8
            assert sum(row.status == 'running' for row in all_rows(client, AnalystJob)) == 8
            assert sum(row.status == 'queued' for row in all_rows(client, AnalystJob)) >= 4
        finally:
            await supervisor.stop()
        assert provider.peak == 8
    asyncio.run(scenario())


def test_rate_limit_defers_the_shared_queue_without_consuming_other_attempts(job_client):
    from datetime import datetime, timezone
    from app.services.glm import GlmError
    client = job_client
    client.post(collection_url(client), json={'locale':'zh'})
    client.app.state.glm_client = ScriptedProvider(reports=[GlmError('rate_limited', retryable=True, status_code=429)])
    assert run_once(client)
    rows = all_rows(client, AnalystJob)
    now = datetime.now(timezone.utc)
    assert all((row.available_at.replace(tzinfo=timezone.utc)-now).total_seconds() >= 29 for row in rows)
    assert sum(row.attempts for row in rows) == 1
    # A restarted supervisor observes the same durable cooldown.
    assert run_once(client) is False
