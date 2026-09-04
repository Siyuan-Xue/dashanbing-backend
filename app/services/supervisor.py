import asyncio
import logging
import time
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlmodel import Session, select

from app.models import Analysis, TaskInput
from app.services.analysis_state import ACTIVE_STATUSES, AnalysisStatus


logger = logging.getLogger(__name__)


class AnalysisSupervisor:
    """Persistent SQLite queue with exactly one child process slot."""

    def __init__(self, app: FastAPI):
        self.app = app
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_retention_run = 0.0

    async def start(self) -> None:
        self._mark_interrupted()
        await self._run_retention()
        self._task = asyncio.create_task(self._loop(), name="analysis-supervisor")

    async def _run_retention(self) -> None:
        from app.services.retention import RetentionService

        service = RetentionService(
            self.app.state.settings,
            self.app.state.engine,
            self.app.state.storage,
        )
        try:
            await asyncio.to_thread(service.run_once)
        except Exception:
            logger.exception("Retention cleanup failed")
        finally:
            self._last_retention_run = time.monotonic()

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    def _mark_interrupted(self) -> None:
        with Session(self.app.state.engine) as session:
            analyses = session.exec(select(Analysis)).all()
            changed = False
            for analysis in analyses:
                valid_slots = set(
                    session.exec(
                        select(TaskInput.slot).where(TaskInput.task_id == analysis.id)
                    ).all()
                )
                self.app.state.storage.recover_task_input_uploads(
                    analysis.id,
                    status=analysis.status,
                    valid_slots=valid_slots,
                )
                if analysis.status == AnalysisStatus.uploading:
                    analysis.status = AnalysisStatus.draft
                    analysis.stage_message = "Upload interrupted; replace the slot to continue"
                    analysis.updated_at = datetime.now(timezone.utc)
                    session.add(analysis)
                    changed = True
                elif AnalysisStatus(analysis.status) in ACTIVE_STATUSES or analysis.status == AnalysisStatus.cancel_requested:
                    analysis.status = AnalysisStatus.interrupted
                    analysis.stage_message = "服务重启，任务已中断；可从原输入重试"
                    analysis.updated_at = datetime.now(timezone.utc)
                    session.add(analysis)
                    changed = True
            if changed:
                session.commit()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            if time.monotonic() - self._last_retention_run >= 3600:
                await self._run_retention()
            analysis_id = self._next_queued_id()
            if analysis_id is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                continue
            try:
                await self._run_one(analysis_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unhandled analysis worker failure for %s", analysis_id)

    def _next_queued_id(self) -> str | None:
        if not getattr(self.app.state, "gpu_queue_ready", True):
            return None
        with Session(self.app.state.engine) as session:
            analysis = session.exec(
                select(Analysis)
                .where(Analysis.status == AnalysisStatus.queued)
                .order_by(Analysis.created_at)
            ).first()
            return analysis.id if analysis else None

    async def _run_one(self, analysis_id: str) -> None:
        from app.services.worker import run_analysis

        await run_analysis(self.app, analysis_id)
