"""Owner-only camera preview and synchronization; sync handlers run in worker threads."""
import json
import threading

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_session
from app.models import User
from app.services.input_preview import InputPreviewService
from app.services.task_sync import (
    camera_paths, confirm_sync, read_sync_config, source_versions, sync_error, sync_status,
)
from app.services.tasks import begin_write, task_inputs, task_or_404, utc_now
from app.sync_schemas import Camera, FramePublic, PreviewStatus, SyncInput, SyncPublic

router = APIRouter(prefix='/tasks', tags=['task-sync'])
_SERVICE_LOCK = threading.Lock()


def _service(request: Request) -> InputPreviewService:
    storage = request.app.state.storage
    with _SERVICE_LOCK:
        if not hasattr(storage, 'input_preview'):
            storage.input_preview = InputPreviewService(storage.root)
        return storage.input_preview


def _owned(task_id, session, user):
    task = task_or_404(task_id, user.id, session)
    return task, task_inputs(task.id, session)


def _public(task, items):
    return {'status': sync_status(task, items), 'source_versions': source_versions(items), 'config': read_sync_config(task)}


@router.get('/{task_id}/sync', response_model=SyncPublic)
def get_sync(task_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    return _public(task, items)


@router.put('/{task_id}/sync', response_model=SyncPublic)
def put_sync(task_id: str, payload: SyncInput, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    if task.status != 'draft':
        raise sync_error('task_state_conflict', 'Synchronization can only be changed on a draft task.', 409)
    config = confirm_sync(task, items, payload)
    session.rollback()
    begin_write(session)
    task, items = _owned(task_id, session, current_user)
    if task.status != 'draft' or source_versions(items) != config['input_versions']:
        raise sync_error('sync_stale', 'Task inputs changed while synchronization was checked.', 409)
    task.sync_config_json = json.dumps(config, allow_nan=False)
    task.updated_at = utc_now()
    session.add(task)
    session.commit()
    return _public(task, items)


@router.post('/{task_id}/sync/preview', response_model=PreviewStatus, status_code=202)
def prepare_preview(task_id: str, request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    if task.status != 'draft':
        raise sync_error('task_state_conflict', 'Prepare input previews on a draft task.', 409)
    return _service(request).prepare(task.id, camera_paths(items), source_versions(items))


@router.get('/{task_id}/sync/preview', response_model=PreviewStatus)
def preview_status(task_id: str, request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    return _service(request).status(task.id, source_versions(items))


def _versions(items, camera, source_version):
    camera_paths(items)
    versions = source_versions(items)
    if source_version is not None and versions.get(camera) != source_version:
        raise sync_error('sync_stale', 'Camera source version changed.', 409)
    return versions


@router.get('/{task_id}/sync/preview/{camera}', response_class=FileResponse, response_model=None,
            responses={200: {'content': {'video/mp4': {}}}, 206: {'description': 'Partial video content'}, 416: {'description': 'Unsatisfiable byte range'}})
def preview_video(task_id: str, camera: Camera, request: Request, source_version: str | None = None,
                  session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    path = _service(request).video_path(task.id, camera, _versions(items, camera, source_version))
    return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'private, no-cache'}, content_disposition_type='inline')


@router.get('/{task_id}/sync/frames/{camera}', response_model=FramePublic)
def preview_frame(task_id: str, camera: Camera, request: Request, time_ms: float = Query(ge=0, allow_inf_nan=False),
                  source_version: str | None = None, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    task, items = _owned(task_id, session, current_user)
    return _service(request).frame(task.id, camera, _versions(items, camera, source_version), time_ms)
