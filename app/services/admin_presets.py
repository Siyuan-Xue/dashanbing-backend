"""Preset generation uses the same durable provider capacity as reports and chat."""
import asyncio
import json
import os
from datetime import timedelta, timezone
from uuid import uuid4

from sqlmodel import Session, select

from app.admin_models import AdminPresetJob, AdminJobControl
from app.models import utc_now
from app.services.analyst import digest, pack, system_prompt, validate_report, AnalystSupervisor, MAX_ATTEMPTS
from app.services.analyst_collections import preset_report_path
from app.services.admin_scheduling import claim_preset, record_ai_attempt, release_lease, mark_interrupted


def enqueue_preset(app,preset_id,facts,*,locale,style,subject_id=None):
    if locale not in {'zh','en'} or style not in {'coach','roast'}:
        raise ValueError('Unsupported preset variant')
    key=digest(dict(preset=preset_id,locale=locale,style=style,subject_id=subject_id))
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        if session.get(AdminPresetJob,key) is None:
            session.add(AdminPresetJob(id=key,preset_id=preset_id,payload_json=pack(dict(facts=facts,memory={},locale=locale,style=style,
                subject_id=subject_id,model=app.state.settings.glm_model))))
        session.commit()
    return key


def next_preset(app):
    with Session(app.state.engine) as session:
        from app.services.admin_scheduling import _ordered
        rows=_ordered(session,'preset',AdminPresetJob,[AdminPresetJob.status=='queued',AdminPresetJob.available_at<=utc_now()])
        return rows[0].id if rows else None


def _finish(app,job_id,*,usage=None,failed=False):
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        job=session.get(AdminPresetJob,job_id)
        if job and job.status=='running':
            job.status='failed' if failed else 'completed'
            job.updated_at=utc_now()
            if usage is not None:
                job.usage_json=pack(usage)
            session.add(job);session.commit()


async def run_preset(app,job_id):
    if not claim_preset(app,job_id):
        return False
    attempted = False
    try:
        with Session(app.state.engine) as session:
            job=session.get(AdminPresetJob,job_id)
            payload=json.loads(job.payload_json)
        destination=preset_report_path(app.state.settings,job.preset_id,payload['locale'],payload['style'],payload.get('subject_id'))
        if destination.exists():
            saved=json.loads(destination.read_text(encoding='utf-8'))
            valid=(saved.get('verified') is True and saved.get('facts_hash')==digest(payload['facts']) and
                   saved.get('subject_id')==payload.get('subject_id') and saved['report']['model']==payload['model'] and
                   saved['report']['locale']==payload['locale'] and saved['report']['style']==payload['style'])
            if valid:
                validate_report({k:v for k,v in saved['report'].items() if k in {'summary','highlights','players','comparison','suggestions'}},payload['facts'],{})
            _finish(app,job_id,failed=not valid)
            return True
        if not record_ai_attempt(app,'preset',job_id):
            return False
        attempted = True
        response=await asyncio.wait_for(AnalystSupervisor(app)._provider().complete_json([
            {'role':'system','content':system_prompt(payload,report=True)},
            {'role':'user','content':pack({'facts':payload['facts'],'memory':{}})}],request_id=job_id),
            timeout=app.state.settings.glm_timeout_seconds)
        body=validate_report(response.data,payload['facts'],{})
        report={**body.model_dump(),'id':str(uuid4()),'model':payload['model'],'locale':payload['locale'],'style':payload['style'],'created_at':utc_now().isoformat()}
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name('.'+destination.name+'.'+str(uuid4())+'.tmp')
        try:
            temporary.write_text(json.dumps(dict(verified=True,subject_id=payload.get('subject_id'),facts_hash=digest(payload['facts']),report=report,usage=response.usage),ensure_ascii=False,indent=2),encoding='utf-8')
            # Atomic create without replace: even an external writer's successful file is preserved.
            os.link(temporary,destination)
        finally:
            temporary.unlink(missing_ok=True)
        _finish(app,job_id,usage=response.usage)
    except asyncio.CancelledError:
        mark_interrupted(app.state.engine,'preset',job_id)
        raise
    except Exception as error:
        from pydantic import ValidationError
        with Session(app.state.engine) as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            current=session.get(AdminPresetJob,job_id)
            ctl=session.get(AdminJobControl,('preset',job_id))
            retry=attempted and (getattr(error,'retryable',False) or isinstance(error,(ValueError,ValidationError,asyncio.TimeoutError))) and current.attempts<MAX_ATTEMPTS and not (ctl and ctl.repair)
            delay=max(30*2**max(0,current.attempts-1),getattr(error,'retry_after_seconds',None) or 0) if getattr(error,'code',None)=='rate_limited' else 2**current.attempts
            current.status='queued' if retry else 'failed'
            current.available_at=utc_now()+timedelta(seconds=delay);current.updated_at=utc_now()
            if getattr(error,'code',None)=='rate_limited':
                from app.analyst_models import AnalystProviderState
                provider=session.get(AnalystProviderState,'glm') or AnalystProviderState(provider='glm')
                provider.available_at=max(provider.available_at.replace(tzinfo=timezone.utc),current.available_at)
                session.add(provider)
            session.add(current);session.commit()
    finally:
        release_lease(app.state.engine,'preset',job_id)
    return True
