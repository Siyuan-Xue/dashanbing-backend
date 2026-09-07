import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from sqlmodel import Session, select

from app.models import Analysis
from app.analyst_models import AnalystJob
from app.services.supervisor import AnalysisSupervisor
from tests.test_admin_auth import admin_app, login


def test_application_ai_cap_allows_lowering_but_never_more_than_eight(admin_app):
    import pytest
    from pydantic import ValidationError
    from app.config import AppSettings
    from app.services.admin import current_settings
    from app.admin_models import AdminSettings
    app, client = admin_app
    for value in (0, 9, 64):
        with pytest.raises(ValidationError):
            AppSettings(_env_file=None, analyst_concurrency_cap=value)
    for value in range(1, 9):
        assert AppSettings(_env_file=None, analyst_concurrency_cap=value).analyst_concurrency_cap == value
    app.state.settings.analyst_concurrency_cap = 2
    with Session(app.state.engine) as session:
        stored = session.get(AdminSettings, 1)
        values = json.loads(stored.values_json); values['ai_concurrency'] = 64
        stored.values_json = json.dumps(values); session.add(stored); session.commit()
        assert current_settings(session, app.state.settings)['ai_concurrency'] == 2
    headers = login(client)
    assert client.patch('/api/v1/admin/settings', headers=headers,
        json={'ai_concurrency':3,'reason':'exceeds reduced cap'}).status_code == 422
    assert client.get('/api/v1/admin/settings', headers=headers).json()['bounds']['ai_concurrency'] == {'min':1,'max':2}


def test_video_pause_hold_priority_and_single_claim(admin_app):
    app, client = admin_app
    headers = login(client)
    with Session(app.state.engine) as s:
        rows=[Analysis(owner_id=2,title='private',input_manifest_json='{}',status='queued') for _ in range(2)]
        s.add_all(rows); s.commit(); ids=[r.id for r in rows]
    assert client.post('/api/v1/admin/jobs/actions',headers=headers,json={'reason':'test operation','kind':'video','ids':[ids[0]],'action':'hold'}).status_code == 200
    supervisor=AnalysisSupervisor(app)
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'reason':'test operation','video_paused':True}).status_code == 200
    assert supervisor._next_queued_id() is None
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'reason':'test operation','video_paused':False}).status_code == 200
    with ThreadPoolExecutor(2) as pool:
        claimed=list(pool.map(lambda _: AnalysisSupervisor(app)._next_queued_id(), range(2)))
    assert claimed.count(ids[1]) == 1 and claimed.count(None) == 1


def test_ai_global_capacity_persistent_hold_and_read_does_not_claim(admin_app):
    app, client=admin_app
    headers=login(client)
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'reason':'test operation','ai_concurrency':1}).status_code == 200
    from app.services.admin_scheduling import claim_ai, release_lease
    with Session(app.state.engine) as s:
        jobs=[AnalystJob(owner_id=2,kind='prepare') for _ in range(2)]
        s.add_all(jobs);s.commit();ids=[j.id for j in jobs]
    assert client.get('/api/v1/admin/jobs',headers=headers).status_code == 200
    one=claim_ai(app)
    assert one is not None
    assert claim_ai(app) is None
    release_lease(app.state.engine, 'ai',one)
    assert client.patch('/api/v1/admin/settings',headers=headers,json={'reason':'test operation','ai_paused':True}).status_code == 200
    assert claim_ai(app) is None


def test_personal_quota_changes_new_admission_only(admin_app):
    app,client=admin_app
    headers=login(client)
    assert client.patch('/api/v1/admin/users/2',headers=headers,json={'reason':'test operation','quotas':{'drafts':0,'daily_video':0}}).status_code == 200
    normal=login(client,False)
    usage=client.get('/api/v1/account/usage',headers=normal).json()
    assert usage['drafts']['limit']==0 and usage['submitted_today']['limit']==0
    assert client.post('/api/v1/tasks',headers=normal,json={'title':'blocked'}).status_code==429
    assert client.get('/api/v1/account/limits',headers=normal).json()['quotas']['drafts']==0


