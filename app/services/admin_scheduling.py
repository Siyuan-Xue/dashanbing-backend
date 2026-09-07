"""SQLite writer-serialized claims shared by HTTP workers and preset CLI.

Leases use kernel locks in the shared local runtime. Slow requests never expire.
Legacy foreign claims without lock evidence remain unknown and fail closed.
"""
import json
import fcntl
import os
import socket
from datetime import timedelta, timezone

from sqlmodel import Session, select
from sqlalchemy import func

from app.admin_models import AdminLease, AdminJobControl, AdminPresetJob, AdminRepairDay, AdminAttempt
from app.analyst_models import AnalystJob, AnalystProviderState, AnalystReport, AnalystMessage
from app.models import Analysis, User, utc_now
from app.services.admin import current_settings, VIDEO_REPAIR_LIMIT, AI_REPAIR_LIMIT


def control(session,kind,job_id):
    return session.get(AdminJobControl,(kind,job_id))


def lease_alive(lease):
    if lease.hostname != socket.gethostname():
        return True
    try:
        os.kill(lease.pid,0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def add_lease(session,kind,job_id,pool):
    from app.services.admin_leases import acquire_guard
    lease = AdminLease(kind=kind,job_id=job_id,pool=pool,pid=os.getpid(),hostname=socket.gethostname())
    acquire_guard(session, lease)
    session.add(lease)


def release_lease(engine,kind,job_id):
    from app.services.admin_leases import take_guard, lock_path
    guard = None
    video_fd = None
    try:
        with Session(engine) as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            guard = take_guard(engine, kind, job_id)
            if kind == 'video':
                video_fd = getattr(engine, '_video_worker_locks', {}).pop(job_id, None)
            row=session.get(AdminLease,(kind,job_id))
            if row:
                path = lock_path(engine, row)
                owned = guard is not None and guard[0] == path
                legacy = (path is None or not path.exists()) and row.pid == os.getpid() and row.hostname == socket.gethostname()
                if owned or legacy:
                    session.delete(row)
            session.commit()
    finally:
        # close, never LOCK_UN: an inherited child retains ownership on parent exit.
        if guard:
            os.close(guard[1])
        if video_fd is not None:
            os.close(video_fd)


def _recover_interrupted(session, kind, job, *, enqueue=True):
    """Reuse an interrupted identity without resetting any actual-call counters.

    Graceful cancellation leaves ordinary jobs running until recovery. Repairs and
    exhausted jobs fail immediately; only an explicit admin action grants more work.
    Caller owns the SQLite writer lock and has established that no worker is active.
    """
    from app.services.analyst import MAX_ATTEMPTS
    if job.status != 'running':
        return
    target = None
    if kind == 'ai' and (job.report_id or job.message_id):
        target = session.get(AnalystReport, job.report_id) if job.report_id else session.get(AnalystMessage, job.message_id)
        if target and target.status == 'completed':
            job.status = 'completed'; job.updated_at = utc_now(); session.add(job)
            return
    ctl = control(session, kind, job.id)
    retry = job.attempts < MAX_ATTEMPTS and not (ctl and ctl.repair)
    if kind == 'ai' and job.kind != 'prepare' and target is None:
        retry = False
    if retry and not enqueue:
        return
    now = utc_now()
    job.status = 'queued' if retry else 'failed'
    job.updated_at = now
    message = 'AI 分析暂时未完成，请稍后重试'
    if kind == 'ai':
        job.error = None if retry else message
    if retry:
        provider = session.get(AnalystProviderState, 'glm')
        job.available_at = max(now, job.available_at.replace(tzinfo=timezone.utc),
            provider.available_at.replace(tzinfo=timezone.utc) if provider else now)
    session.add(job)
    if target:
        target.status = job.status; target.updated_at = now
        if isinstance(target, AnalystReport):
            target.error = None if retry else message
        else:
            target.content = '' if retry else message
            target.citations_json = '[]'; target.revision += 1
        session.add(target)


def mark_interrupted(engine, kind, job_id):
    """Called after the canceled provider coroutine has stopped, before lease release."""
    with Session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        job = session.get(AnalystJob if kind == 'ai' else AdminPresetJob, job_id)
        if job:
            _recover_interrupted(session, kind, job, enqueue=False)
        session.commit()


def recover_unleased_jobs(session):
    for kind, model in (('ai', AnalystJob), ('preset', AdminPresetJob)):
        for job in session.exec(select(model).where(model.status == 'running')).all():
            if session.get(AdminLease, (kind, job.id)) is None:
                _recover_interrupted(session, kind, job)
    session.flush()


def recover_dead_leases(session):
    from app.services.admin_leases import guard_alive
    for lease in session.exec(select(AdminLease)).all():
        locked = guard_alive(session.get_bind(), lease)
        if locked is True or locked is None and lease_alive(lease):
            continue
        model={'video':Analysis,'ai':AnalystJob,'preset':AdminPresetJob}[lease.kind]
        row=session.get(model,lease.job_id)
        if row and row.status not in {'completed','failed','canceled','expired','interrupted'}:
            if lease.kind == 'video':
                row.status='interrupted'; row.updated_at=utc_now(); session.add(row)
            else:
                _recover_interrupted(session, lease.kind, row)
        session.delete(lease)
    session.flush()


def _budget(session,kind):
    day=utc_now().date().isoformat()
    row=session.get(AdminRepairDay,day) or AdminRepairDay(utc_date=day)
    if kind=='video':
        if row.video_used>=VIDEO_REPAIR_LIMIT:
            return False
        row.video_used+=1
    else:
        if row.ai_used>=AI_REPAIR_LIMIT:
            return False
        row.ai_used+=1
    session.add(row)
    return True


def _ordered(session,kind,model,filters):
    # No row is claimed until settings, capacity and hold state share one writer lock.
    rows=session.exec(select(model).where(*filters).order_by(model.created_at,model.id)).all()
    controls={r.job_id:r for r in session.exec(select(AdminJobControl).where(AdminJobControl.kind==kind)).all()}
    rows=[r for r in rows if not (controls.get(r.id) and controls[r.id].held)]
    rows.sort(key=lambda row:(-getattr(controls.get(row.id),'priority',0),row.created_at,row.id))
    return rows


def claim_video(app):
    directory = app.state.settings.runtime_root / 'tmp'
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / 'video-worker.lock', os.O_CREAT | os.O_RDWR, 0o600)
    retained = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        job_id = _claim_video(app)
        if job_id is not None:
            locks = getattr(app.state.engine, '_video_worker_locks', None)
            if locks is None:
                locks = {}
                app.state.engine._video_worker_locks = locks
            locks[job_id] = fd
            from app.services.admin_leases import guard_fd
            app.state.video_worker_lock_fds = (fd, guard_fd(app.state.engine, 'video', job_id))
            retained = True
        return job_id
    finally:
        if not retained:
            os.close(fd)


