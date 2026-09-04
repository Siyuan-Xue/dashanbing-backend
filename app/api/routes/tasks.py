import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.api.routes.analyses import _allowed_media_kinds, _original_sources
from app.database import get_session
from app.models import (
    Analysis,
    PresetRerunRequest,
    TaskCreate,
    TaskInput,
    TaskListPublic,
    TaskPublic,
    User,
)
from app.services.analysis_state import ACTIVE_STATUSES, AnalysisStatus
from app.services.media import MEDIA_FILES, ORIGINAL_CAMERA_FILES, remux_to_browser_mp4, resolve_review_media
from app.services.results import ProductResult, build_product_result
from app.services.storage import (
    InsufficientStorage,
    InvalidVideoUpload,
    UploadTooLarge,
    VideoProbeUnavailable,
)
from app.services.tasks import (
    DRAFT_STATUSES,
    RUNNING_STATUSES,
    TASK_SLOTS,
    add_task_inputs_from_manifest,
    begin_write,
    delete_task_inputs,
    enforce_daily_submission_quota,
    enforce_unfinished_quota,
    expire_drafts,
    record_submission,
    task_can_be_deleted,
    task_inputs,
    task_or_404,
    task_public,
    utc_now,
    valid_manifest,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])
TaskStatusFilter = Literal[
    "draft", "uploading", "queued", "running", "completed", "failed", "canceled", "expired"
]


def _commit(session: Session, task: Analysis) -> Analysis:
    task.updated_at = utc_now()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def _storage_error(error: Exception) -> HTTPException:
    if isinstance(error, InvalidVideoUpload):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, UploadTooLarge):
        return HTTPException(status_code=413, detail=str(error))
    if isinstance(error, InsufficientStorage):
        return HTTPException(status_code=507, detail=str(error))
    if isinstance(error, VideoProbeUnavailable):
        return HTTPException(status_code=503, detail=str(error))
    raise error


def _restore_uploading_task(session: Session, task_id: str, owner_id: int) -> None:
    try:
        begin_write(session)
        task = task_or_404(task_id, owner_id, session)
        if task.status == "uploading":
            task.status = "draft"
            task.stage_message = "Draft"
            _commit(session, task)
        else:
            session.commit()
    except Exception:
        session.rollback()