def test_retry_rejects_success_missing_inputs_and_batch_rolls_back(admin_app):
    app,client=admin_app
    headers=login(client)
    with Session(app.state.engine) as s:
        rows=[Analysis(owner_id=2,title='private',input_manifest_json='{}',status=status) for status in ('failed','completed')]
        s.add_all(rows);s.commit();ids=[r.id for r in rows]
    response=client.post('/api/v1/admin/jobs/actions',headers=headers,json={'reason':'test operation','kind':'video','ids':ids,'action':'retry'})
    assert response.status_code==409
    with Session(app.state.engine) as s:
        assert s.get(Analysis,ids[0]).status=='failed'


def test_actual_ai_attempt_budget_and_additional_retries(admin_app):
    app,client=admin_app
    from app.admin_models import AdminJobControl, AdminRepairDay
    from app.services.admin_scheduling import record_ai_attempt
    from app.models import utc_now
    with Session(app.state.engine) as s:
        job=AnalystJob(owner_id=2,kind='report',status='running')
        s.add(job);s.flush();jid=job.id
        s.add(AdminJobControl(kind='ai',job_id=jid,repair=True))
        day=utc_now().date().isoformat()
        s.add(AdminRepairDay(utc_date=day,ai_used=99))
        s.commit()
    assert record_ai_attempt(app,'ai',jid) is True
    assert record_ai_attempt(app,'ai',jid) is False
    with Session(app.state.engine) as s:
        assert s.get(AdminRepairDay,day).ai_used==100
        assert s.get(AnalystJob,jid).attempts==1


def test_admin_video_repair_does_not_charge_ordinary_unfinished_quota(admin_app):
    app,client=admin_app
    from app.admin_models import AdminJobControl
    from app.services.tasks import enforce_unfinished_quota
    headers=login(client)
    client.patch('/api/v1/admin/users/2',headers=headers,json={'quotas':{'unfinished':1},'reason':'repair exemption'})
    with Session(app.state.engine) as s:
        task=Analysis(owner_id=2,title='repair',status='queued',input_manifest_json='{}');s.add(task);s.flush()
        s.add(AdminJobControl(kind='video',job_id=task.id,repair=True));s.commit()
        enforce_unfinished_quota(s,2)
    normal=login(client,False)
    assert client.get('/api/v1/account/usage',headers=normal).json()['unfinished_tasks']['used']==0


def test_video_priority_and_utc_repair_limit_persist(admin_app,tmp_path):
    app,client=admin_app
    from app.admin_models import AdminJobControl,AdminRepairDay
    from app.services.admin_scheduling import claim_video,release_lease
    from app.models import utc_now
    with Session(app.state.engine) as s:
        rows=[Analysis(owner_id=2,title='job',status='queued',input_manifest_json='{}') for _ in range(2)]
        s.add_all(rows);s.flush();ids=[r.id for r in rows]
        s.add(AdminJobControl(kind='video',job_id=ids[1],priority=80,repair=True))
        s.add(AdminRepairDay(utc_date=utc_now().date().isoformat(),video_used=19));s.commit()
    assert claim_video(app)==ids[1]
    release_lease(app.state.engine,'video',ids[1])
    assert claim_video(app)==ids[0]
    with Session(app.state.engine) as s:
        assert s.get(AdminRepairDay,utc_now().date().isoformat()).video_used==20


def test_repair_allows_only_three_extra_attempts_and_preserves_request_and_success(admin_app):
    app,client=admin_app
    from app.analyst_models import AnalystReport
    from app.services.analyst import pack
    from app.admin_models import AdminJobControl
    headers=login(client)
    with Session(app.state.engine) as s:
        report=AnalystReport(owner_id=2,cache_key='original',status='failed')
        s.add(report);s.flush()
        job=AnalystJob(owner_id=2,kind='report',report_id=report.id,request_id='original-request',status='failed',attempts=3,payload_json=pack({'facts':{'subjects':[],'evidence':[]}}))
        s.add(job);s.commit();jid=job.id;rid=report.id
    for count in range(3):
        response=client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'ai','ids':[jid],'action':'retry','reason':'provider repaired'})
        assert response.status_code==200,response.text
        with Session(app.state.engine) as s:
            job=s.get(AnalystJob,jid);report=s.get(AnalystReport,rid)
            assert job.request_id=='original-request' and job.attempts==3+count
            job.attempts+=1;job.status='failed';report.status='failed'
            s.add(job);s.add(report);s.commit()
    assert client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'ai','ids':[jid],'action':'retry','reason':'fourth retry blocked'}).status_code==409
    with Session(app.state.engine) as s:
        assert s.get(AdminJobControl,('ai',jid)).admin_retries==3


