import asyncio
from datetime import timedelta
from types import SimpleNamespace

from sqlmodel import Session, select

from app.models import utc_now
from app.analyst_models import AnalystJob
from tests.test_admin_auth import admin_app, login


def test_preset_and_report_share_global_capacity_and_provider_backoff(admin_app):
    app,client=admin_app
    from app.services.admin_presets import enqueue_preset
    from app.services.admin_scheduling import claim_ai,claim_preset,release_lease,provider_backoff
    from app.analyst_schemas import AnalystFacts
    headers=login(client)
    client.patch('/api/v1/admin/settings',headers=headers,json={'ai_concurrency':1,'reason':'capacity test'})
    pid=enqueue_preset(app,'quick-demo',AnalystFacts().model_dump(),locale='zh',style='coach')
    assert enqueue_preset(app,'quick-demo',AnalystFacts().model_dump(),locale='zh',style='coach')==pid
    with Session(app.state.engine) as s:
        job=AnalystJob(owner_id=2,kind='prepare');s.add(job);s.commit();jid=job.id
    assert claim_ai(app)==jid
    assert claim_preset(app,pid) is False
    release_lease(app.state.engine,'ai',jid)
    provider_backoff(app.state.engine,utc_now()+timedelta(seconds=60))
    assert claim_preset(app,pid) is False


def test_preset_generation_never_overwrites_and_counts_actual_attempts(admin_app):
    app,client=admin_app
    from app.services.admin_presets import enqueue_preset,run_preset
    from app.admin_models import AdminPresetJob,AdminAttempt
    from app.analyst_schemas import AnalystFacts
    calls=[]
    class Provider:
        async def complete_json(self,*args,**kwargs):
            calls.append(kwargs['request_id'])
            return SimpleNamespace(data={'summary':'verified','highlights':[],'players':[],'comparison':None,'suggestions':[]},usage={'total_tokens':5})
    app.state.glm_client=Provider()
    pid=enqueue_preset(app,'quick-demo',AnalystFacts().model_dump(),locale='zh',style='coach')
    assert asyncio.run(run_preset(app,pid)) is True
    path=app.state.settings.runtime_root/'analyst-presets'/'quick-demo'/'zh-coach.json'
    original=path.read_bytes()
    assert asyncio.run(run_preset(app,pid)) is False
    assert len(calls)==1 and path.read_bytes()==original
    with Session(app.state.engine) as s:
        assert s.get(AdminPresetJob,pid).status=='completed'
        assert len(s.exec(select(AdminAttempt).where(AdminAttempt.job_id==pid)).all())==1


def test_restart_does_not_reclaim_live_lease_or_reset_attempts(admin_app):
    app,client=admin_app
    from app.services.admin_scheduling import claim_ai,release_lease
    from app.services.analyst import AnalystSupervisor
    with Session(app.state.engine) as s:
        job=AnalystJob(owner_id=2,kind='prepare',attempts=2);s.add(job);s.commit();jid=job.id
    assert claim_ai(app)==jid
    # Startup recovery must preserve another supervisor's live claim.
    async def startup():
        supervisor=AnalystSupervisor(app)
        await supervisor.start()
        await supervisor.stop()
    asyncio.run(startup())
    with Session(app.state.engine) as s:
        assert s.get(AnalystJob,jid).status=='running'
        assert s.get(AnalystJob,jid).attempts==3
    assert claim_ai(app) is None
    release_lease(app.state.engine,'ai',jid)


def test_running_reports_continue_during_pause_and_no_new_provider_request_starts(admin_app):
    app,client=admin_app
    from app.analyst_models import AnalystReport
    from app.services.analyst import AnalystSupervisor,pack
    from app.analyst_schemas import AnalystFacts
    headers=login(client)
    client.patch('/api/v1/admin/settings',headers=headers,json={'ai_concurrency':1,'reason':'capacity test'})
    with Session(app.state.engine) as s:
        for number in range(2):
            report=AnalystReport(owner_id=2,cache_key=f'key-{number}',status='queued')
            s.add(report);s.flush()
            s.add(AnalystJob(owner_id=2,kind='report',report_id=report.id,payload_json=pack({'facts':AnalystFacts().model_dump(),'memory':{},'locale':'zh','style':'coach'})))
        s.commit()
    async def scenario():
        started=asyncio.Event();release=asyncio.Event();calls=[]
        class Provider:
            async def complete_json(self,*args,**kwargs):
                calls.append(kwargs.get('request_id'));started.set();await release.wait()
                return SimpleNamespace(data={'summary':'done','highlights':[],'players':[],'comparison':None,'suggestions':[]},usage={'total_tokens':1})
        app.state.glm_client=Provider()
        running=asyncio.create_task(AnalystSupervisor(app).run_once())
        await asyncio.wait_for(started.wait(),timeout=2)
        response=client.patch('/api/v1/admin/settings',headers=headers,json={'ai_paused':True,'reason':'keep current job'})
        assert response.status_code==200
        assert await AnalystSupervisor(app).run_once() is False
        release.set()
        assert await running is True
        return calls
    assert len(asyncio.run(scenario()))==1
    with Session(app.state.engine) as s:
        assert len(s.exec(select(AnalystReport).where(AnalystReport.status=='completed')).all())==1
        assert len(s.exec(select(AnalystJob).where(AnalystJob.status=='queued')).all())==1


def test_completed_preset_missing_original_file_can_be_backfilled(admin_app):
    app,client=admin_app
    from app.services.admin_presets import enqueue_preset
    from app.admin_models import AdminPresetJob
    from app.analyst_schemas import AnalystFacts
    pid=enqueue_preset(app,'quick-demo',AnalystFacts().model_dump(),locale='zh',style='coach')
    with Session(app.state.engine) as s:
        row=s.get(AdminPresetJob,pid);row.status='completed';s.add(row);s.commit()
    headers=login(client)
    response=client.post('/api/v1/admin/jobs/actions',headers=headers,json={'kind':'preset','ids':[pid],'action':'backfill','reason':'restore missing original variant'})
    assert response.status_code==200,response.text


def test_preexisting_verified_preset_is_reused_without_provider_request(admin_app):
    app,client=admin_app
    import json
    from app.services.admin_presets import enqueue_preset,run_preset
    from app.services.analyst import digest
    from app.admin_models import AdminPresetJob
    from app.analyst_schemas import AnalystFacts
    facts=AnalystFacts().model_dump()
    path=app.state.settings.runtime_root/'analyst-presets'/'quick-demo'/'zh-coach.json'
    path.parent.mkdir(parents=True)
    saved={'verified':True,'facts_hash':digest(facts),'subject_id':None,'report':{'id':'existing-id','model':'glm-5.3','locale':'zh','style':'coach','created_at':utc_now().isoformat(),'summary':'keep','highlights':[],'players':[],'comparison':None,'suggestions':[]}}
    path.write_text(json.dumps(saved))
    pid=enqueue_preset(app,'quick-demo',facts,locale='zh',style='coach')
    assert asyncio.run(run_preset(app,pid)) is True
    with Session(app.state.engine) as s:
        assert s.get(AdminPresetJob,pid).status=='completed'
        assert s.get(AdminPresetJob,pid).attempts==0
    assert json.loads(path.read_text())==saved
