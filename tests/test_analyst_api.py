import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis, User


@pytest.fixture
def analyst_client(tmp_path):
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'app.db'}", runtime_root=tmp_path / 'runtime', sample_root=tmp_path / 'samples', admin_username='admin', admin_password='correct-password', jwt_secret_key='test-secret-with-at-least-thirty-two-characters', worker_enabled=False, auto_create_schema=True, min_free_storage_gb=0)
    with TestClient(create_app(settings=settings)) as client:
        assert client.post('/api/v1/login/access-token', data={'username':'admin','password':'correct-password'}).status_code == 200
        with Session(client.app.state.engine) as session:
            owner = session.exec(select(User)).first()
            task = Analysis(title='训练', owner_id=owner.id, input_manifest_json='{}', status='completed')
            session.add(task); session.commit(); session.refresh(task)
            client.task_id = task.id
        out = client.app.state.storage.analysis_root(client.task_id) / 'output'
        out.mkdir(parents=True)
        (out/'report.json').write_text(json.dumps({'clips':[{'clip_id':'stu_03:0','student_id':'stu_03','action_type':'jump_shot','start_ms':1000,'release_ms':1500,'end_ms':2000}], 'shot_outcomes':[{'clip_id':'stu_03:0','student_id':'stu_03','made':True,'confidence':.9}], 'shot_stats':{'attempts':1,'makes':1,'misses':0,'undetermined':0}}))
        (out/'summary.json').write_text(json.dumps({'student_ids':['stu_03']}))
        yield client


def test_missing_key_is_explicit_without_breaking_completed_task(analyst_client):
    client=analyst_client
    response=client.get(f'/api/v1/tasks/{client.task_id}/analyst/report')
    assert response.status_code == 200
    assert response.json()['status'] == 'disabled'
    assert response.json()['report'] is None
    assert client.get(f'/api/v1/tasks/{client.task_id}').json()['status'] == 'completed'


def test_report_and_conversation_reject_other_owner(analyst_client):
    client=analyst_client
    client.post('/api/v1/register',json={'username':'outsider','email':'outside@example.com','password':'another-password'})
    client.post('/api/v1/login/access-token',data={'username':'outsider','password':'another-password'})
    assert client.get(f'/api/v1/tasks/{client.task_id}/analyst/report').status_code == 404
    assert client.post('/api/v1/analyst/conversations',json={'task_id':client.task_id}).status_code == 404


def test_report_request_without_key_never_queues_fake_completion(analyst_client):
    response=analyst_client.post(f'/api/v1/tasks/{analyst_client.task_id}/analyst/report',json={'locale':'zh','style':'coach'})
    assert response.status_code == 503


def test_real_report_lifecycle_and_idempotent_retry(analyst_client):
    from pydantic import SecretStr
    from app.services.analyst import AnalystSupervisor
    from app.services.glm import GlmJsonResult
    client = analyst_client
    client.app.state.settings.glm_api_key = SecretStr('test-only-key')
    class Provider:
        async def complete_json(self, messages, request_id):
            return GlmJsonResult(data={'summary':'这次出手值得重看','highlights':[{'text':'回看这一球','evidence_ids':['event-1']}],'players':[],'comparison':None,'suggestions':['下次继续练习稳定出手']},usage={'total_tokens':42})
    client.app.state.glm_client = Provider()
    url = f'/api/v1/tasks/{client.task_id}/analyst/report'
    first = client.post(url,json={'locale':'zh','style':'coach'})
    assert first.status_code == 202
    assert first.json()['status'] == 'queued'
    assert client.post(url,json={}).json()['status'] == 'queued'
    assert asyncio.run(AnalystSupervisor(client.app).run_once()) is True
    completed = client.get(url).json()
    assert completed['status'] == 'completed'
    assert completed['report']['model'] == 'glm-5.3'
    assert completed['report']['highlights'][0]['evidence_ids'] == ['event-1']
    assert asyncio.run(AnalystSupervisor(client.app).run_once()) is False
    assert client.get(f'/api/v1/tasks/{client.task_id}').json()['status'] == 'completed'


def test_conversation_messages_restore_and_stream_saved_snapshots(analyst_client):
    from pydantic import SecretStr
    from app.services.analyst import AnalystSupervisor
    from app.services.glm import GlmTextDelta, GlmUsage
    client = analyst_client
    client.app.state.settings.glm_api_key = SecretStr('test-only-key')
    class Provider:
        async def stream(self,messages,request_id):
            yield GlmTextDelta(text='先看这一球 ')
            yield GlmTextDelta(text='[event-1]')
            yield GlmUsage(usage={'total_tokens':11})
    client.app.state.glm_client = Provider()
    created = client.post('/api/v1/analyst/conversations',json={'task_id':client.task_id})
    assert created.status_code == 201
    url = '/api/v1/analyst/conversations/' + created.json()['id']
    sent = client.post(url+'/messages',json={'content':'哪球值得重看','request_id':'once'})
    assert sent.status_code == 202
    duplicate = client.post(url+'/messages',json={'content':'哪球值得重看','request_id':'once'})
    assert duplicate.json() == sent.json()
    assert client.post(url+'/messages',json={'content':'different','request_id':'once'}).status_code == 409
    asyncio.run(AnalystSupervisor(client.app).run_once())
    restored = client.get(url).json()['messages']
    assert len(restored) == 2
    assert restored[-1]['content'] == '先看这一球 [event-1]'
    assert restored[-1]['citations'] == ['event-1']
    events = client.get(url+'/events')
    assert events.headers['content-type'].startswith('text/event-stream')
    assert 'event: message' in events.text and 'event: done' in events.text
    assert '先看这一球' in events.text
