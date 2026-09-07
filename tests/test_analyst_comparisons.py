"""Separate, explicitly requested history reports never replace session reports."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json

import pytest
from sqlmodel import Session, select

from app.analyst_models import AnalystJob, AnalystReport, TaskSubject, TrainingObservation, TrainingProfile
from app.models import Analysis, User
from app.services import analyst
from app.services.analyst_facts import metrics_for_subject
from app.services.training_profiles import cleanup_analyst_task, invalidate_memory
from test_analyst_jobs import (
    job_client, facts, report_body, ScriptedProvider, PausingProvider,
    all_rows, get_row, report_url, request_report, run_once, make_due, set_daily_ai_limit,
)


def comparison_url(client):
    return f"/api/v1/tasks/{client.task_id}/analyst/comparisons"


def history(client, facts, *, kind="player", subject="player_1", bind=True, name="Alex"):
    response = client.post('/api/v1/training-profiles', json={"kind": kind, "name": name})
    assert response.status_code == 201, response.text
    profile_id = response.json()['id']
    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, client.task_id)
        previous = Analysis(owner_id=client.owner_id, title="Previous", status="expired", mode=task.mode,
                            input_manifest_json="{}", created_at=task.created_at - timedelta(days=1))
        session.add(previous)
        session.flush()
        row = TrainingObservation(owner_id=client.owner_id, profile_id=profile_id, source_task_id=previous.id,
                                  fingerprint=f"previous-{profile_id}", mode=task.mode,
                                  occurred_at=previous.created_at,
                                  metrics_json=(facts.metrics if kind == "team" else metrics_for_subject(facts, subject)).model_dump_json())
        session.add(row)
        session.commit()
        session.refresh(row)
        observation_id = row.id
    if bind:
        current = client.get(f"/api/v1/tasks/{client.task_id}/analyst/context").json()
        payload = {"subjects": [{"id": item['id'], "profile_id": profile_id if item['id'] == subject and kind == "player" else item['profile_id']} for item in current['subjects']],
                   "team_profile_id": profile_id if kind == "team" else current['team_profile_id']}
        response = client.put(f"/api/v1/tasks/{client.task_id}/analyst/context", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()['comparison_id'] is None
    return profile_id, observation_id


def post_comparison(client, observation_id, **kwargs):
    return client.post(comparison_url(client), json={"comparison_id": observation_id, "locale": "en", "style": "coach", **kwargs})


def snapshot(client, job):
    return (get_row(client, AnalystReport, job.report_id).model_dump(mode="json"),
            get_row(client, AnalystJob, job.id).model_dump(mode="json"))


def finish_base(client, body):
    job = request_report(client)
    client.app.state.glm_client = ScriptedProvider(reports=[body])
    assert run_once(client)
    return job


def comparison_body(body):
    return {**body, "comparison": {"text": "Compare the recorded sessions with their sample sizes", "evidence_ids": ["event-1"]}}


def comparison_jobs(client):
    return sorted((job for job in all_rows(client, AnalystJob)
                   if json.loads(job.payload_json).get('report_kind') == 'comparison'),
                  key=lambda job: job.created_at)


def test_session_bytes_and_jobs_survive_binding_goals_comparison_and_history_changes(job_client, facts, report_body):
    client = job_client
    base = finish_base(client, report_body)
    original = snapshot(client, base)
    profile, observation = history(client, facts)
    assert client.patch(f'/api/v1/training-profiles/{profile}', json={"goals": "Updated goal"}).status_code == 200
    assert snapshot(client, base) == original
    assert client.get(comparison_url(client), params={"locale": "en"}).json() == {"items": []}
    context_before = client.get(f'/api/v1/tasks/{client.task_id}/analyst/context').json()
    response = post_comparison(client, observation)
    assert response.status_code == 202, response.text
    assert response.json()['comparison_id'] == observation
    assert response.json()['status'] == 'queued'
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)])
    assert run_once(client)
    items = client.get(comparison_url(client), params={"locale": "en"}).json()['items']
    assert len(items) == 1 and items[0]['status'] == 'completed'
    assert items[0]['report']['id'] != base.report_id
    assert client.get(f'/api/v1/tasks/{client.task_id}/analyst/context').json() == context_before
    assert post_comparison(client, observation).json() == items[0]
    with Session(client.app.state.engine) as session:
        row = session.get(TrainingObservation, observation)
        metrics = json.loads(row.metrics_json)
        metrics['shots']['makes'] = 0
        row.metrics_json = json.dumps(metrics)
        session.add(row)
        invalidate_memory(session, client.owner_id, observation_ids={observation})
        session.commit()
    assert client.get(comparison_url(client), params={"locale": "en"}).json() == {"items": []}
    assert client.get(report_url(client), params={"locale": "en"}).json()['report']['id'] == base.report_id
    assert snapshot(client, base) == original


@pytest.mark.parametrize('kind', ['player', 'team'])
def test_comparison_snapshot_scopes_profiles_history_and_current_metrics(job_client, facts, report_body, kind):
    client = job_client
    profile, observation = history(client, facts, kind=kind)
    history(client, facts, subject='player_2', name='Unrelated private name')
    response = post_comparison(client, observation)
    assert response.status_code == 202, response.text
    jobs = comparison_jobs(client)
    assert len(jobs) == 2
    assert [json.loads(job.payload_json)['style'] for job in jobs] == ['coach', 'roast']
    for job in jobs:
        payload = json.loads(job.payload_json)
        assert job.kind == 'report'
        assert payload['report_kind'] == 'comparison' and payload['comparison_id'] == observation
        assert [p['id'] for p in payload['memory']['profiles']] == [profile]
        assert [o['id'] for o in payload['memory']['observations']] == [observation]
        scope = payload['memory']['comparison_scope']
        assert scope['subject_id'] == ('player_1' if kind == 'player' else None)
        assert scope['current_metrics'] == (metrics_for_subject(facts, 'player_1') if kind == 'player' else facts.metrics).model_dump(mode='json')
        assert 'Unrelated private name' not in job.payload_json
        if kind == 'player':
            assert {s['id'] for s in payload['facts']['subjects']} == {'player_1'}
            assert {e['subject_id'] for e in payload['facts']['evidence']} == {'player_1'}
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)] * 2)
    for job in jobs:
        assert run_once(client)
        assert get_row(client, AnalystJob, job.id).status == 'completed'
        style = json.loads(job.payload_json)['style']
        items = client.get(comparison_url(client), params={'locale': 'en', 'style': style}).json()['items']
        assert len(items) == 1 and items[0]['status'] == 'completed'
        assert items[0]['report']['style'] == style
    assert run_once(client) is False
    assert [call[1] for call in client.app.state.glm_client.calls] == [job.request_id for job in jobs]


def test_session_generation_ignores_legacy_comparison_preference_and_memory(job_client, facts, report_body):
    client = job_client
    profile, observation = history(client, facts)
    response = client.put(f'/api/v1/tasks/{client.task_id}/analyst/context', json={
        'subjects': [{'id': 'player_1', 'profile_id': profile}], 'comparison_id': observation,
    })
    assert response.status_code == 200
    job = finish_base(client, report_body)
    payload = json.loads(get_row(client, AnalystJob, job.id).payload_json)
    assert payload['memory'] == {}
    assert payload['report_kind'] == 'session'
    assert get_row(client, AnalystReport, job.report_id).kind == 'session'
    assert len(all_rows(client, AnalystJob)) == 1
    assert client.get(comparison_url(client), params={"locale": "en"}).json() == {'items': []}


@pytest.mark.parametrize('changed', ['none', 'facts', 'locale', 'model', 'scrubbed'])
def test_legacy_original_lookup_preserves_rows_only_for_matching_inputs(job_client, facts, report_body, changed):
    client = job_client
    job = finish_base(client, report_body)
    with Session(client.app.state.engine) as session:
        row = session.get(AnalystReport, job.report_id)
        stored_job = session.get(AnalystJob, job.id)
        payload = json.loads(stored_job.payload_json)
        payload.pop('report_kind', None)
        payload.pop('prompt_version', None)
        payload['memory'] = {'profiles': [{'id': 'old-profile', 'notes': 'Original context'}]}
        if changed == 'facts':
            payload['facts']['fingerprint'] = 'different-input'
        if changed == 'locale':
            row.locale = payload['locale'] = 'zh'
        if changed == 'model':
            row.model = 'old-model'
        task = session.get(Analysis, client.task_id)
        row.cache_key = analyst.digest({'owner': client.owner_id, 'task': task.id, 'facts': payload['facts'],
            'memory': payload['memory'], 'locale': row.locale, 'style': row.style, 'model': row.model, 'prompt': 'basketball-analyst-v1'})
        payload['cache_key'] = row.cache_key
        stored_job.payload_json = json.dumps(payload if changed != 'scrubbed' else {'automatic': False})
        session.add(row)
        session.add(stored_job)
        session.commit()
    before = snapshot(client, job)
    response = client.get(report_url(client), params={'locale': 'en'})
    assert response.status_code == 200
    assert response.json()['status'] == ('completed' if changed == 'none' else 'waiting')
    if changed == 'none':
        assert client.post(report_url(client), json={'locale': 'en'}).json()['report']['id'] == job.report_id
        assert len(all_rows(client, AnalystJob)) == 1
        profile, _ = history(client, facts)
        assert client.patch(f'/api/v1/training-profiles/{profile}', json={'notes': 'New notes'}).status_code == 200
        assert client.get(report_url(client), params={'locale': 'en'}).json()['report']['id'] == job.report_id
    assert snapshot(client, job) == before


@pytest.mark.parametrize('style', ['coach', 'roast'])
def test_comparison_validation_dedup_and_quota_are_separate_from_session(job_client, facts, report_body, style):
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    _, unlinked = history(client, facts, bind=False)
    assert post_comparison(client, unlinked).status_code == 422
    assert post_comparison(client, 'missing').status_code == 404
    _, observation = history(client, facts)
    set_daily_ai_limit(client, 2)
    alternate = 'roast' if style == 'coach' else 'coach'
    assert post_comparison(client, observation, style=style).status_code == 202
    jobs = comparison_jobs(client)
    assert [json.loads(job.payload_json)['style'] for job in jobs] == [style, alternate]
    assert [json.loads(job.payload_json)['automatic'] for job in jobs] == [False, True]
    assert len({job.report_id for job in jobs}) == len({job.request_id for job in jobs}) == 2
    pending = [snapshot(client, job) for job in jobs]
    for requested in (style, alternate):
        assert post_comparison(client, observation, style=requested).status_code == 202
        assert post_comparison(client, observation, style=requested, regenerate=True).status_code == 202
    assert len(all_rows(client, AnalystJob)) == 3
    assert [snapshot(client, job) for job in jobs] == pending
    assert sum(not json.loads(job.payload_json)['automatic'] for job in all_rows(client, AnalystJob)) == 2
    assert post_comparison(client, observation, locale='zh', style=style).status_code == 429
    assert len(all_rows(client, AnalystReport)) == 3
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)] * 2)
    for job in jobs:
        assert run_once(client)
        assert get_row(client, AnalystJob, job.id).status == 'completed'
    completed = [snapshot(client, job) for job in jobs]
    for requested in (style, alternate):
        assert post_comparison(client, observation, style=requested).json()['status'] == 'completed'
        assert post_comparison(client, observation, style=requested, regenerate=True).status_code == 429
    assert [snapshot(client, job) for job in jobs] == completed
    assert len(all_rows(client, AnalystJob)) == 3
    assert run_once(client) is False
    assert snapshot(client, base) == before


def test_failed_comparison_and_explicit_retry_leave_original_unchanged(job_client, facts, report_body):
    from app.services.glm import GlmError
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    _, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    requested, sibling = comparison_jobs(client)
    client.app.state.glm_client = ScriptedProvider(reports=[GlmError('Unavailable', retryable=False)])
    assert run_once(client)
    item = client.get(comparison_url(client), params={'locale': 'en'}).json()['items'][0]
    assert item['status'] == 'failed' and item['error']
    failed = snapshot(client, requested)
    sibling_before = snapshot(client, sibling)
    assert snapshot(client, base) == before
    assert post_comparison(client, observation).status_code == 202
    retried = comparison_jobs(client)[-1]
    assert retried.id not in {requested.id, sibling.id}
    assert retried.report_id == requested.report_id
    assert snapshot(client, sibling) == sibling_before
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)] * 2)
    # The existing sibling precedes the newly queued explicit retry.
    assert run_once(client)
    assert get_row(client, AnalystJob, sibling.id).status == 'completed'
    assert get_row(client, AnalystJob, retried.id).status == 'queued'
    assert run_once(client)
    assert get_row(client, AnalystJob, retried.id).status == 'completed'
    assert client.get(comparison_url(client), params={'locale': 'en'}).json()['items'][0]['status'] == 'completed'
    assert get_row(client, AnalystJob, requested.id).model_dump(mode='json') == failed[1]
    assert [call[1] for call in client.app.state.glm_client.calls] == [sibling.request_id, retried.request_id]
    assert len(all_rows(client, AnalystJob)) == 4
    assert run_once(client) is False
    assert snapshot(client, base) == before


@pytest.mark.parametrize('late_error', [False, True])
def test_inflight_comparison_revocation_cannot_republish_and_preserves_session(job_client, facts, report_body, late_error):
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    profile, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    report_ids = {job.report_id for job in comparison_jobs(client)}
    async def run():
        provider = PausingProvider(comparison_body(report_body), error=ValueError('late') if late_error else None)
        client.app.state.glm_client = provider
        pending = asyncio.create_task(analyst.AnalystSupervisor(client.app).run_once())
        await asyncio.wait_for(provider.started.wait(), 2)
        assert client.patch(f'/api/v1/training-profiles/{profile}', json={'notes': 'changed'}).status_code == 200
        provider.release.set()
        await pending
    asyncio.run(run())
    assert client.get(comparison_url(client), params={'locale': 'en'}).json() == {'items': []}
    assert snapshot(client, base) == before
    revoked = [job for job in all_rows(client, AnalystJob) if job.id != base.id]
    assert len(revoked) == 2
    assert all(job.status == 'failed' for job in revoked)
    assert sorted(json.loads(job.payload_json)['automatic'] for job in revoked) == [False, True]
    assert all(json.loads(job.payload_json) == {'automatic': json.loads(job.payload_json)['automatic']} for job in revoked)
    assert all(job.report_id is None for job in revoked)
    assert len(report_ids) == 2
    assert all(get_row(client, AnalystReport, report_id) is None for report_id in report_ids)
    assert run_once(client) is False


def test_comparison_does_not_suppress_automatic_session_reconciliation(job_client, facts):
    client = job_client
    _, observation = history(client, facts)
    assert post_comparison(client, observation, locale='zh').status_code == 202
    assert analyst.AnalystSupervisor(client.app).reconcile_completed() == 1
    assert analyst.AnalystSupervisor(client.app).reconcile_completed() == 0
    assert len([job for job in all_rows(client, AnalystJob) if job.kind == 'prepare']) == 1


@pytest.mark.parametrize('mutation', ['delete', 'expire', 'reset'])
def test_explicit_cleanup_or_reset_removes_both_report_kinds(job_client, facts, report_body, mutation):
    client = job_client
    finish_base(client, report_body)
    _, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    with Session(client.app.state.engine) as session:
        if mutation == 'reset':
            invalidate_memory(session, client.owner_id)
        else:
            cleanup_analyst_task(session, client.task_id, expired=mutation == 'expire')
        session.commit()
    assert all_rows(client, AnalystReport) == []
    assert not any(job.status in {'queued', 'running'} for job in all_rows(client, AnalystJob))


def test_concurrent_comparison_posts_and_regeneration_reuse_one_durable_job_per_style(job_client, facts, report_body):
    from concurrent.futures import ThreadPoolExecutor
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    _, observation = history(client, facts)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post_comparison(client, observation), range(2)))
    assert [response.status_code for response in responses] == [202, 202]
    assert len(all_rows(client, AnalystReport)) == len(all_rows(client, AnalystJob)) == 3
    requested, sibling = comparison_jobs(client)
    assert [json.loads(job.payload_json)['style'] for job in (requested, sibling)] == ['coach', 'roast']
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)] * 3)
    assert run_once(client)
    original = post_comparison(client, observation).json()['report']
    original_job = get_row(client, AnalystJob, requested.id).model_dump()
    sibling_before = snapshot(client, sibling)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post_comparison(client, observation, regenerate=True), range(2)))
    assert [response.status_code for response in responses] == [202, 202]
    assert all(response.json()['report'] == original for response in responses)
    assert len(all_rows(client, AnalystReport)) == 3
    assert len(all_rows(client, AnalystJob)) == 4
    refreshed = comparison_jobs(client)[-1]
    assert refreshed.report_id == requested.report_id
    assert refreshed.request_id != requested.request_id
    assert snapshot(client, sibling) == sibling_before
    assert sum(not json.loads(job.payload_json)['automatic'] for job in all_rows(client, AnalystJob)) == 3
    assert run_once(client)
    assert get_row(client, AnalystJob, sibling.id).status == 'completed'
    assert get_row(client, AnalystJob, refreshed.id).status == 'queued'
    sibling_completed = snapshot(client, sibling)
    assert run_once(client)
    assert get_row(client, AnalystJob, refreshed.id).status == 'completed'
    assert post_comparison(client, observation).json()['report']['id'] == original['id']
    assert snapshot(client, sibling) == sibling_completed
    assert get_row(client, AnalystJob, requested.id).model_dump() == original_job
    assert [call[1] for call in client.app.state.glm_client.calls] == [requested.request_id, sibling.request_id, refreshed.request_id]
    assert len(all_rows(client, AnalystJob)) == 4
    assert run_once(client) is False
    assert snapshot(client, base) == before


def test_comparison_restart_recovers_same_report_and_request_without_touching_original(job_client, facts, report_body, monkeypatch):
    client = job_client
    # Default locale lets the startup collection backfill reuse this original.
    response = client.post(report_url(client), json={})
    assert response.status_code == 202
    client.app.state.glm_client = ScriptedProvider(reports=[report_body])
    assert run_once(client)
    base = all_rows(client, AnalystJob)[0]
    before = snapshot(client, base)
    _, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    job, sibling = comparison_jobs(client)
    sibling_before = snapshot(client, sibling)
    with Session(client.app.state.engine) as session:
        current = session.get(AnalystJob, job.id)
        current.status = 'running'
        current.attempts = 1
        session.add(current)
        row = session.get(AnalystReport, job.report_id)
        row.status = 'running'
        session.add(row)
        session.commit()
    async def parked(*_):
        await asyncio.Event().wait()
    monkeypatch.setattr(analyst.AnalystSupervisor, '_loop', parked)
    monkeypatch.setattr(analyst.AnalystSupervisor, '_reconcile_loop', parked)
    async def restart():
        supervisor = analyst.AnalystSupervisor(client.app)
        await supervisor.start()
        try:
            assert get_row(client, AnalystJob, job.id).status == 'queued'
            assert get_row(client, AnalystReport, job.report_id).status == 'queued'
            assert snapshot(client, sibling) == sibling_before
            prepares = [row for row in all_rows(client, AnalystJob) if row.kind == 'prepare']
            assert len(prepares) == 1 and prepares[0].status == 'queued'
            client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)])
            assert await supervisor.run_once()
        finally:
            await supervisor.stop()
    asyncio.run(restart())
    recovered = get_row(client, AnalystJob, job.id)
    assert recovered.status == 'completed' and recovered.attempts == 2
    assert recovered.report_id == job.report_id and recovered.request_id == job.request_id
    assert client.app.state.glm_client.calls[0][1] == job.request_id
    assert snapshot(client, sibling) == sibling_before
    assert len(all_rows(client, AnalystJob)) == 4
    assert snapshot(client, base) == before


@pytest.mark.parametrize('invalid', ['missing_comparison', 'foreign_evidence', 'foreign_player', 'private_path'])
def test_comparison_output_validation_retries_without_mutating_session(job_client, facts, report_body, invalid):
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    _, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    body = comparison_body(deepcopy(report_body))
    if invalid == 'missing_comparison':
        body['comparison'] = None
    elif invalid == 'foreign_evidence':
        body['comparison']['evidence_ids'] = ['event-2']
    elif invalid == 'foreign_player':
        body['players'][0]['subject_id'] = 'player_2'
    else:
        body['comparison']['text'] = '/Users/synthetic/private'
    provider = ScriptedProvider(reports=[body, comparison_body(report_body)])
    client.app.state.glm_client = provider
    job = next(job for job in all_rows(client, AnalystJob) if job.id != base.id)
    assert run_once(client)
    assert get_row(client, AnalystJob, job.id).status == 'queued'
    assert client.get(comparison_url(client), params={'locale': 'en'}).json()['items'][0]['report'] is None
    make_due(client, job.id)
    assert run_once(client)
    assert get_row(client, AnalystJob, job.id).status == 'completed'
    assert provider.calls[0][1] == provider.calls[1][1]
    assert snapshot(client, base) == before


@pytest.mark.parametrize('change', ['mode', 'actions', 'future', 'same_input', 'profile_kind'])
def test_incompatible_comparison_never_creates_report_or_job(job_client, facts, change):
    client = job_client
    profile, observation = history(client, facts)
    with Session(client.app.state.engine) as session:
        row = session.get(TrainingObservation, observation)
        task = session.get(Analysis, client.task_id)
        if change == 'mode':
            row.mode = 'quick' if task.mode == 'full' else 'full'
        elif change == 'actions':
            metrics = json.loads(row.metrics_json)
            metrics['action_counts'] = {'layup': 1}
            row.metrics_json = json.dumps(metrics)
        elif change == 'future':
            row.occurred_at = task.created_at + timedelta(days=1)
        elif change == 'same_input':
            observation = session.exec(select(TrainingObservation).where(
                TrainingObservation.owner_id == client.owner_id, TrainingObservation.profile_id == profile,
                TrainingObservation.fingerprint == facts.fingerprint)).one().id
        else:
            linked = session.get(TrainingProfile, profile)
            linked.kind = 'team'
            session.add(linked)
        session.add(row)
        session.commit()
    assert post_comparison(client, observation).status_code == 422
    assert all_rows(client, AnalystReport) == all_rows(client, AnalystJob) == []
    assert client.app.state.glm_client.calls == []


def test_comparisons_enforce_task_and_observation_owner_scope(job_client, facts):
    client = job_client
    _, observation = history(client, facts)
    with Session(client.app.state.engine) as session:
        outsider = User(username='outsider', hashed_password='unused')
        session.add(outsider)
        session.flush()
        other_task = Analysis(owner_id=outsider.id, title='Private', status='completed', input_manifest_json='{}')
        other_profile = TrainingProfile(owner_id=outsider.id, kind='player', name='Private profile')
        session.add_all([other_task, other_profile])
        session.flush()
        other_history = TrainingObservation(owner_id=outsider.id, profile_id=other_profile.id, source_task_id=other_task.id,
            fingerprint='other', mode='full', metrics_json=facts.metrics.model_dump_json())
        session.add(other_history)
        session.commit()
        foreign_task_id, foreign_history_id = other_task.id, other_history.id
    assert post_comparison(client, foreign_history_id).status_code == 404
    assert client.get(f'/api/v1/tasks/{foreign_task_id}/analyst/comparisons').status_code == 404
    assert client.post(f'/api/v1/tasks/{foreign_task_id}/analyst/comparisons', json={'comparison_id': observation}).status_code == 404
    assert client.get(comparison_url(client)).json() == {'items': []}
    assert all_rows(client, AnalystJob) == []


@pytest.mark.parametrize('expired', [False, True])
def test_history_source_expiry_or_deletion_preserves_original_and_requires_explicit_comparison_request(job_client, facts, report_body, expired):
    client = job_client
    base = finish_base(client, report_body)
    before = snapshot(client, base)
    _, observation = history(client, facts)
    assert post_comparison(client, observation).status_code == 202
    client.app.state.glm_client = ScriptedProvider(reports=[comparison_body(report_body)])
    assert run_once(client)
    with Session(client.app.state.engine) as session:
        row = session.get(TrainingObservation, observation)
        source_id = row.source_task_id
        cleanup_analyst_task(session, source_id, expired=expired)
        session.commit()
    assert client.get(comparison_url(client), params={'locale': 'en'}).json() == {'items': []}
    assert snapshot(client, base) == before
    assert run_once(client) is False
    assert post_comparison(client, observation).status_code == (202 if expired else 404)


@pytest.mark.parametrize('style', ['coach', 'roast'])
def test_comparison_list_filters_locale_style_and_never_queues_unrequested_history(job_client, facts, style):
    client = job_client
    _, observation = history(client, facts)
    history(client, facts, subject='player_2')
    for locale in ('en', 'zh'):
        for requested in ('coach', 'roast'):
            assert client.get(comparison_url(client), params={'locale': locale, 'style': requested}).json() == {'items': []}
    assert all_rows(client, AnalystJob) == []
    assert post_comparison(client, observation, style=style).status_code == 202
    jobs = comparison_jobs(client)
    alternate = 'roast' if style == 'coach' else 'coach'
    assert [json.loads(job.payload_json)['style'] for job in jobs] == [style, alternate]
    before = [snapshot(client, job) for job in jobs]
    assert client.get(comparison_url(client), params={'locale': 'zh'}).json() == {'items': []}
    for requested in ('coach', 'roast'):
        items = client.get(comparison_url(client), params={'locale': 'en', 'style': requested}).json()['items']
        assert len(items) == 1 and items[0]['comparison_id'] == observation
        assert items[0]['status'] == 'queued' and items[0]['report'] is None
    assert len(all_rows(client, AnalystJob)) == len(all_rows(client, AnalystReport)) == 2
    assert [snapshot(client, job) for job in jobs] == before
    assert client.app.state.glm_client.calls == []