def _claim_video(app):
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        recover_dead_leases(session)
        current=current_settings(session,app.state.settings)
        if not current['video_enabled'] or current['video_paused'] or session.exec(select(AdminLease).where(AdminLease.pool=='video')).first():
            session.commit();return None
        from app.services.tasks import RUNNING_STATUSES
        if session.exec(select(Analysis.id).where(Analysis.status.in_(RUNNING_STATUSES))).first():
            session.commit();return None
        for row in _ordered(session,'video',Analysis,[Analysis.status=='queued']):
            owner=session.get(User,row.owner_id)
            if not owner or owner.role!='user' or not owner.is_active:
                continue
            ctl=control(session,'video',row.id)
            if ctl and ctl.repair:
                if not _budget(session,'video'):
                    continue
                session.add(AdminAttempt(kind='video',job_id=row.id,owner_id=row.owner_id,repair=True))
            add_lease(session,'video',row.id,'video')
            job_id=row.id
            session.commit()
            return job_id
        session.commit();return None


def _ai_capacity(session,app):
    current=current_settings(session,app.state.settings)
    provider=session.get(AnalystProviderState,'glm')
    return (current['ai_enabled'] and not current['ai_paused'] and
        not (provider and provider.available_at.replace(tzinfo=timezone.utc)>utc_now()) and
        session.exec(select(func.count()).select_from(AdminLease).where(AdminLease.pool=='ai')).one()<current['ai_concurrency'])


