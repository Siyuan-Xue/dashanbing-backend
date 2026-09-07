"""Metadata-only administration and bounded admission settings."""
import json
import os
import shutil
import subprocess
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, inspect, text
from sqlmodel import Session, select

from app.admin_models import AdminSettings, AdminUserQuota, AdminRepairDay, AdminAudit, AdminJobControl, AdminPresetJob, AdminAttempt, AdminLease
from app.analyst_models import AnalystJob, AnalystReport, AnalystMessage
from app.models import Analysis, User, ApiKey, utc_now
from app.services.admin_audit import audited_mutation

DEFAULT_QUOTAS = dict(drafts=3, unfinished=5, daily_video=20, daily_ai=100)
QUOTA_MAX = dict(drafts=30, unfinished=50, daily_video=200, daily_ai=1000)
VIDEO_REPAIR_LIMIT = 20
AI_REPAIR_LIMIT = 100
ADMIN_RETRIES = 3


def initialize_settings(app):
    app.state.engine._admin_settings = app.state.settings
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        if session.get(AdminSettings, 1) is None:
            session.add(AdminSettings(values_json=json.dumps(default_settings(app.state.settings))))
        session.commit()


def quota_bounds(settings=None):
    return {key: {'min': 0, 'max': getattr(settings, 'admin_max_' + key, value)} for key, value in QUOTA_MAX.items()}


def default_settings(settings=None):
    quotas = {**DEFAULT_QUOTAS, 'daily_ai': getattr(settings, 'analyst_daily_limit', 100)}
    quotas = {key: min(value, quota_bounds(settings)[key]['max']) for key, value in quotas.items()}
    return dict(video_enabled=True, video_paused=False, ai_enabled=True, ai_paused=False,
                ai_concurrency=min(getattr(settings, 'analyst_concurrency', 8), getattr(settings, 'analyst_concurrency_cap', 8)),
                default_quotas=quotas)


def current_settings(session, settings=None):
    settings = settings or getattr(session.get_bind(), '_admin_settings', None)
    current = default_settings(settings)
    row = session.get(AdminSettings, 1)
    if row:
        current.update(json.loads(row.values_json))
    current['ai_concurrency'] = max(1, min(current['ai_concurrency'], getattr(settings, 'analyst_concurrency_cap', 8)))
    current['default_quotas'] = {k: min(max(0, v), quota_bounds(settings)[k]['max']) for k, v in current['default_quotas'].items()}
    return current


def effective_quotas(session, owner_id, settings=None):
    settings = settings or getattr(session.get_bind(), '_admin_settings', None)
    quotas = current_settings(session, settings)['default_quotas'].copy()
    row = session.get(AdminUserQuota, owner_id)
    if row:
        quotas.update(json.loads(row.values_json))
    return {key: min(max(0, value), quota_bounds(settings)[key]['max']) for key, value in quotas.items()}


def repair_budget(session):
    day = utc_now().date().isoformat()
    row = session.get(AdminRepairDay, day)
    return dict(utc_date=day, video_used=row.video_used if row else 0, video_limit=VIDEO_REPAIR_LIMIT,
                ai_used=row.ai_used if row else 0, ai_limit=AI_REPAIR_LIMIT)


def settings_public(app, session):
    return dict(current=current_settings(session, app.state.settings),
        bounds=dict(ai_concurrency=dict(min=1, max=app.state.settings.analyst_concurrency_cap),
                    priority=dict(min=-100, max=100), quotas=quota_bounds(app.state.settings), batch_size=10, admin_retries=3),
        repair_budget=repair_budget(session))


def validate_quotas(values, settings, *, nullable):
    for key, value in values.items():
        if value is None and nullable:
            continue
        if value is None or not 0 <= value <= quota_bounds(settings)[key]['max']:
            raise HTTPException(422, 'Quota exceeds server bounds')


def settings_snapshot(app, session):
    current = current_settings(session, app.state.settings)
    values = {key:current[key] for key in ('video_enabled','video_paused','ai_enabled','ai_paused','ai_concurrency')}
    values['default_quotas'] = {key:current['default_quotas'][key] for key in DEFAULT_QUOTAS}
    return values


