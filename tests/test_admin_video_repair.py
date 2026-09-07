import asyncio
import json
from datetime import timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.admin_models import AdminAudit, AdminJobControl
from app.models import Analysis, StorageDeletion, SubmissionEvent, utc_now
from app.services.tasks import TASK_SLOTS
from app.services.worker import run_analysis
from tests.test_admin_auth import admin_app, login


def failed_video(app, tmp_path):
    old = utc_now() - timedelta(days=2)
    manifest = {}
    for slot in (*TASK_SLOTS, 'sync'):
        path = tmp_path / (slot + '.fixture')
        path.write_text('{}')
        manifest[slot] = str(path)
    with Session(app.state.engine) as session:
        row = Analysis(owner_id=2, title='private', input_manifest_json=json.dumps(manifest), status='failed',
            submitted_at=old, started_at=old+timedelta(seconds=10), completed_at=old+timedelta(seconds=20),
            error_code='ENGINE_FAILED', error_message='old error')
        session.add(row); session.flush()
        session.add(SubmissionEvent(task_id=row.id, owner_id=2, kind='submit', submitted_at=old))
        session.commit(); session.refresh(row)
        return row


@pytest.mark.parametrize('target', ['analysis_root', 'enrollment', 'input', 'data', 'engine_output'])
def test_admin_retry_rechecks_durable_cleanup_after_jobs_listing(admin_app, tmp_path, target):
    app, client = admin_app
    row = failed_video(app, tmp_path)
    headers = login(client)
    listed = client.get('/api/v1/admin/jobs?kind=video', headers=headers).json()['items'][0]
    assert 'retry' in listed['allowed_actions']
    with Session(app.state.engine) as session:
        session.add(StorageDeletion(analysis_id=row.id, target=target)); session.commit()
    response = client.post('/api/v1/admin/jobs/actions', headers=headers,
        json={'kind':'video', 'ids':[row.id], 'action':'retry', 'reason':'retry after stale listing'})
    assert response.status_code == 409
    with Session(app.state.engine) as session:
        assert session.get(Analysis, row.id).model_dump() == row.model_dump()
        assert session.get(AdminJobControl, ('video', row.id)) is None
        assert session.get(StorageDeletion, (row.id, target)) is not None
        assert len(session.exec(select(SubmissionEvent)).all()) == 1
        audit = session.exec(select(AdminAudit)).one()
        assert json.loads(audit.changes_json)['outcome'] == {'status':'rejected', 'http_status':409}
    listed = client.get('/api/v1/admin/jobs?kind=video', headers=headers).json()['items'][0]
    assert 'retry' not in listed['allowed_actions']


def test_admin_retry_resets_attempt_timestamps_without_ordinary_quota_charge(admin_app, tmp_path, monkeypatch):
    app, client = admin_app
    row = failed_video(app, tmp_path)
    lower = utc_now()
    response = client.post('/api/v1/admin/jobs/actions', headers=login(client),
        json={'kind':'video', 'ids':[row.id], 'action':'retry', 'reason':'new repair execution'})
    assert response.status_code == 200
    with Session(app.state.engine) as session:
        queued = session.get(Analysis, row.id)
        assert queued.started_at is None and queued.completed_at is None
        assert lower <= queued.submitted_at.replace(tzinfo=timezone.utc) <= utc_now()
        assert queued.error_code is None and queued.error_message is None
        event = session.exec(select(SubmissionEvent)).one()
        assert event.submitted_at == row.submitted_at and event.kind == 'submit'
        audit = json.loads(session.exec(select(AdminAudit)).one().changes_json)
        assert audit['before'][row.id]['started_at'] is not None
        assert audit['after'][row.id]['started_at'] is None
        assert audit['after'][row.id]['completed_at'] is None
        assert audit['before'][row.id]['submitted_at'] != audit['after'][row.id]['submitted_at']
    # Exercise the real worker lifecycle with a tiny child instead of research GPU
    # execution; the original-input fixtures above are deliberately not real videos.
    from tests.test_worker import replace_research_child
    app.state.settings.simulation_mode = False
    output = app.state.storage.prepare(row.id) / 'output'
    replace_research_child(monkeypatch, '\n'.join([
        'from pathlib import Path', f'output=Path({str(output)!r})',
        'output.mkdir(parents=True,exist_ok=True)',
        'for name in ("report.json","summary.json","media_manifest.json"): (output/name).write_text("{}")',
    ]))
    asyncio.run(run_analysis(app, row.id))
    with Session(app.state.engine) as session:
        done = session.get(Analysis, row.id)
        assert done.status == 'completed'
        assert lower <= done.started_at.replace(tzinfo=timezone.utc) <= done.completed_at.replace(tzinfo=timezone.utc)
        assert (done.completed_at - done.started_at).total_seconds() < 10
        assert len(session.exec(select(SubmissionEvent)).all()) == 1


def test_admin_repair_of_legacy_unledgered_video_does_not_charge_ordinary_daily_quota(admin_app, tmp_path):
    from app.services.tasks import count_daily_submissions
    app, client = admin_app
    row = failed_video(app, tmp_path)
    with Session(app.state.engine) as session:
        session.delete(session.exec(select(SubmissionEvent)).one()); session.commit()
        assert count_daily_submissions(session, 2) == 0
    response = client.post('/api/v1/admin/jobs/actions', headers=login(client),
        json={'kind':'video', 'ids':[row.id], 'action':'retry', 'reason':'repair legacy video'})
    assert response.status_code == 200
    with Session(app.state.engine) as session:
        assert count_daily_submissions(session, 2) == 0
        assert session.exec(select(SubmissionEvent)).all() == []