def claim_ai(app):
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        recover_dead_leases(session)
        if not _ai_capacity(session,app):
            session.commit();return None
        for job in _ordered(session,'ai',AnalystJob,[AnalystJob.status=='queued',AnalystJob.available_at<=utc_now()]):
            owner=session.get(User,job.owner_id)
            if not owner or not owner.is_active or owner.role!='user':
                continue
            if session.get(AdminLease,('ai',job.id)):
                continue
            # A second queued identity must never run against an already successful/live output.
            if job.report_id or job.message_id:
                field=AnalystJob.report_id if job.report_id else AnalystJob.message_id
                target_id=job.report_id or job.message_id
                if session.exec(select(AnalystJob.id).where(field==target_id,AnalystJob.status=='running')).first():
                    continue
                target=session.get(AnalystReport,job.report_id) if job.report_id else session.get(AnalystMessage,job.message_id)
                if not target or target.status=='completed':
                    job.status='failed';session.add(job);continue
            ctl=control(session,'ai',job.id)
            if ctl and ctl.repair and job.kind!='prepare':
                day=session.get(AdminRepairDay,utc_now().date().isoformat())
                if day and day.ai_used>=AI_REPAIR_LIMIT:
                    continue
            job.status='running';job.updated_at=utc_now()
            # Preparation has no provider call, but retains its own bounded retry counter.
            if job.kind=='prepare':
                job.attempts+=1
            session.add(job);add_lease(session,'ai',job.id,'ai')
            job_id=job.id;session.commit();return job_id
        session.commit();return None


def claim_preset(app,job_id):
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        recover_dead_leases(session)
        job=session.get(AdminPresetJob,job_id)
        # The standalone preset CLI has no application startup hook. An unleased
        # running job can be a graceful shutdown; a live/foreign lease is untouched.
        if job and job.status == 'running' and session.get(AdminLease, ('preset', job_id)) is None:
            _recover_interrupted(session, 'preset', job)
        ctl=control(session,'preset',job_id)
        if (not job or job.status!='queued' or job.available_at.replace(tzinfo=timezone.utc)>utc_now() or
            ctl and ctl.held or session.get(AdminLease,('preset',job_id)) or not _ai_capacity(session,app)):
            session.commit();return False
        job.status='running';job.updated_at=utc_now()
        session.add(job);add_lease(session,'preset',job_id,'ai');session.commit();return True


def record_ai_attempt(app,kind,job_id):
    """Charge immediately before a provider request, including every repair retry."""
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        model=AnalystJob if kind=='ai' else AdminPresetJob
        job=session.get(model,job_id)
        if not job or job.status!='running':
            return False
        provider=session.get(AnalystProviderState,'glm')
        if provider and provider.available_at.replace(tzinfo=timezone.utc)>utc_now():
            job.status='queued'
            job.available_at=provider.available_at
            session.add(job);session.commit();return False
        ctl=control(session,kind,job_id)
        repair=bool(ctl and ctl.repair)
        if repair and not _budget(session,kind):
            job.status='queued'
            job.available_at=utc_now().replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
            session.add(job);session.commit();return False
        job.attempts+=1;job.updated_at=utc_now();session.add(job)
        session.add(AdminAttempt(kind=kind,job_id=job_id,owner_id=getattr(job,'owner_id',None),repair=repair))
        session.commit();return True


def provider_backoff(engine,deadline):
    with Session(engine) as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        row=session.get(AnalystProviderState,'glm') or AnalystProviderState(provider='glm')
        row.available_at=max(row.available_at.replace(tzinfo=timezone.utc),deadline)
        session.add(row);session.commit()
