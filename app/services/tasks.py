from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Analysis,
    SubmissionEvent,
    TaskInput,
    TaskInputPublic,
    TaskPublic,
    TaskPublicStatus,
)
from app.services.analysis_state import ACTIVE_STATUSES, AnalysisStatus


TASK_SLOTS = ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04")
DRAFT_STATUSES = {"draft", "uploading"}
RUNNING_STATUSES = {status.value for status in ACTIVE_STATUSES} | {
    AnalysisStatus.cancel_requested.value,
}
UNFINISHED_STATUSES = DRAFT_STATUSES | RUNNING_STATUSES | {AnalysisStatus.queued.value}
TERMINAL_TASK_STATUSES = {
    AnalysisStatus.completed.value,
    AnalysisStatus.failed.value,
    AnalysisStatus.canceled.value,
    AnalysisStatus.interrupted.value,
    "expired",
}

MAX_DRAFTS = 3
MAX_UNFINISHED = 5
MAX_DAILY_SUBMISSIONS = 20
DRAFT_TTL = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


PUBLIC_STATUS_BY_INTERNAL: dict[AnalysisStatus, TaskPublicStatus] = {
    AnalysisStatus.draft: "draft",
    AnalysisStatus.uploading: "uploading",
    AnalysisStatus.queued: "queued",
    AnalysisStatus.running: "running",
    AnalysisStatus.registering: "running",
    AnalysisStatus.perception: "running",
    AnalysisStatus.ball_tracking: "running",
    AnalysisStatus.synchronizing: "running",
    AnalysisStatus.action_recognition: "running",
    AnalysisStatus.outcome_detection: "running",
    AnalysisStatus.exporting: "running",
    AnalysisStatus.visualizing: "running",
    AnalysisStatus.cancel_requested: "running",
    AnalysisStatus.completed: "completed",
    AnalysisStatus.failed: "failed",
    AnalysisStatus.canceled: "canceled",
    AnalysisStatus.interrupted: "failed",
    AnalysisStatus.expired: "expired",
}
if set(PUBLIC_STATUS_BY_INTERNAL) != set(AnalysisStatus):
    raise RuntimeError("Every internal analysis status must have a public task status")


def public_status(value: str) -> TaskPublicStatus:
    return PUBLIC_STATUS_BY_INTERNAL[AnalysisStatus(value)]


