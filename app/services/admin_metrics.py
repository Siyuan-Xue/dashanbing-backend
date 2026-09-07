"""Timing samples and coarse failures from persisted metadata, never log bodies."""
from collections import Counter
from datetime import timedelta, timezone
import math

from sqlalchemy import func
from sqlmodel import select

from app.admin_models import AdminPresetJob
from app.analyst_models import AnalystJob
from app.models import Analysis

VIDEO_ERROR_CODES = {
    'ENGINE_FAILED':'engine_failed',
    'registration_count_mismatch':'registration_count_mismatch',
    'registration_quality_failed':'registration_quality_failed',
    'registration_config_required':'registration_config_required',
}


def _seconds(start, end):
    if start is None or end is None:
        return None
    start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
    end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
    value = (end - start).total_seconds()
    return value if math.isfinite(value) and value >= 0 else None


def _summary(values):
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return {'count':0, 'p50':None, 'p95':None}

    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 3)

    return {'count':len(ordered), 'p50':percentile(0.5), 'p95':percentile(0.95)}


def timings(session, *, now):
    """Successful completions in the current UTC day; negative/missing spans omitted.

    AI duration includes queuing, retries and provider work, from created_at to
    completed updated_at. It combines reports, chat and presets, excluding prepare.
    """
    since = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    until = since + timedelta(days=1)
    video = session.exec(select(Analysis.submitted_at, Analysis.started_at, Analysis.completed_at).where(
        Analysis.status=='completed', Analysis.completed_at>=since, Analysis.completed_at<until)).all()
    ai = session.exec(select(AnalystJob.created_at, AnalystJob.updated_at).where(
        AnalystJob.status=='completed', AnalystJob.kind.in_(('report','message')),
        AnalystJob.updated_at>=since, AnalystJob.updated_at<until)).all()
    preset = session.exec(select(AdminPresetJob.created_at, AdminPresetJob.updated_at).where(
        AdminPresetJob.status=='completed', AdminPresetJob.updated_at>=since, AdminPresetJob.updated_at<until)).all()
    return {
        'video_queue_seconds':_summary(_seconds(submitted, started) for submitted, started, completed in video),
        'video_execution_seconds':_summary(_seconds(started, completed) for submitted, started, completed in video),
        'ai_total_seconds':_summary(_seconds(created, completed) for created, completed in [*ai,*preset]),
    }


def errors(session):
    """Current failed backlog, across all dates, grouped by a fixed coarse code set."""
    counts = Counter()
    for status, raw_code, count in session.exec(select(Analysis.status, Analysis.error_code, func.count()).where(
            Analysis.status.in_(('failed','interrupted'))).group_by(Analysis.status, Analysis.error_code)).all():
        code = 'interrupted' if status=='interrupted' else VIDEO_ERROR_CODES.get(raw_code, 'unknown')
        counts[('video',code)] += count
    for kind, count in session.exec(select(AnalystJob.kind, func.count()).where(AnalystJob.status=='failed').group_by(AnalystJob.kind)).all():
        code = 'preparation_failed' if kind=='prepare' else 'generation_failed'
        counts[('ai',code)] += count
    presets = session.exec(select(func.count()).select_from(AdminPresetJob).where(AdminPresetJob.status=='failed')).one()
    if presets:
        counts[('preset','generation_failed')] = presets
    return [{'kind':kind, 'code':code, 'count':count} for (kind,code),count in sorted(counts.items())]
