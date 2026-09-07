from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import AppSettings
from app.main import create_app
from app.models import User, Analysis, ApiKey
from app.security import api_key_digest


@pytest.fixture
def admin_app(tmp_path):
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'admin.db'}", runtime_root=tmp_path / 'runtime',
        sample_root=tmp_path / 'samples', model_root=tmp_path / 'models', frontend_dist=tmp_path / 'frontend',
        admin_password='correct-password', jwt_secret_key='test-secret-with-at-least-thirty-two-characters',
        simulation_mode=True, worker_enabled=False, analyst_worker_enabled=False, auto_create_schema=True)
    app = create_app(settings=settings)
    with TestClient(app) as client:
        client.post('/api/v1/register', json={'username':'normal', 'email':'normal@example.com', 'password':'normal-password', 'role':'admin'})
        yield app, client


def login(client, admin=True):
    response = client.post('/api/v1/login/access-token', data={'username':'admin' if admin else 'normal', 'password':'correct-password' if admin else 'normal-password'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token'], 'Origin':'http://testserver'}


def test_roles_are_exclusive_and_registration_cannot_elevate(admin_app):
    app, client = admin_app
    headers = login(client)
    assert client.get('/api/v1/users/me', headers=headers).json()['role'] == 'admin'
    assert client.get('/api/v1/tasks', headers=headers).status_code == 403
    assert client.get('/api/v1/admin/overview', headers=headers).status_code == 200
    normal = login(client, False)
    assert client.get('/api/v1/users/me', headers=normal).json()['role'] == 'user'
    assert client.get('/api/v1/admin/overview', headers=normal).status_code == 403


def test_admin_mutations_validate_origin_and_force_logout(admin_app):
    app, client = admin_app
    user_headers = login(client, False)
    admin_headers = login(client)
    assert client.patch('/api/v1/admin/settings', headers={**admin_headers, 'Origin':'https://evil.example'}, json={'reason':'test operation','ai_paused':True}).status_code == 403
    assert client.patch('/api/v1/admin/settings', headers={'Authorization':admin_headers['Authorization']}, json={'reason':'test operation','ai_paused':True}).status_code == 403
    assert client.post('/api/v1/admin/users/2/force-logout', headers=admin_headers,json={'reason':'test force logout'}).status_code == 204
    assert client.get('/api/v1/users/me', headers=user_headers).status_code == 401
    assert client.post('/api/v1/logout', headers=admin_headers).status_code == 204
    assert client.get('/api/v1/users/me', headers=admin_headers).status_code == 401


def test_admin_reads_are_metadata_only_and_side_effect_free(admin_app):
    app, client = admin_app
    headers = login(client)
    with Session(app.state.engine) as session:
        session.add(Analysis(owner_id=2, title='PRIVATE TITLE', status='failed', input_manifest_json='{"secret":"/home/private"}', error_message='PRIVATE RAW ERROR'))
        session.commit()
    from sqlalchemy import event
    writes = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE','REPLACE','CREATE','DROP'}:
            writes.append(statement)
    event.listen(app.state.engine, 'before_cursor_execute', observe)
    for endpoint in ('overview', 'users', 'settings', 'jobs', 'audit', 'deployment'):
        response = client.get('/api/v1/admin/' + endpoint, headers=headers)
        assert response.status_code == 200, response.text
        assert all(secret not in response.text for secret in ('PRIVATE TITLE','PRIVATE RAW ERROR','/home/private','hashed_password','glm_api_key'))
    event.remove(app.state.engine, 'before_cursor_execute', observe)
    assert writes == []


def test_bounds_and_no_dangerous_admin_mutations(admin_app):
    app, client = admin_app
    headers = login(client)
    assert client.patch('/api/v1/admin/settings', headers=headers, json={'reason':'test operation','ai_concurrency':999}).status_code == 422
    assert client.patch('/api/v1/admin/users/2', headers=headers, json={'reason':'test operation','role':'admin'}).status_code == 422
    assert client.post('/api/v1/admin/jobs/actions', headers=headers, json={'reason':'test operation','kind':'video','ids':['x'],'action':'delete'}).status_code == 422
    assert client.post('/api/v1/admin/deployment', headers=headers).status_code == 405


def test_existing_database_does_not_promote_first_user_or_check_env_password(admin_app):
    app, client = admin_app
    from app.main import _bootstrap_admin
    with Session(app.state.engine) as session:
        user = session.get(User, 1)
        user.role = 'user'
        session.add(user); session.commit()
    app.state.settings.admin_password = 'different-password'
    assert _bootstrap_admin(app) is True
    with Session(app.state.engine) as session:
        assert session.get(User, 1).role == 'user'


def test_admin_api_keys_are_rejected_without_last_used_write(admin_app):
    app, client = admin_app
    from app.models import utc_now
    secret = 'dsb_live_synthetic_test_key'
    with Session(app.state.engine) as session:
        key = ApiKey(owner_id=1,name='synthetic',prefix='dsb_live_',last_four='test',digest=api_key_digest(secret,app.state.settings.jwt_secret_key),expires_at=utc_now()+timedelta(days=1))
        session.add(key); session.commit(); key_id=key.id
    for path in ('admin/overview','tasks','users/me'):
        assert client.get('/api/v1/'+path,headers={'Authorization':'Bearer '+secret}).status_code in (401,403)
    with Session(app.state.engine) as session:
        assert session.get(ApiKey,key_id).last_used_at is None


def test_mutation_reason_is_required_trimmed_and_audited(admin_app):
    app,client=admin_app
    headers=login(client)
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'ai_paused':True}).status_code==422
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'ai_paused':True,'reason':'   '}).status_code==422
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'ai_paused':True,'reason':'  provider maintenance  '}).status_code==200
    rows=client.get('/api/v1/admin/audit',headers=headers).json()['items']
    assert rows[0]['reason']=='provider maintenance'


def test_inactive_and_stale_admin_sessions_are_rejected(admin_app):
    app,client=admin_app
    headers=login(client)
    with Session(app.state.engine) as s:
        admin=s.get(User,1);admin.is_active=False;s.add(admin);s.commit()
    assert client.get('/api/v1/admin/settings',headers=headers).status_code==401
    with Session(app.state.engine) as s:
        admin=s.get(User,1);admin.is_active=True;admin.session_version+=1;s.add(admin);s.commit()
    assert client.get('/api/v1/admin/settings',headers=headers).status_code==401


def test_api_keys_cannot_reach_admin_reads_without_usage_side_effect(admin_app):
    app,client=admin_app
    from app.models import utc_now
    secret='dsb_live_normal_user_test'
    with Session(app.state.engine) as s:
        key=ApiKey(owner_id=2,name='synthetic',prefix='dsb_live_',last_four='test',digest=api_key_digest(secret,app.state.settings.jwt_secret_key),expires_at=utc_now()+timedelta(days=1))
        s.add(key);s.commit();key_id=key.id
    assert client.get('/api/v1/admin/jobs',headers={'Authorization':'Bearer '+secret}).status_code==403
    with Session(app.state.engine) as s:
        assert s.get(ApiKey,key_id).last_used_at is None