def change_settings(app, session, actor_id, payload):
    with audited_mutation(session, actor_id=actor_id, action='settings.update', target_kind='settings',
                          reason=payload.reason, snapshot=lambda:settings_snapshot(app,session)):
        current = current_settings(session, app.state.settings)
        changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
        if any(v is None for v in changes.values()):
            raise HTTPException(422, 'Settings cannot be null')
        if 'ai_concurrency' in changes and changes['ai_concurrency'] > app.state.settings.analyst_concurrency_cap:
            raise HTTPException(422, 'Concurrency exceeds server bounds')
        if 'default_quotas' in changes:
            validate_quotas(changes['default_quotas'], app.state.settings, nullable=False)
            current['default_quotas'].update(changes['default_quotas'])
        current.update({k:v for k,v in changes.items() if k != 'default_quotas'})
        row = session.get(AdminSettings, 1) or AdminSettings()
        row.values_json = json.dumps(current)
        session.add(row)
    return settings_public(app, session)


def user_usage(session, owner_id):
    from app.services.tasks import DRAFT_STATUSES, UNFINISHED_STATUSES, count_daily_submissions
    repair_ids = select(AdminJobControl.job_id).where(AdminJobControl.kind == 'video', AdminJobControl.repair.is_(True))
    statuses = session.exec(select(Analysis.status).where(Analysis.owner_id == owner_id, Analysis.id.not_in(repair_ids))).all()
    since = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Ordinary admissions, including deleted output jobs, remain in their ledger.
    rows = session.exec(select(AnalystJob.payload_json).where(AnalystJob.owner_id == owner_id, AnalystJob.created_at >= since)).all()
    return dict(drafts=sum(s in DRAFT_STATUSES for s in statuses), unfinished=sum(s in UNFINISHED_STATUSES for s in statuses),
                daily_video=count_daily_submissions(session, owner_id), daily_ai=sum(not json.loads(p).get('automatic') for p in rows))


def user_public(app, session, user):
    override = session.get(AdminUserQuota, user.id)
    return dict(id=user.id, username=user.username, email=user.email, role=user.role, is_active=user.is_active,
        created_at=user.created_at, quotas=effective_quotas(session,user.id,app.state.settings),
        quota_overrides=json.loads(override.values_json) if override else {}, usage=user_usage(session,user.id))


def revoke_credentials(session, user):
    user.session_version += 1
    session.add(user)
    for key in session.exec(select(ApiKey).where(ApiKey.owner_id == user.id, ApiKey.revoked_at.is_(None))).all():
        key.revoked_at = utc_now()
        session.add(key)


def business_user(session, user_id):
    user = session.get(User, user_id)
    if not user or user.role != 'user':
        raise HTTPException(404, 'Business user not found')
    return user


def user_snapshot(app, session, user_id):
    user = session.get(User, user_id)
    if not user or user.role != 'user':
        return {}
    row = session.get(AdminUserQuota, user_id)
    overrides = json.loads(row.values_json) if row else {}
    return {'is_active':user.is_active, 'session_version':user.session_version,
            'quotas':effective_quotas(session,user_id,app.state.settings),
            'quota_overrides':{key:value for key,value in overrides.items() if key in DEFAULT_QUOTAS}}


def change_user(app, session, actor_id, user_id, payload=None, *, reason=None):
    action = 'users.force_logout' if payload is None else 'users.update'
    with audited_mutation(session, actor_id=actor_id, action=action, target_kind='user', ids=[user_id],
                          reason=reason if payload is None else payload.reason,
                          snapshot=lambda:user_snapshot(app,session,user_id), http_status=204 if payload is None else 200):
        user = business_user(session, user_id)
        if payload is None:
            revoke_credentials(session, user)
        else:
            changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
            if any(value is None for value in changes.values()):
                raise HTTPException(422, 'Mutation fields cannot be null')
            if 'is_active' in changes:
                if user.is_active != changes['is_active']:
                    revoke_credentials(session, user)
                user.is_active = changes['is_active']
                session.add(user)
            if 'quotas' in changes:
                validate_quotas(changes['quotas'], app.state.settings, nullable=True)
                row = session.get(AdminUserQuota, user.id) or AdminUserQuota(owner_id=user.id)
                values = json.loads(row.values_json)
                for key, value in changes['quotas'].items():
                    if value is None:
                        values.pop(key, None)
                    else:
                        values[key] = value
                row.values_json = json.dumps(values)
                session.add(row)
    return user_public(app,session,user)


