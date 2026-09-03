import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.database import get_session
from app.models import Analysis, AnalysisPublic, PresetRerunRequest
from app.services.analysis_state import ACTIVE_STATUSES, AnalysisStatus, transition_status
from app.services.presets import MEDIA_FILES
from app.services.results import ProductResult, build_product_result


router = APIRouter(prefix="/analyses", tags=["analyses"], dependencies=[Depends(get_current_user)])


def _analysis_or_404(analysis_id: str, session: Session) -> Analysis:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def _commit(session: Session, analysis: Analysis) -> Analysis:
    analysis.updated_at = datetime.now(timezone.utc)
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis


def _manifest_inputs_available(manifest: dict) -> bool:
    required = {"enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04", "sync"}
    return required.issubset(manifest) and all(
        isinstance(manifest[name], str) and Path(manifest[name]).is_file()
        for name in required
    )


@router.post("/upload", response_model=AnalysisPublic, status_code=status.HTTP_201_CREATED)
def upload_analysis(
    request: Request,
    title: str = Form(min_length=1, max_length=120),
    mode: Literal["quick", "full"] = Form(),
    enrollment_video: UploadFile = File(),
    cam_01: UploadFile = File(),
    cam_02: UploadFile = File(),
    cam_03: UploadFile = File(),
    cam_04: UploadFile = File(),
    session: Session = Depends(get_session),
) -> Analysis:
    try:
        request.app.state.readiness.require_ready()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    analysis = Analysis(title=title, mode=mode, source_type="upload", input_manifest_json="{}")
    storage = request.app.state.storage
    try:
        manifest = storage.save_uploads(
            analysis.id,
            {
                "enrollment_video": enrollment_video.file,
                "cam_01": cam_01.file,
                "cam_02": cam_02.file,
                "cam_03": cam_03.file,
                "cam_04": cam_04.file,
            },
        )
        analysis.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
        return _commit(session, analysis)
    except ValueError as error:
        storage.delete(analysis.id)
        raise HTTPException(status_code=413, detail=str(error)) from error
    except Exception:
        storage.delete(analysis.id)
        raise


@router.post("/preset", response_model=AnalysisPublic, status_code=status.HTTP_201_CREATED)
def rerun_preset(
    payload: PresetRerunRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Analysis:
    try:
        request.app.state.readiness.require_ready()
        manifest = request.app.state.presets.rerun_manifest(payload.preset_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Preset rerun inputs are unavailable") from None
    except KeyError:
        raise HTTPException(status_code=404, detail="Preset not found") from None
    analysis = Analysis(
        title=f"预置重跑：{payload.preset_id}",
        mode=payload.mode,
        source_type="preset",
        preset_id=payload.preset_id,
        input_manifest_json=json.dumps(manifest, ensure_ascii=False),
    )
    request.app.state.storage.prepare_preset(analysis.id, manifest)
    return _commit(session, analysis)


@router.get("", response_model=list[AnalysisPublic])
def list_analyses(session: Session = Depends(get_session)) -> list[Analysis]:
    return list(session.exec(select(Analysis).order_by(Analysis.created_at.desc())).all())


@router.get("/{analysis_id}", response_model=AnalysisPublic)
def get_analysis(analysis_id: str, session: Session = Depends(get_session)) -> Analysis:
    return _analysis_or_404(analysis_id, session)


@router.get("/{analysis_id}/result", response_model=ProductResult)
def get_result(analysis_id: str, request: Request, session: Session = Depends(get_session)) -> ProductResult:
    analysis = _analysis_or_404(analysis_id, session)
    if analysis.status != AnalysisStatus.completed:
        raise HTTPException(status_code=409, detail="Analysis is not completed")
    root = request.app.state.storage.analysis_root(analysis.id) / "output"
    try:
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Analysis result is unavailable") from error
    media_manifest = _load_media_manifest(root)
    media = {
        kind: f"/api/v1/analyses/{analysis.id}/media/{kind}" for kind in media_manifest
    }
    return build_product_result(report=report, summary=summary, media=media)


def _load_media_manifest(output_root: Path) -> dict[str, str]:
    path = output_root / "media_manifest.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        kind: filename
        for kind, filename in payload.items()
        if kind in MEDIA_FILES and filename == MEDIA_FILES[kind]
    }


@router.get("/{analysis_id}/media/{kind}")
def analysis_media(analysis_id: str, kind: str, request: Request, session: Session = Depends(get_session)) -> FileResponse:
    analysis = _analysis_or_404(analysis_id, session)
    if analysis.status != AnalysisStatus.completed:
        raise HTTPException(status_code=409, detail="Analysis is not completed")
    output_root = request.app.state.storage.analysis_root(analysis.id) / "output"
    manifest = _load_media_manifest(output_root)
    filename = manifest.get(kind)
    if filename is None:
        raise HTTPException(status_code=404, detail="Analysis media not found")
    path = output_root / "viz" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Analysis media not found")
    return FileResponse(path, media_type="video/mp4", filename=filename, content_disposition_type="inline")


@router.post("/{analysis_id}/cancel", response_model=AnalysisPublic)
def cancel_analysis(analysis_id: str, session: Session = Depends(get_session)) -> Analysis:
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    analysis = _analysis_or_404(analysis_id, session)
    current = AnalysisStatus(analysis.status)
    if current == AnalysisStatus.cancel_requested:
        return analysis
    target = AnalysisStatus.cancel_requested if current in ACTIVE_STATUSES else AnalysisStatus.canceled
    try:
        analysis.status = transition_status(current, target).value
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    analysis.stage_message = "正在取消" if target == AnalysisStatus.cancel_requested else "已取消"
    return _commit(session, analysis)


@router.post("/{analysis_id}/retry", response_model=AnalysisPublic)
def retry_analysis(
    analysis_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Analysis:
    try:
        request.app.state.readiness.require_ready()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    # Reserve the SQLite writer before reloading and validating the manifest.
    # Retention uses the same reservation and must re-check status after this
    # transaction commits, so it cannot delete inputs behind a queued retry.
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    analysis = _analysis_or_404(analysis_id, session)
    try:
        manifest = json.loads(analysis.input_manifest_json)
    except json.JSONDecodeError:
        manifest = {}
    if not _manifest_inputs_available(manifest):
        raise HTTPException(status_code=409, detail="原输入已过期或不完整，无法重试")
    try:
        analysis.status = transition_status(analysis.status, AnalysisStatus.queued).value
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    analysis.progress = 0
    analysis.stage_message = "等待执行"
    analysis.error_code = None
    analysis.error_message = None
    analysis.started_at = None
    analysis.completed_at = None
    return _commit(session, analysis)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    analysis = _analysis_or_404(analysis_id, session)
    if AnalysisStatus(analysis.status) in ACTIVE_STATUSES or analysis.status == AnalysisStatus.cancel_requested:
        raise HTTPException(status_code=409, detail="Running analysis must be canceled first")
    request.app.state.storage.delete(analysis.id)
    session.delete(analysis)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
