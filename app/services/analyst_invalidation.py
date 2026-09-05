"""Revoke only analyst snapshots that depend on changed confirmed memory."""

import json

from sqlmodel import Session, select

from app.analyst_models import (
    AnalystConversation, AnalystJob, AnalystMessage, AnalystReport, TaskSubject, TrainingObservation, utc_now,
)
from app.models import Analysis


def _memory_depends(payload: str, tasks: set[str], profiles: set[str], observations: set[str]) -> bool:
    try:
        memory = json.loads(payload).get("memory", {})
    except (ValueError, TypeError, AttributeError):
        return False
    if not isinstance(memory, dict):
        return False
    if memory.get("comparison_id") in observations:
        return True
    profile_rows = [memory.get("profile"), *(memory.get("profiles") or [])]
    if any(isinstance(row, dict) and row.get("id") in profiles for row in profile_rows):
        return True
    rows = [memory.get("comparison"), *(memory.get("observations") or []), *(memory.get("subjects") or [])]
    return any(isinstance(row, dict) and (
        row.get("id") in observations or row.get("profile_id") in profiles or row.get("task_id") in tasks
    ) for row in rows)


def revoke_snapshots(session: Session, owner_id: int, *, task_ids: set[str] | None = None,
                     profile_ids: set[str] | None = None, observation_ids: set[str] | None = None) -> None:
    # Explicit full revocation is retained for callers requesting an account reset.
    from app.services.training_profiles import _scrub_job

    all_snapshots = task_ids is None and profile_ids is None and observation_ids is None
    tasks, profiles, observations = set(task_ids or ()), set(profile_ids or ()), set(observation_ids or ())
    if profiles:
        tasks.update(row.task_id for row in session.exec(select(TaskSubject).where(
            TaskSubject.owner_id == owner_id, TaskSubject.profile_id.in_(profiles))).all())
    jobs = list(session.exec(select(AnalystJob).where(AnalystJob.owner_id == owner_id)).all())
    reports = list(session.exec(select(AnalystReport).where(AnalystReport.owner_id == owner_id)).all())
    conversations = list(session.exec(select(AnalystConversation).where(AnalystConversation.owner_id == owner_id)).all())
    messages = list(session.exec(select(AnalystMessage).where(AnalystMessage.owner_id == owner_id)).all())
    by_message = {row.id: row for row in messages}
    session_reports = {row.id for row in reports if row.kind == "session"}
    comparison_reports = {row.id for row in reports if row.kind == "comparison"}
    protected_jobs = set()
    if not all_snapshots:
        for job in jobs:
            try:
                kind = json.loads(job.payload_json).get("report_kind", "session")
            except (ValueError, TypeError, AttributeError):
                kind = "session"
            if job.kind == "prepare" or (job.kind == "report" and
                    (job.report_id in session_reports or job.report_id not in comparison_reports and kind == "session")):
                protected_jobs.add(job.id)
    affected_jobs = {row.id for row in jobs if row.id not in protected_jobs and (all_snapshots or row.task_id in tasks
                     or _memory_depends(row.payload_json, tasks, profiles, observations))}
    affected_reports = {row.id for row in reports if all_snapshots or row.kind == "comparison" and (
        row.task_id in tasks or row.comparison_id in observations)}
    affected_conversations = {row.id for row in conversations if all_snapshots or row.task_id in tasks
                              or row.comparison_id in observations}
    for job in jobs:
        if job.id in affected_jobs:
            if job.report_id and (all_snapshots or job.report_id not in session_reports):
                affected_reports.add(job.report_id)
            if job.message_id in by_message:
                affected_conversations.add(by_message[job.message_id].conversation_id)
    # Later answers can inherit earlier replies, so revoke the affected session's
    # assistant history together while retaining user questions and quota records.
    for message in messages:
        if message.conversation_id in affected_conversations and message.role == "assistant":
            message.status = "failed"
            message.content = ""
            message.citations_json = "[]"
            message.revision += 1
            message.updated_at = utc_now()
            session.add(message)
    for job in jobs:
        answer = by_message.get(job.message_id)
        if job.id not in protected_jobs and (job.id in affected_jobs or job.report_id in affected_reports
                or answer and answer.conversation_id in affected_conversations):
            _scrub_job(session, job)
    for report in reports:
        if report.id in affected_reports:
            session.delete(report)
    for conversation in conversations:
        if conversation.id in affected_conversations:
            if not _comparison_still_valid(session, conversation):
                conversation.comparison_id = None
            conversation.updated_at = utc_now()
            session.add(conversation)
    session.flush()


def _comparison_still_valid(session: Session, conversation: AnalystConversation) -> bool:
    if not conversation.comparison_id:
        return True
    observation = session.get(TrainingObservation, conversation.comparison_id)
    task = session.get(Analysis, conversation.task_id) if conversation.task_id else None
    if not observation or not task or observation.owner_id != conversation.owner_id or observation.mode != task.mode:
        return False
    links = session.exec(select(TaskSubject).where(
        TaskSubject.owner_id == conversation.owner_id, TaskSubject.task_id == task.id,
        TaskSubject.profile_id == observation.profile_id)).all()
    return any(conversation.subject_id is None or row.subject_id == conversation.subject_id for row in links)