def resources(settings):
    result = dict(cpu=dict(logical_count=os.cpu_count(),load_average=list(os.getloadavg()) if hasattr(os,'getloadavg') else None),memory=None,disk=None,gpu=None)
    try:
        import psutil
        memory=psutil.virtual_memory()
        result['memory']=dict(total_bytes=memory.total,available_bytes=memory.available)
        result['cpu']['utilization_percent']=psutil.cpu_percent(interval=None)
    except ImportError:
        try:
            values={line.split(':')[0]:int(line.split()[1])*1024 for line in open('/proc/meminfo') if line.startswith(('MemTotal:', 'MemAvailable:'))}
            result['memory']=dict(total_bytes=values['MemTotal'],available_bytes=values['MemAvailable'])
        except (OSError,KeyError,ValueError):
            pass
    try:
        disk=shutil.disk_usage(settings.runtime_root)
        result['disk']=dict(total_bytes=disk.total,used_bytes=disk.used,free_bytes=disk.free)
    except OSError:
        pass
    try:
        completed=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1,check=True)
        result['gpu']=[dict(utilization_percent=float(v[0]),memory_used_bytes=int(v[1])*1024**2,memory_total_bytes=int(v[2])*1024**2) for line in completed.stdout.splitlines() if len(v:=line.split(','))==3]
    except (OSError,subprocess.SubprocessError,ValueError):
        pass
    return result


def overview(app, session):
    from app.services.tasks import RUNNING_STATUSES
    from app.services.admin_metrics import timings, errors
    queues={}
    for kind, model in [('video',Analysis),('ai',AnalystJob),('preset',AdminPresetJob)]:
        counts=dict(session.exec(select(model.status,func.count()).group_by(model.status)).all())
        queues[kind]={status:counts.get(status,0) for status in ('queued','running','failed','completed')}
        if kind=='video':
            queues[kind]['running']=sum(counts.get(s,0) for s in RUNNING_STATUSES)
            queues[kind]['failed']+=counts.get('interrupted',0)
    since=utc_now().replace(hour=0,minute=0,second=0,microsecond=0)
    attempts=session.exec(select(func.count()).select_from(AdminAttempt).where(AdminAttempt.kind!='video',AdminAttempt.created_at>=since)).one()
    tokens=0
    for model in (AnalystJob,AdminPresetJob):
        for usage in session.exec(select(model.usage_json).where(model.updated_at>=since)).all():
            value=json.loads(usage).get('total_tokens',0)
            if isinstance(value,int) and value>=0:
                tokens+=value
    from app.models import SubmissionEvent
    submissions=session.exec(select(func.count()).select_from(SubmissionEvent).where(SubmissionEvent.submitted_at>=since)).one()
    return dict(resources=resources(app.state.settings),queues=queues,timings=timings(session,now=utc_now()),errors=errors(session),usage=dict(ai_attempts=attempts,ai_tokens=tokens,video_submissions=submissions),
        users=dict(total=session.exec(select(func.count()).select_from(User).where(User.role=='user')).one(),
                   active=session.exec(select(func.count()).select_from(User).where(User.role=='user',User.is_active.is_(True))).one()),repair_budget=repair_budget(session))


def deployment(app, session):
    revision=None
    if 'alembic_version' in inspect(session.get_bind()).get_table_names():
        revision=session.execute(text('SELECT version_num FROM alembic_version')).scalar()
    current=current_settings(session,app.state.settings)
    return dict(application=dict(version=app.version,database_revision=revision),workers=dict(video_enabled=app.state.settings.worker_enabled and current['video_enabled'],
        ai_enabled=app.state.settings.analyst_worker_enabled and current['ai_enabled']),backup=dict(status='unknown'),read_only=True)
