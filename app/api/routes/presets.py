from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.models import PresetPublic
from app.services.results import ProductResult


router = APIRouter(prefix="/presets", tags=["presets"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PresetPublic])
def list_presets(request: Request) -> list[dict]:
    return request.app.state.presets.list()


@router.get("/{preset_id}/result", response_model=ProductResult)
def preset_result(preset_id: str, request: Request) -> ProductResult:
    try:
        return request.app.state.presets.result(preset_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Preset not found") from None


@router.get("/{preset_id}/media/{kind}")
def preset_media(preset_id: str, kind: str, request: Request) -> FileResponse:
    try:
        path = request.app.state.presets.media_path(preset_id, kind)
    except KeyError:
        raise HTTPException(status_code=404, detail="Preset media not found") from None
    return FileResponse(path, media_type="video/mp4", filename=path.name, content_disposition_type="inline")
