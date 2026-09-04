import asyncio
import json
import os
import signal
import shutil
import sys
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from sqlmodel import Session

from app.models import Analysis
from app.services.analysis_state import AnalysisStatus, transition_status
from app.services.media import MEDIA_FILES, ORIGINAL_CAMERA_FILES, PHASES_FILE, install_original_camera_videos


STAGE_PROGRESS = {
    AnalysisStatus.registering: 5,
    AnalysisStatus.perception: 20,
    AnalysisStatus.ball_tracking: 40,
    AnalysisStatus.synchronizing: 52,
    AnalysisStatus.action_recognition: 60,
    AnalysisStatus.outcome_detection: 72,
    AnalysisStatus.exporting: 82,
    AnalysisStatus.visualizing: 90,
}

STAGE_MESSAGES = {
    AnalysisStatus.registering: "注册匿名参与者",
    AnalysisStatus.perception: "人体感知与匿名跟踪",
    AnalysisStatus.ball_tracking: "篮球与篮筐跟踪",
    AnalysisStatus.synchronizing: "多机位时间同步",
    AnalysisStatus.action_recognition: "动作识别",
    AnalysisStatus.outcome_detection: "投篮命中判定",
    AnalysisStatus.exporting: "导出分析结果",
    AnalysisStatus.visualizing: "生成复核视频",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_stage(app: FastAPI, analysis_id: str, target: AnalysisStatus) -> None:
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        analysis = session.get(Analysis, analysis_id)
        if analysis is None or analysis.status == target:
            return
        analysis.status = transition_status(analysis.status, target).value
        analysis.progress = STAGE_PROGRESS[target]
        analysis.stage_message = STAGE_MESSAGES[target]
        analysis.updated_at = _now()
        if analysis.started_at is None:
            analysis.started_at = _now()
        session.add(analysis)
        session.commit()


def _complete(app: FastAPI, analysis_id: str) -> None:
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        current = AnalysisStatus(analysis.status)
        if current in {AnalysisStatus.canceled, AnalysisStatus.completed}:
            return
        if current == AnalysisStatus.cancel_requested:
            analysis.status = transition_status(current, AnalysisStatus.canceled).value
            analysis.stage_message = "已取消"
        else:
            if current != AnalysisStatus.visualizing:
                _advance_missing_stages(session, analysis)
            analysis.status = transition_status(analysis.status, AnalysisStatus.completed).value
            analysis.progress = 100
            analysis.stage_message = "分析完成"
        analysis.completed_at = _now()
        analysis.updated_at = _now()
        session.add(analysis)
        session.commit()


def _advance_missing_stages(session: Session, analysis: Analysis) -> None:
    ordered = list(STAGE_PROGRESS)
    current = AnalysisStatus(analysis.status)
    start = ordered.index(current) + 1 if current in ordered else 0
    for stage in ordered[start:]:
        analysis.status = transition_status(analysis.status, stage).value


def _fail(app: FastAPI, analysis_id: str, code: str, message: str) -> None:
    with Session(app.state.engine) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        current = AnalysisStatus(analysis.status)
        if current in {AnalysisStatus.canceled, AnalysisStatus.completed}:
            return
        if current == AnalysisStatus.cancel_requested:
            analysis.status = transition_status(current, AnalysisStatus.canceled).value
            analysis.stage_message = "已取消"
        else:
            analysis.status = transition_status(current, AnalysisStatus.failed).value
            analysis.stage_message = "分析失败"
            analysis.error_code = code
            analysis.error_message = message[-4000:]
        analysis.updated_at = _now()
        analysis.completed_at = _now()
        session.add(analysis)
        session.commit()


def _cancel_requested(app: FastAPI, analysis_id: str) -> bool:
    with Session(app.state.engine) as session:
        analysis = session.get(Analysis, analysis_id)
        return bool(analysis and analysis.status == AnalysisStatus.cancel_requested)


def _simulate(app: FastAPI, analysis: Analysis) -> None:
    output = app.state.storage.analysis_root(analysis.id) / "output"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    source = None
    if analysis.source_type == "preset" and analysis.preset_id:
        candidate = app.state.presets.group_root(analysis.preset_id)
        if candidate.is_dir():
            source = candidate
    if source is not None:
        for filename in ("report.json", "summary.json", "motion.json"):
            if (source / filename).is_file():
                shutil.copy2(source / filename, output / filename)
        phases = source / "viz" / PHASES_FILE
        if phases.is_file():
            (output / "viz").mkdir(parents=True, exist_ok=True)
            shutil.copy2(phases, output / "viz" / PHASES_FILE)
    else:
        (output / "report.json").write_text(
            json.dumps(
                {
                    "clips": [],
                    "shot_outcomes": [],
                    "shot_stats": {"attempts": 0, "makes": 0, "misses": 0, "undetermined": 0},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (output / "summary.json").write_text(
            json.dumps({"student_ids": [], "action_type_hist": {}, "clip_count": 0}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output / "motion.json").write_text("{}", encoding="utf-8")
    try:
        manifest = json.loads(analysis.input_manifest_json)
    except json.JSONDecodeError:
        manifest = {}
    install_original_camera_videos(
        output / "viz",
        {
            kind: Path(manifest[kind])
            for kind in ORIGINAL_CAMERA_FILES
            if isinstance(manifest.get(kind), str)
        },
    )
    media = {
        kind: filename
        for kind, filename in MEDIA_FILES.items()
        if (output / "viz" / filename).is_file()
    }
    (output / "media_manifest.json").write_text(
        json.dumps(media, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _consume_output(app: FastAPI, analysis_id: str, process, log_path: Path) -> list[str]:
    recent: list[str] = []
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        assert process.stdout is not None
        while line := await process.stdout.readline():
            text = line.decode("utf-8", errors="replace").rstrip()
            log.write(text + "\n")
            log.flush()
            recent.append(text)
            recent = recent[-30:]
            if not text.startswith("PRODUCT_EVENT "):
                continue
            try:
                event = json.loads(text.removeprefix("PRODUCT_EVENT "))
                _set_stage(app, analysis_id, AnalysisStatus(event["stage"]))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    return recent


async def _terminate_process_group(process, *, grace_seconds: float = 15) -> None:
    """Stop the isolated engine process group, including FFmpeg descendants."""
    process_group_id = process.pid
    if process.returncode is None:
        with suppress(ProcessLookupError):
            os.killpg(process_group_id, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process_group_id, signal.SIGKILL)
            await process.wait()

    # The Python runner may exit before a misbehaving descendant. Its dedicated
    # process group is no longer needed once cancellation/shutdown was requested.
    with suppress(ProcessLookupError):
        os.killpg(process_group_id, signal.SIGKILL)


async def _run_subprocess(app: FastAPI, analysis: Analysis) -> None:
    settings = app.state.settings
    task_root = app.state.storage.analysis_root(analysis.id)
    manifest = task_root / "input_manifest.json"
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "research_engine.product_runner",
        "--task-root",
        str(task_root),
        "--manifest",
        str(manifest),
        "--mode",
        analysis.mode,
        "--model-root",
        str(settings.model_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=environment,
        cwd=Path(__file__).resolve().parents[2],
        start_new_session=True,
    )
    output_task = asyncio.create_task(
        _consume_output(app, analysis.id, process, task_root / "logs" / "engine.log")
    )
    try:
        while process.returncode is None:
            if _cancel_requested(app, analysis.id):
                await _terminate_process_group(process)
                break
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except asyncio.TimeoutError:
                continue
        try:
            recent = await asyncio.wait_for(asyncio.shield(output_task), timeout=10)
        except asyncio.TimeoutError:
            await _terminate_process_group(process, grace_seconds=0.2)
            recent = await output_task
        if _cancel_requested(app, analysis.id):
            _fail(app, analysis.id, "CANCELED", "用户取消任务")
            return
        if process.returncode != 0:
            raise RuntimeError("\n".join(recent[-10:]) or f"Engine exited with {process.returncode}")
        output = task_root / "output"
        for filename in ("report.json", "summary.json", "media_manifest.json"):
            if not (output / filename).is_file():
                raise RuntimeError(f"Engine output is missing {filename}")
    finally:
        await _terminate_process_group(process, grace_seconds=0.2)
        if not output_task.done():
            output_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await output_task


async def run_analysis(app: FastAPI, analysis_id: str) -> None:
    with Session(app.state.engine) as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None or analysis.status != AnalysisStatus.queued:
            return
        detached = Analysis.model_validate(analysis)
    try:
        _set_stage(app, analysis_id, AnalysisStatus.registering)
        if app.state.settings.simulation_mode:
            _simulate(app, detached)
            for stage in list(STAGE_PROGRESS)[1:]:
                _set_stage(app, analysis_id, stage)
        else:
            await _run_subprocess(app, detached)
        _complete(app, analysis_id)
    except Exception as error:
        task_root = app.state.storage.analysis_root(analysis_id)
        log_path = task_root / "logs" / "worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"{type(error).__name__}: {error}\n")
        _fail(
            app,
            analysis_id,
            "ENGINE_FAILED",
            "科研引擎执行失败，详情已写入本地任务日志。",
        )
