from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import AppSettings
from app.models import Analysis
from app.services.analysis_state import AnalysisStatus, TERMINAL_STATUSES
from app.services.deletions import (
    ANALYSIS_ROOT,
    DATA,
    ENGINE_OUTPUT,
    ENROLLMENT,
    INPUT,
    drain_storage_deletions,
    enqueue_storage_deletion,
)
from app.services.storage import AnalysisStorage
from app.services.tasks import DRAFT_TTL, delete_task_inputs, mark_draft_expired


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class RetentionService:
    """Apply retention only under writable analysis roots; presets are never visited."""

    def __init__(self, settings: AppSettings, engine: Engine, storage: AnalysisStorage):
        self.settings = settings
        self.engine = engine
        self.storage = storage

    def run_once(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        with Session(self.engine) as session:
            analysis_ids = list(session.exec(select(Analysis.id)).all())
        for analysis_id in analysis_ids:
            # The writer reservation makes the status check and durable outbox
            # insertion atomic. Recursive filesystem work happens after commit.
            with Session(self.engine) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                analysis = session.get(Analysis, analysis_id)
                if analysis is None:
                    session.commit()
                    continue
                analysis_status = AnalysisStatus(analysis.status)
                if analysis_status in {AnalysisStatus.draft, AnalysisStatus.uploading}:
                    if current - _aware(analysis.created_at) >= DRAFT_TTL:
                        mark_draft_expired(session, analysis, current)
                        enqueue_storage_deletion(session, analysis.id, ANALYSIS_ROOT)
                        session.commit()
                    else:
                        session.commit()
                    continue
                if analysis_status not in TERMINAL_STATUSES:
                    session.commit()
                    continue
                terminal_at = _aware(analysis.completed_at) or _aware(analysis.updated_at)
                if terminal_at is None:
                    session.commit()
                    continue
                age_days = (current - terminal_at).total_seconds() / 86400
                if age_days >= self.settings.result_retention_days:
                    enqueue_storage_deletion(session, analysis.id, ANALYSIS_ROOT)
                    delete_task_inputs(session, analysis.id)
                    session.delete(analysis)
                    session.commit()
                    continue
                if age_days >= self.settings.raw_retention_days:
                    enqueue_storage_deletion(session, analysis.id, INPUT)
                    enqueue_storage_deletion(session, analysis.id, DATA)
                    enqueue_storage_deletion(session, analysis.id, ENGINE_OUTPUT)
                elif age_days >= self.settings.enrollment_retention_days:
                    enqueue_storage_deletion(session, analysis.id, ENROLLMENT)
                session.commit()
        drain_storage_deletions(self.engine, self.storage)