def test_one_ai_attempt_per_invocation_even_after_claim_restart(admin_app):
    app,client=admin_app
    from app.services.admin_scheduling import claim_ai,record_ai_attempt,provider_backoff
    from app.analyst_models import AnalystReport
    from datetime import timedelta
    from app.models import utc_now
    with Session(app.state.engine) as s:
        report=AnalystReport(owner_id=2,cache_key='backoff',status='queued');s.add(report);s.flush()
        job=AnalystJob(owner_id=2,kind='report',report_id=report.id);s.add(job);s.commit();jid=job.id
    assert claim_ai(app)==jid
    provider_backoff(app.state.engine,utc_now()+timedelta(seconds=60))
    assert record_ai_attempt(app,'ai',jid) is False
    with Session(app.state.engine) as s:
        assert s.get(AnalystJob,jid).attempts==0


def test_backfill_uses_original_expected_locale_and_subjects_only(admin_app,monkeypatch):
    app,client=admin_app
    from app.analyst_models import AnalystReport
    from app.services.analyst import AnalystSupervisor,pack
    from app.analyst_schemas import AnalystFacts
    from pydantic import SecretStr
    # Only the external facts loader is substituted; queue writes are real SQLite.
    from app import analyst_schemas
    facts=AnalystFacts()
    monkeypatch.setattr('app.services.analyst_facts.load_task_facts',lambda *args: facts)
    app.state.settings.glm_api_key=SecretStr('synthetic-test-key')
    headers=login(client)
    with Session(app.state.engine) as s:
        task=Analysis(owner_id=2,title='completed',status='completed',analyst_locale='en',input_manifest_json='{}')
        s.add(task);s.flush()
        prep=AnalystJob(owner_id=2,task_id=task.id,kind='prepare',status='completed',payload_json=pack({'automatic':True,'collection_version':1,'locale':'zh','subjects':[]}))
        s.add(prep);s.commit();jid=prep.id
    response=client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'ai','ids':[jid],'action':'backfill','reason':'missing original reports'})
    assert response.status_code==200,response.text
    assert asyncio.run(AnalystSupervisor(app).run_once()) is True
    with Session(app.state.engine) as s:
        reports=s.exec(select(AnalystReport)).all()
        assert len(reports)==2 and {r.locale for r in reports}=={'zh'}
        from app.admin_models import AdminJobControl
        children=s.exec(select(AnalystJob).where(AnalystJob.kind=='report')).all()
        assert all(s.get(AdminJobControl,('ai',j.id)).repair for j in children)


def test_inherited_video_lock_blocks_replacement_worker(admin_app):
    app,client=admin_app
    import subprocess
    import sys
    from app.services.admin_scheduling import claim_video,release_lease
    with Session(app.state.engine) as s:
        task=Analysis(owner_id=2,title='queued',status='queued',input_manifest_json='{}');s.add(task);s.commit();tid=task.id
    assert claim_video(app)==tid
    fds=tuple(getattr(app.state,'video_worker_lock_fds',()))
    # The child keeps both the global GPU mutex and its durable claim's liveness lock.
    assert len(fds)==2
    child=subprocess.Popen([sys.executable,'-c','import sys; sys.stdin.read()'],stdin=subprocess.PIPE,pass_fds=fds)
    try:
        release_lease(app.state.engine,'video',tid)
        assert claim_video(app) is None
    finally:
        child.communicate(timeout=5)
    assert claim_video(app)==tid
    release_lease(app.state.engine,'video',tid)