def task_or_404(task_id: str, owner_id: int, session: Session) -> Analysis:
    task = session.exec(
        select(Analysis).where(Analysis.id == task_id, Analysis.owner_id == owner_id)
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def task_inputs(task_id: str, session: Session) -> list[TaskInput]:
    return list(
        session.exec(
            select(TaskInput).where(TaskInput.task_id == task_id).order_by(TaskInput.slot)
        ).all()
    )


def delete_task_inputs(session: Session, task_id: str) -> None:
    for item in task_inputs(task_id, session):
        session.delete(item)
    session.flush()


def add_task_inputs_from_manifest(
    session: Session,
    task_id: str,
    manifest: dict[str, str],
    *,
    original_filenames: dict[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    timestamp = now or utc_now()
    names = original_filenames or {}
    for slot in TASK_SLOTS:
        path = Path(manifest[slot])
        session.add(
            TaskInput(
                task_id=task_id,
                slot=slot,
                original_filename=Path(names.get(slot) or path.name).name[:255],
                byte_size=path.stat().st_size,
                validation_state="valid",
                path=str(path),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )


def task_public(task: Analysis, session: Session) -> TaskPublic:
    return TaskPublic(
        id=task.id,
        title=task.title,
        mode=task.mode,
        source_type=task.source_type,
        preset_id=task.preset_id,
        status=public_status(task.status),
        progress=task.progress,
        stage_message=task.stage_message,
        error_code=task.error_code,
        error_message=task.error_message,
        submitted_at=task.submitted_at,
        created_via=task.created_via,
        retry_count=task.retry_count,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        inputs=[TaskInputPublic.model_validate(item) for item in task_inputs(task.id, session)],
    )


def mark_draft_expired(session: Session, task: Analysis, current: datetime) -> None:
    task.status = "expired"
    task.stage_message = "Draft expired"
    task.updated_at = current
    task.completed_at = current
    session.add(task)
    for item in task_inputs(task.id, session):
        item.validation_state = "expired"
        item.updated_at = current
        session.add(item)


def expire_drafts(session: Session, owner_id: int, storage, *, now: datetime | None = None) -> None:
    current = now or utc_now()
    cutoff = current - DRAFT_TTL
    drafts = list(
        session.exec(
            select(Analysis).where(
                Analysis.owner_id == owner_id,
                Analysis.status.in_(DRAFT_STATUSES),
                Analysis.created_at <= cutoff,
            )
        ).all()
    )
    if not drafts:
        return
    for task in drafts:
        mark_draft_expired(session, task, current)
    session.commit()
    for task in drafts:
        storage.delete(task.id)


def begin_write(session: Session) -> None:
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _owner_tasks(session: Session, owner_id: int) -> list[Analysis]:
    return list(session.exec(select(Analysis).where(Analysis.owner_id == owner_id)).all())


def enforce_unfinished_quota(
    session: Session,
    owner_id: int,
    *,
    include_new_draft: bool = False,
) -> None:
    tasks = _owner_tasks(session, owner_id)
    if include_new_draft and sum(task.status in DRAFT_STATUSES for task in tasks) >= MAX_DRAFTS:
        raise HTTPException(status_code=429, detail="Draft task quota exceeded (maximum 3 drafts)")
    if sum(task.status in UNFINISHED_STATUSES for task in tasks) >= MAX_UNFINISHED:
        raise HTTPException(status_code=429, detail="Unfinished task quota exceeded (maximum 5)")


def _utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or utc_now()
    start = current.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def enforce_daily_submission_quota(
    session: Session,
    owner_id: int,
) -> None:
    start, end = _utc_day_bounds()
    event_count = session.exec(
        select(func.count())
        .select_from(SubmissionEvent)
        .where(
            SubmissionEvent.owner_id == owner_id,
            SubmissionEvent.submitted_at >= start,
            SubmissionEvent.submitted_at < end,
        )
    ).one()
    ledger_task_ids = select(SubmissionEvent.task_id).where(
        SubmissionEvent.owner_id == owner_id
    )
    unledgered_count = session.exec(
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.owner_id == owner_id,
            Analysis.submitted_at >= start,
            Analysis.submitted_at < end,
            Analysis.id.not_in(ledger_task_ids),
        )
    ).one()
    if event_count + unledgered_count >= MAX_DAILY_SUBMISSIONS:
        raise HTTPException(
            status_code=429,
            detail="Daily submission quota exceeded (maximum 20 per UTC day)",
        )


def record_submission(
    session: Session,
    task: Analysis,
    *,
    kind: str,
    submitted_at: datetime | None = None,
) -> datetime:
    timestamp = submitted_at or utc_now()
    task.submitted_at = timestamp
    session.add(
        SubmissionEvent(
            task_id=task.id,
            owner_id=task.owner_id,
            kind=kind,
            submitted_at=timestamp,
        )
    )
    return timestamp


def task_can_be_deleted(status: str) -> bool:
    return status == AnalysisStatus.draft.value or status in TERMINAL_TASK_STATUSES


def valid_manifest(task: Analysis, session: Session) -> dict[str, str] | None:
    items = task_inputs(task.id, session)
    try:
        existing = json.loads(task.input_manifest_json)
    except json.JSONDecodeError:
        existing = {}
    if not items:
        required = (*TASK_SLOTS, "sync")
        if all(isinstance(existing.get(name), str) and Path(existing[name]).is_file() for name in required):
            return {name: existing[name] for name in required}
        return None
    by_slot = {item.slot: item for item in items if item.validation_state == "valid"}
    if set(by_slot) != set(TASK_SLOTS):
        return None
    manifest = {slot: by_slot[slot].path for slot in TASK_SLOTS}
    if not all(Path(path).is_file() for path in manifest.values()):
        return None
    sync = existing.get("sync")
    if isinstance(sync, str) and Path(sync).is_file():
        manifest["sync"] = sync
    return manifest
