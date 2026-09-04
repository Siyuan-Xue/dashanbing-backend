import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import AppSettings
from app.models import Analysis
from app.services.analysis_state import AnalysisStatus, TERMINAL_STATUSES
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

    @staticmethod
    def _remove(path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def run_once(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        with Session(self.engine) as session:
            analysis_ids = list(session.exec(select(Analysis.id)).all())
        for analysis_id in analysis_ids:
            # A SQLite write reservation prevents retry/cancel from changing the
            # status between this final check and destructive filesystem work.
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
                        session.commit()
                        self.storage.delete(analysis.id)
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
                root = self.storage.analysis_root(analysis.id)
                if age_days >= self.settings.result_retention_days:
                    self.storage.delete(analysis.id)
                    delete_task_inputs(session, analysis.id)
                    session.delete(analysis)
                    session.commit()
                    continue
                if age_days >= self.settings.enrollment_retention_days:
                    self._remove(root / "data" / "enrollment")
                if age_days >= self.settings.raw_retention_days:
                    self._remove(root / "input")
                    self._remove(root / "data")
                    self._remove(root / "engine-output")
                session.commit()
