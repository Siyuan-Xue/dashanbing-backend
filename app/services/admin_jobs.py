"""Explicit operations allowlist; retries reuse original durable identities."""
import json
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import select

from app.admin_models import AdminJobControl, AdminPresetJob, AdminLease
from app.analyst_models import AnalystJob, AnalystReport, AnalystMessage
from app.models import Analysis, User, utc_now
from app.services.admin import repair_budget, ADMIN_RETRIES
from app.services.admin_audit import audited_mutation

MODELS={'video':Analysis,'ai':AnalystJob,'preset':AdminPresetJob}


def control_for(session,kind,job_id):
    return session.get(AdminJobControl,(kind,job_id)) or AdminJobControl(kind=kind,job_id=job_id)


def retry_eligible(app,session,kind,row):
    if row.status not in {'failed','interrupted'}:
        return False
    if kind=='video':
        from app.services.deletions import has_pending_storage_deletion
        if has_pending_storage_deletion(session, row.id):
            return False
        from app.services.tasks import valid_manifest, TASK_SLOTS
        manifest=valid_manifest(row,session)
        # A partial successful result is never cleared by repair.
        root=app.state.storage.analysis_root(row.id)/'output'
        return bool(manifest and all(slot in manifest for slot in TASK_SLOTS) and
                    not (root/'report.json').exists())
    if kind=='preset':
        if not row.expected:
            return False
        from app.services.analyst_collections import preset_report_path
        payload=json.loads(row.payload_json)
        path=preset_report_path(app.state.settings,row.preset_id,payload['locale'],payload['style'],payload.get('subject_id'))
        return bool(payload.get('facts')) and not path.exists()
    payload=json.loads(row.payload_json)
    if row.task_id:
        task=session.get(Analysis,row.task_id)
        if task is None or task.owner_id!=row.owner_id or task.status!='completed':
            return False
    if row.kind=='prepare':
        return bool(row.task_id)
    target=session.get(AnalystReport,row.report_id) if row.kind=='report' and row.report_id else session.get(AnalystMessage,row.message_id) if row.kind=='message' and row.message_id else None
    return bool(target and target.owner_id==row.owner_id and target.status=='failed' and payload.get('facts'))


def preset_missing_original(app, row):
    if not row.expected:
        return False
    try:
        from app.services.analyst_collections import preset_report_path
        payload = json.loads(row.payload_json)
        path = preset_report_path(app.state.settings, row.preset_id, payload['locale'], payload['style'], payload.get('subject_id'))
        return bool(payload.get('facts')) and not path.exists()
    except (KeyError, TypeError, ValueError):
        return False


def expected_backfill(session, row):
    if row.kind != 'prepare' or row.status != 'completed' or not row.task_id:
        return False
    task = session.get(Analysis, row.task_id)
    if not task or task.owner_id != row.owner_id or task.status != 'completed':
        return False
    try:
        payload = json.loads(row.payload_json)
        if payload.get('collection_version') != 1 or payload.get('locale') not in {'zh','en'} or not isinstance(payload.get('subjects'), list):
            return False
        expected = {(subject, style) for subject in [None, *payload['subjects']] for style in ('coach','roast')}
        existing = set(session.exec(select(AnalystReport.subject_id, AnalystReport.style).where(
            AnalystReport.task_id == row.task_id, AnalystReport.owner_id == row.owner_id,
            AnalystReport.kind == 'session', AnalystReport.locale == payload['locale'])).all())
        return bool(expected - existing)
    except (TypeError, ValueError):
        return False


def allowed_actions(app,session,kind,row,control=None):
    control=control or control_for(session,kind,row.id)
    actions=[]
    if row.status=='queued' and not session.get(AdminLease,(kind,row.id)):
        actions=['release' if control.held else 'hold','priority']
    if kind=='preset' and row.status=='completed' and control.admin_retries < ADMIN_RETRIES and preset_missing_original(app,row):
        actions.append('backfill')
    if kind=='ai' and control.admin_retries < ADMIN_RETRIES and expected_backfill(session,row):
        actions.append('backfill')
    if control.admin_retries < ADMIN_RETRIES and retry_eligible(app,session,kind,row):
        actions+=['retry']
        # Only persisted original preset/report snapshots are backfillable.
        if kind=='preset' or kind=='ai' and row.kind=='report':
            actions+=['backfill']
    return actions


def metadata(app,session,kind,row):
    control=control_for(session,kind,row.id)
    return dict(id=row.id,kind=kind,owner_id=getattr(row,'owner_id',None),task_id=row.id if kind=='video' else getattr(row,'task_id',None),
                status=row.status,created_at=row.created_at,updated_at=row.updated_at,attempts=row.retry_count if kind=='video' else row.attempts,
                held=control.held,priority=control.priority,admin_retries=control.admin_retries,
                allowed_actions=allowed_actions(app,session,kind,row,control))


def job_snapshot(session, kind, ids):
    from app.services.analysis_state import AnalysisStatus
    valid_statuses = {status.value for status in AnalysisStatus}
    result = {}
    for job_id in ids:
        row = session.get(MODELS[kind], job_id)
        if row is None:
            continue
        control = control_for(session, kind, job_id)
        result[job_id] = {'status':row.status if row.status in valid_statuses else 'unknown',
                         'held':control.held, 'priority':control.priority, 'admin_retries':control.admin_retries}
        if kind == 'video':
            result[job_id].update({field:getattr(row, field).isoformat() if getattr(row, field) else None
                                  for field in ('submitted_at', 'started_at', 'completed_at')})
    return result


def act(app,session,actor_id,payload):
    with audited_mutation(session, actor_id=actor_id, action='jobs.'+payload.action,
                          target_kind=payload.kind, ids=payload.ids, reason=payload.reason,
                          snapshot=lambda:job_snapshot(session,payload.kind,payload.ids)):
        rows=[]
        for job_id in payload.ids:
            row=session.get(MODELS[payload.kind],job_id)
            if row is None:
                raise HTTPException(404,'Job not found')
            control=control_for(session,payload.kind,job_id)
            if payload.action not in allowed_actions(app,session,payload.kind,row,control):
                raise HTTPException(409,'Job is not eligible for this action')
            if payload.action in {'retry','backfill'}:
                budget=repair_budget(session)
                prefix='video' if payload.kind=='video' else 'ai'
                if budget[prefix+'_used']>=budget[prefix+'_limit']:
                    raise HTTPException(429,'UTC repair budget exhausted')
                control.admin_retries+=1
                control.repair=True
                row.status='queued'
                row.updated_at=utc_now()
                if payload.kind=='video':
                    row.submitted_at=row.updated_at
                    row.started_at=None;row.completed_at=None
                    row.error_code=None;row.error_message=None;row.progress=0
                    row.stage_message='Queued for administrator repair'
                else:
                    row.available_at=utc_now()
                    if payload.kind=='ai':
                        # Preserve attempt count, payload, request key, body and successful outputs.
                        row.error=None
                        if row.report_id:
                            target=session.get(AnalystReport,row.report_id)
                            target.status='queued';target.error=None;session.add(target)
                        if row.message_id:
                            target=session.get(AnalystMessage,row.message_id)
                            target.status='queued';session.add(target)
                session.add(row)
            elif payload.action in {'hold','release'}:
                control.held=payload.action=='hold'
            elif payload.action=='priority':
                control.priority=payload.priority
            session.add(control)
            rows.append(dict(id=row.id,status=row.status))
    return {'items':rows}
