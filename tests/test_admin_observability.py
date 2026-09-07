"""Operational observations expose metadata and audit actual transaction outcomes."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event
from sqlmodel import Session, select

from app.admin_models import AdminAudit, AdminJobControl, AdminPresetJob
from app.analyst_models import AnalystJob
from app.models import Analysis, User
from tests.test_admin_auth import admin_app, login


def test_overview_timings_use_completed_utc_day_and_end_to_end_ai_duration(admin_app, monkeypatch):
    app, client = admin_app
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    monkeypatch.setattr('app.services.admin.utc_now', lambda: now)
    with Session(app.state.engine) as session:
        for wait, run in ((10, 20), (30, 60)):
            session.add(Analysis(owner_id=2, title='PRIVATE TITLE', input_manifest_json='{}', status='completed',
                submitted_at=now-timedelta(seconds=wait+run), started_at=now-timedelta(seconds=run), completed_at=now))
        # Missing and reversed timestamps must not create invented zero-duration samples.
        session.add(Analysis(owner_id=2, title='private', input_manifest_json='{}', status='completed', completed_at=now))
        session.add(Analysis(owner_id=2, title='private', input_manifest_json='{}', status='completed',
            submitted_at=now, started_at=now-timedelta(seconds=1), completed_at=now-timedelta(seconds=2)))
        session.add(Analysis(owner_id=2, title='old', input_manifest_json='{}', status='completed',
            submitted_at=now-timedelta(days=1,seconds=200), started_at=now-timedelta(days=1,seconds=100), completed_at=now-timedelta(days=1)))
        session.add(AnalystJob(owner_id=2, kind='report', status='completed', created_at=now-timedelta(seconds=100), updated_at=now))
        session.add(AnalystJob(owner_id=2, kind='message', status='completed', created_at=now-timedelta(seconds=200), updated_at=now))
        session.add(AnalystJob(owner_id=2, kind='prepare', status='completed', created_at=now-timedelta(seconds=999), updated_at=now))
        session.add(AnalystJob(owner_id=2, kind='report', status='running', created_at=now-timedelta(seconds=999), updated_at=now))
        session.add(AdminPresetJob(id='preset-timing', preset_id='quick-demo', status='completed', created_at=now-timedelta(seconds=300), updated_at=now))
        session.commit()
    response = client.get('/api/v1/admin/overview', headers=login(client))
    assert response.status_code == 200
    assert response.json()['timings'] == {
        'video_queue_seconds': {'count': 2, 'p50': 20, 'p95': 29},
        'video_execution_seconds': {'count': 2, 'p50': 40, 'p95': 58},
        'ai_total_seconds': {'count': 3, 'p50': 200, 'p95': 290},
    }
    assert 'PRIVATE TITLE' not in response.text


def test_overview_errors_use_coarse_allowlist_and_empty_timings_are_null(admin_app):
    app, client = admin_app
    with Session(app.state.engine) as session:
        for code, status in [('registration_count_mismatch','failed'), ('ENGINE_FAILED','failed'), ('/home/private/RAW_ERROR','failed'), (None,'interrupted')]:
            session.add(Analysis(owner_id=2, title='PRIVATE TITLE', input_manifest_json='{}', status=status, error_code=code, error_message='PRIVATE BODY /home/video'))
        session.add(AnalystJob(owner_id=2, kind='prepare', status='failed', error='PRIVATE PROVIDER FAILURE'))
        session.add(AnalystJob(owner_id=2, kind='message', status='failed', error='PRIVATE CHAT FAILURE'))
        session.add(AdminPresetJob(id='failed-preset', preset_id='quick-demo', status='failed'))
        session.commit()
    response = client.get('/api/v1/admin/overview', headers=login(client))
    assert response.status_code == 200
    errors = {(item['kind'],item['code']):item['count'] for item in response.json()['errors']}
    assert errors == {('video','registration_count_mismatch'):1, ('video','engine_failed'):1,
        ('video','unknown'):1, ('video','interrupted'):1, ('ai','preparation_failed'):1,
        ('ai','generation_failed'):1, ('preset','generation_failed'):1}
    assert all(item == {'count':0,'p50':None,'p95':None} for item in response.json()['timings'].values())
    assert all(secret not in response.text for secret in ('PRIVATE', '/home/', 'RAW_ERROR'))


def last_audit(client, headers):
    return client.get('/api/v1/admin/audit', headers=headers).json()['items'][0]


def test_settings_audit_records_before_after_and_applied_outcome(admin_app):
    app, client = admin_app
    headers = login(client)
    before = client.get('/api/v1/admin/settings', headers=headers).json()['current']
    response = client.patch('/api/v1/admin/settings', headers=headers, json={'ai_paused':True,'default_quotas':{'daily_ai':7},'reason':'  provider maintenance  '})
    assert response.status_code == 200
    record = last_audit(client, headers)
    assert record['reason'] == 'provider maintenance'
    assert record['changes'] == {'before':before,'after':response.json()['current'], 'outcome':{'status':'applied','http_status':200}}


def test_user_audit_tracks_active_session_and_quota_changes_without_identity_data(admin_app):
    app, client = admin_app
    headers = login(client)
    response = client.patch('/api/v1/admin/users/2', headers=headers, json={'is_active':False,'quotas':{'drafts':0},'reason':'temporary restriction'})
    assert response.status_code == 200
    changes = last_audit(client,headers)['changes']
    assert changes['before']['is_active'] is True and changes['after']['is_active'] is False
    assert changes['before']['session_version'] == 0 and changes['after']['session_version'] == 1
    assert changes['before']['quotas']['drafts'] == 3 and changes['after']['quotas']['drafts'] == 0
    assert all(key not in json.dumps(changes) for key in ('username','email','hashed_password','normal@example.com'))
    assert client.post('/api/v1/admin/users/2/force-logout',headers=headers,json={'reason':'revoke remaining sessions'}).status_code == 204
    changes = last_audit(client,headers)['changes']
    assert changes['before']['session_version'] == 1 and changes['after']['session_version'] == 2
    assert changes['outcome'] == {'status':'applied','http_status':204}


def test_job_audit_snapshots_metadata_and_rejected_batch_rolls_back(admin_app):
    app, client = admin_app
    headers = login(client)
    with Session(app.state.engine) as session:
        queued = Analysis(owner_id=2,title='PRIVATE TITLE',status='queued',input_manifest_json='{}')
        completed = Analysis(owner_id=2,title='PRIVATE TITLE',status='completed',input_manifest_json='{}',error_message='/home/private')
        session.add_all([queued,completed]);session.commit();ids=[queued.id,completed.id]
    response = client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'video','ids':[ids[0]],'action':'priority','priority':10,'reason':'operational priority'})
    assert response.status_code == 200
    applied = last_audit(client,headers)['changes']
    assert applied['before'][ids[0]] == {'status':'queued','held':False,'priority':0,'admin_retries':0,
                                       'submitted_at':None,'started_at':None,'completed_at':None}
    assert applied['after'][ids[0]] == {'status':'queued','held':False,'priority':10,'admin_retries':0,
                                      'submitted_at':None,'started_at':None,'completed_at':None}
    response = client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'video','ids':ids,'action':'hold','reason':'batch must be atomic'})
    assert response.status_code == 409
    record = last_audit(client,headers)
    assert record['reason'] == 'batch must be atomic'
    assert record['changes']['outcome'] == {'status':'rejected','http_status':409}
    assert record['changes']['before'] == record['changes']['after']
    with Session(app.state.engine) as session:
        assert session.get(AdminJobControl,('video',ids[0])).held is False
    assert 'PRIVATE' not in json.dumps(record) and '/home/' not in json.dumps(record)


@pytest.mark.parametrize(('path','payload'), [
    ('/settings',{'ai_concurrency':999,'reason':'over server cap'}),
    ('/users/2',{'is_active':False,'quotas':{'daily_ai':999999},'reason':'partial write must rollback'}),
    ('/users/9999',{'is_active':False,'reason':'missing identity'}),
])
def test_valid_admin_payload_rejections_are_audited_without_partial_writes(admin_app,path,payload):
    app, client = admin_app
    headers = login(client)
    response = client.patch('/api/v1/admin'+path,headers=headers,json=payload)
    assert response.status_code in (404,422)
    record = last_audit(client,headers)
    assert record['reason'] == payload['reason']
    assert record['changes']['outcome'] == {'status':'rejected','http_status':response.status_code}
    assert record['changes']['before'] == record['changes']['after']
    with Session(app.state.engine) as session:
        assert session.get(User,2).is_active is True
        assert session.get(User,2).session_version == 0


def test_unauthorized_or_schema_invalid_requests_do_not_enter_operator_audit(admin_app):
    app, client = admin_app
    headers = login(client)
    assert client.patch('/api/v1/admin/settings',headers={**headers,'Origin':'https://evil.invalid'},json={'ai_paused':True,'reason':'unauthorized origin'}).status_code == 403
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'arbitrary':'PRIVATE','reason':'invalid schema'}).status_code == 422
    with Session(app.state.engine) as session:
        assert session.exec(select(AdminAudit)).all() == []
