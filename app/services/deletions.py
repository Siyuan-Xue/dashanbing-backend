from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.models import Analysis, StorageDeletion
from app.services.analysis_state import AnalysisStatus, TERMINAL_STATUSES
from app.services.storage import AnalysisStorage


logger = logging.getLogger(__name__)

DeletionTarget = Literal[
    "analysis_root",
    "enrollment",
    "input",
    "data",
    "engine_output",
]
ANALYSIS_ROOT: DeletionTarget = "analysis_root"
ENROLLMENT: DeletionTarget = "enrollment"
INPUT: DeletionTarget = "input"
DATA: DeletionTarget = "data"
ENGINE_OUTPUT: DeletionTarget = "engine_output"
DELETION_TARGETS = frozenset(
    {ANALYSIS_ROOT, ENROLLMENT, INPUT, DATA, ENGINE_OUTPUT}
)
_RETRY_BLOCKING_TARGETS = frozenset({ANALYSIS_ROOT, INPUT})
_deletion_lock = threading.Lock()


@dataclass(frozen=True)
class PendingDeletion:
    analysis_id: str
    target: str


def enqueue_storage_deletion(
    session: Session,
    analysis_id: str,
    target: DeletionTarget,
) -> None:
    """Persist an idempotent cleanup request in the caller's transaction."""
    if target not in DELETION_TARGETS:
        raise ValueError("Invalid storage deletion target")
    if session.get(StorageDeletion, (analysis_id, target)) is None:
        session.add(StorageDeletion(analysis_id=analysis_id, target=target))


def has_pending_input_deletion(session: Session, analysis_id: str) -> bool:
    """Keep retry from racing a committed raw-input cleanup request."""
    return session.exec(
        select(StorageDeletion.analysis_id).where(
            StorageDeletion.analysis_id == analysis_id,
            StorageDeletion.target.in_(_RETRY_BLOCKING_TARGETS),
        )
    ).first() is not None


def _pending(engine: Engine) -> list[PendingDeletion]:
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(StorageDeletion).order_by(
                    StorageDeletion.created_at,
                    StorageDeletion.analysis_id,
                    StorageDeletion.target,
                )
            ).all()
        )
    return [PendingDeletion(row.analysis_id, row.target) for row in rows]


def _job_is_safe(engine: Engine, job: PendingDeletion) -> None:
    with Session(engine) as session:
        analysis = session.get(Analysis, job.analysis_id)
    if analysis is None:
        return
    try:
        status = AnalysisStatus(analysis.status)
    except ValueError as error:
        raise RuntimeError("Refusing cleanup for analysis with unknown status") from error
    if job.target == ANALYSIS_ROOT:
        if status != AnalysisStatus.expired:
            raise RuntimeError("Refusing root cleanup while analysis row is live")
        return
    if status not in TERMINAL_STATUSES:
        raise RuntimeError("Refusing retention cleanup for non-terminal analysis")


def _record_failure(engine: Engine, job: PendingDeletion, error: Exception) -> None:
    try:
        with Session(engine) as session:
            pending = session.get(StorageDeletion, (job.analysis_id, job.target))
            if pending is None:
                return
            pending.attempts += 1
            detail = f"{type(error).__name__}: {error}".strip()
            pending.last_error = detail[:4000]
            session.add(pending)
            session.commit()
    except Exception:
        logger.exception(
            "Could not record storage cleanup failure for %s/%s",
            job.analysis_id,
            job.target,
        )


def _acknowledge(engine: Engine, job: PendingDeletion) -> None:
    try:
        with Session(engine) as session:
            pending = session.get(StorageDeletion, (job.analysis_id, job.target))
            if pending is None:
                return
            session.delete(pending)
            session.commit()
    except Exception:
        # The filesystem operation is idempotent. A failed acknowledgement leaves
        # the durable row available for the next request or process restart.
        logger.exception(
            "Could not acknowledge storage cleanup for %s/%s",
            job.analysis_id,
            job.target,
        )


def drain_storage_deletions(engine: Engine, storage: AnalysisStorage) -> None:
    """Remove pending paths without retaining any database transaction."""
    with _deletion_lock:
        for job in _pending(engine):
            try:
                _job_is_safe(engine, job)
                storage.remove_deletion_target(job.analysis_id, job.target)
            except Exception as error:
                _record_failure(engine, job, error)
                continue
            _acknowledge(engine, job)