@router.post("", response_model=TaskPublic, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    enforce_unfinished_quota(session, current_user.id, include_new_draft=True)
    task = Analysis(
        title=payload.title,
        mode=payload.mode,
        source_type="upload",
        status="draft",
        progress=0,
        stage_message="Draft",
        input_manifest_json="{}",
        owner_id=current_user.id,
        submitted_at=None,
        created_via="tasks_api",
    )
    _commit(session, task)
    return task_public(task, session)


@router.post("/from-preset", response_model=TaskPublic, status_code=status.HTTP_201_CREATED)
def create_task_from_preset(
    payload: PresetRerunRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    try:
        request.app.state.readiness.require_ready()
        manifest = request.app.state.presets.rerun_manifest(payload.preset_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Preset rerun inputs are unavailable") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Preset not found") from None

    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    enforce_unfinished_quota(session, current_user.id)
    enforce_daily_submission_quota(session, current_user.id)
    now = utc_now()
    task = Analysis(
        title=f"预置重跑：{payload.preset_id}",
        mode=payload.mode,
        source_type="preset",
        preset_id=payload.preset_id,
        status=AnalysisStatus.queued,
        progress=0,
        stage_message="等待执行",
        input_manifest_json=json.dumps(manifest, ensure_ascii=False),
        owner_id=current_user.id,
        submitted_at=now,
        created_via="tasks_preset",
    )
    session.add(task)
    session.flush()
    add_task_inputs_from_manifest(session, task.id, manifest, now=now)
    record_submission(session, task, kind="initial", submitted_at=now)
    request.app.state.storage.prepare_preset(task.id, manifest)
    _commit(session, task)
    return task_public(task, session)


@router.get("", response_model=TaskListPublic)
def list_tasks(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    mode: Literal["quick", "full"] | None = None,
    status_filter: TaskStatusFilter | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskListPublic:
    expire_drafts(session, current_user.id, request.app.state.storage)
    conditions = [Analysis.owner_id == current_user.id]
    if q:
        conditions.append(Analysis.title.contains(q.strip()))
    if mode:
        conditions.append(Analysis.mode == mode)
    if status_filter:
        if status_filter == "running":
            conditions.append(Analysis.status.in_(RUNNING_STATUSES))
        elif status_filter == "failed":
            conditions.append(Analysis.status.in_({"failed", "interrupted"}))
        else:
            conditions.append(Analysis.status == status_filter)
    total = session.exec(
        select(func.count()).select_from(Analysis).where(*conditions)
    ).one()
    tasks = list(
        session.exec(
            select(Analysis)
            .where(*conditions)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return TaskListPublic(
        items=[task_public(task, session) for task in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put("/{task_id}/inputs/{slot}", response_model=TaskPublic)
def upload_task_input(
    task_id: str,
    slot: Literal["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"],
    request: Request,
    file: UploadFile = File(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    task = task_or_404(task_id, current_user.id, session)
    if task.status != "draft":
        raise HTTPException(status_code=409, detail="Inputs can only be changed on a draft task")
    current_inputs = task_inputs(task.id, session)
    request.app.state.storage.recover_task_input_uploads(
        task.id,
        status=task.status,
        valid_slots={item.slot for item in current_inputs},
        committed_operations={
            item.slot: item.upload_operation_id
            for item in current_inputs
            if item.upload_operation_id is not None
        },
    )
    existing_bytes = sum(item.byte_size for item in current_inputs if item.slot != slot)
    task.status = "uploading"
    task.stage_message = f"Validating {slot}"
    _commit(session, task)
    try:
        installed = request.app.state.storage.replace_task_input(
            task.id,
            slot,
            file.file,
            existing_bytes=existing_bytes,
        )
    except Exception as error:
        session.rollback()
        begin_write(session)
        failed_task = task_or_404(task_id, current_user.id, session)
        if failed_task.status == "uploading":
            failed_task.status = "draft"
            failed_task.stage_message = "Draft"
            _commit(session, failed_task)
        else:
            session.commit()
        if isinstance(
            error,
            (InvalidVideoUpload, UploadTooLarge, InsufficientStorage, VideoProbeUnavailable),
        ):
            raise _storage_error(error) from error
        raise

    try:
        begin_write(session)
        task = task_or_404(task_id, current_user.id, session)
        if task.status != "uploading":
            raise HTTPException(
                status_code=409,
                detail="Task changed state while the input was uploading",
            )
        now = utc_now()
        item = session.get(TaskInput, (task.id, slot))
        if item is None:
            item = TaskInput(
                task_id=task.id,
                slot=slot,
                original_filename=Path(file.filename or "upload").name[:255],
                byte_size=installed.byte_size,
                validation_state="valid",
                upload_operation_id=installed.operation_id,
                path=str(installed.destination),
                created_at=now,
                updated_at=now,
            )
        else:
            item.original_filename = Path(file.filename or "upload").name[:255]
            item.byte_size = installed.byte_size
            item.validation_state = "valid"
            item.upload_operation_id = installed.operation_id
            item.path = str(installed.destination)
            item.updated_at = now
        task.status = "draft"
        task.stage_message = "Draft"
        task.updated_at = now
        session.add(item)
        session.add(task)
        session.commit()
    except Exception:
        session.rollback()
        try:
            request.app.state.storage.rollback_task_input(installed)
        finally:
            _restore_uploading_task(session, task_id, current_user.id)
        raise
    try:
        installed = request.app.state.storage.mark_task_input_committed(installed)
        request.app.state.storage.finalize_task_input(installed)
    except OSError:
        # A committed marker is authoritative even after a later lifecycle
        # transition; startup recovery finalizes any stranded backup/marker.
        pass
    session.refresh(task)
    return task_public(task, session)


@router.post("/{task_id}/submit", response_model=TaskPublic)
def submit_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    try:
        request.app.state.readiness.require_ready()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    task = task_or_404(task_id, current_user.id, session)
    if task.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft tasks can be submitted")
    items = task_inputs(task.id, session)
    by_slot = {item.slot: item for item in items if item.validation_state == "valid" and Path(item.path).is_file()}
    missing = [slot for slot in TASK_SLOTS if slot not in by_slot]
    if missing:
        raise HTTPException(status_code=409, detail=f"Missing valid task inputs: {', '.join(missing)}")
    enforce_daily_submission_quota(session, current_user.id)
    manifest = {slot: by_slot[slot].path for slot in TASK_SLOTS}
    try:
        completed_manifest = request.app.state.storage.prepare_task_submission(task.id, manifest)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Submission sync configuration is unavailable") from error
    now = utc_now()
    task.input_manifest_json = json.dumps(completed_manifest, ensure_ascii=False)
    task.status = AnalysisStatus.queued
    task.stage_message = "等待执行"
    record_submission(session, task, kind="initial", submitted_at=now)
    task.updated_at = now
    _commit(session, task)
    return task_public(task, session)


@router.get("/{task_id}", response_model=TaskPublic)
def get_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    expire_drafts(session, current_user.id, request.app.state.storage)
    return task_public(task_or_404(task_id, current_user.id, session), session)


def _review_media_paths(task: Analysis, request: Request) -> dict[str, Path]:
    output_root = request.app.state.storage.analysis_root(task.id) / "output"
    allowed = _allowed_media_kinds(output_root)
    return {
        kind: path
        for kind, path in resolve_review_media(output_root / "viz", _original_sources(task)).items()
        if kind in allowed
    }


@router.get("/{task_id}/result", response_model=ProductResult)
def get_task_result(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ProductResult:
    expire_drafts(session, current_user.id, request.app.state.storage)
    task = task_or_404(task_id, current_user.id, session)
    if task.status != AnalysisStatus.completed:
        raise HTTPException(status_code=409, detail="Task is not completed")
    root = request.app.state.storage.analysis_root(task.id) / "output"
    try:
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Task result is unavailable") from error
    media = {
        kind: f"/api/v1/tasks/{task.id}/media/{kind}"
        for kind in _review_media_paths(task, request)
    }
    return build_product_result(report=report, summary=summary, media=media)


@router.get("/{task_id}/media/{kind}")
def task_media(
    task_id: str,
    kind: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    expire_drafts(session, current_user.id, request.app.state.storage)
    task = task_or_404(task_id, current_user.id, session)
    if task.status != AnalysisStatus.completed:
        raise HTTPException(status_code=409, detail="Task is not completed")
    if kind not in MEDIA_FILES:
        raise HTTPException(status_code=404, detail="Task media not found")
    path = _review_media_paths(task, request).get(kind)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Task media not found")
    if kind in ORIGINAL_CAMERA_FILES:
        destination = request.app.state.storage.analysis_root(task.id) / "output" / "viz" / ORIGINAL_CAMERA_FILES[kind]
        try:
            path = remux_to_browser_mp4(path, destination)
        except (OSError, RuntimeError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=MEDIA_FILES[kind],
        content_disposition_type="inline",
    )


@router.post("/{task_id}/cancel", response_model=TaskPublic)
def cancel_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    task = task_or_404(task_id, current_user.id, session)
    now = utc_now()
    if task.status == AnalysisStatus.cancel_requested:
        return task_public(task, session)
    if task.status in DRAFT_STATUSES or task.status == AnalysisStatus.queued:
        task.status = AnalysisStatus.canceled
        task.stage_message = "已取消"
        task.completed_at = now
    elif task.status in {item.value for item in ACTIVE_STATUSES}:
        task.status = AnalysisStatus.cancel_requested
        task.stage_message = "正在取消"
    else:
        raise HTTPException(status_code=409, detail="Task cannot be canceled from its current state")
    _commit(session, task)
    return task_public(task, session)


@router.post("/{task_id}/retry", response_model=TaskPublic)
def retry_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TaskPublic:
    try:
        request.app.state.readiness.require_ready()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    task = task_or_404(task_id, current_user.id, session)
    if task.status not in {"failed", "canceled", "interrupted"}:
        raise HTTPException(status_code=409, detail="Only failed or canceled tasks can be retried")
    manifest = valid_manifest(task, session)
    if manifest is None or "sync" not in manifest:
        raise HTTPException(status_code=409, detail="Original task inputs are expired or incomplete")
    enforce_unfinished_quota(session, current_user.id)
    enforce_daily_submission_quota(session, current_user.id)
    now = utc_now()
    task.status = AnalysisStatus.queued
    task.progress = 0
    task.stage_message = "等待执行"
    task.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
    task.error_code = None
    task.error_message = None
    task.started_at = None
    task.completed_at = None
    record_submission(session, task, kind="retry", submitted_at=now)
    task.retry_count += 1
    _commit(session, task)
    return task_public(task, session)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    expire_drafts(session, current_user.id, request.app.state.storage)
    begin_write(session)
    task = task_or_404(task_id, current_user.id, session)
    if not task_can_be_deleted(task.status):
        raise HTTPException(status_code=409, detail="Task must be canceled before deletion")
    request.app.state.storage.delete(task.id)
    delete_task_inputs(session, task.id)
    session.delete(task)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
