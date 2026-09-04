import asyncio
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.api.router import api_router
from app.api.deps import get_current_user
from app.config import AppSettings, get_settings
from app.database import create_database_engine, create_tables
from app.models import User
from app.security import hash_password, normalize_identity, verify_password
from app.services.identities import ensure_user_identities
from app.services.presets import PresetCatalog
from app.services.readiness import ReadinessService
from app.services.storage import AnalysisStorage


def _bootstrap_admin(app: FastAPI) -> bool:
    settings = app.state.settings
    if not app.state.readiness.configured_credentials_ready():
        return False
    with Session(app.state.engine) as session:
        existing = session.exec(select(User)).first()
        configured_username = normalize_identity(settings.admin_username)
        if existing is None:
            existing = User(
                username=configured_username,
                hashed_password=hash_password(settings.admin_password),
            )
            session.add(existing)
            session.flush()
            ensure_user_identities(session, existing)
            session.commit()
            return True
        try:
            valid = normalize_identity(existing.username) == configured_username and verify_password(
                settings.admin_password,
                existing.hashed_password,
            )
            if valid:
                ensure_user_identities(session, existing)
                session.commit()
            return valid
        except Exception:
            return False


def create_app(
    database_url: str | None = None,
    *,
    settings: AppSettings | None = None,
) -> FastAPI:
    """Create one local, same-origin basketball analysis application."""
    app_settings = settings or get_settings()
    if database_url is not None:
        app_settings = app_settings.model_copy(update={"database_url": database_url})

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.settings.runtime_root.mkdir(parents=True, exist_ok=True)
        (application.state.settings.runtime_root / "tmp").mkdir(parents=True, exist_ok=True)
        application.state.storage.root.mkdir(parents=True, exist_ok=True)
        if application.state.settings.auto_create_schema:
            create_tables(application.state.engine)
        credentials_ready = _bootstrap_admin(application)
        application.state.readiness.set_database_credentials_ready(credentials_ready)
        if application.state.settings.worker_enabled:
            from app.services.supervisor import AnalysisSupervisor

            # Serialize the one-time deep GPU/model probe before queued work can
            # acquire the single engine slot. Subsequent readiness calls are cached.
            preflight = application.state.readiness.preflight()
            application.state.gpu_queue_ready = bool(preflight["ready"])
            application.state.readiness.lock_queue_state(application.state.gpu_queue_ready)
            supervisor = AnalysisSupervisor(application)
            application.state.supervisor = supervisor
            await supervisor.start()
        else:
            from app.services.supervisor import AnalysisSupervisor

            AnalysisSupervisor(application)._mark_interrupted()
        yield
        supervisor = getattr(application.state, "supervisor", None)
        if supervisor is not None:
            await supervisor.stop()

    application = FastAPI(
        title="篮球课堂训练复盘",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.engine = create_database_engine(app_settings.database_url)
    application.state.storage = AnalysisStorage(app_settings)
    application.state.presets = PresetCatalog(app_settings.sample_root)
    application.state.readiness = ReadinessService(app_settings)
    application.state.upload_admission = asyncio.Lock()
    application.include_router(api_router)

    @application.middleware("http")
    async def reject_oversized_uploads(request: Request, call_next):
        is_legacy_upload = request.method == "POST" and request.url.path == "/api/v1/analyses/upload"
        is_task_upload = (
            request.method == "PUT"
            and request.url.path.startswith("/api/v1/tasks/")
            and "/inputs/" in request.url.path
        )
        if is_legacy_upload or is_task_upload:
            try:
                with Session(application.state.engine) as session:
                    get_current_user(request, session)
            except HTTPException as error:
                return JSONResponse(
                    {"detail": error.detail},
                    status_code=error.status_code,
                    headers=error.headers,
                )
            content_length = request.headers.get("content-length")
            limit = int(application.state.settings.max_upload_size_gb * 1024**3) + 10 * 1024**2
            if content_length is None:
                return JSONResponse({"detail": "Content-Length is required"}, status_code=411)
            try:
                too_large = int(content_length) > limit
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "上传文件总大小超过本地配置上限"}, status_code=413)
            declared_bytes = int(content_length)
            reserve_bytes = int(application.state.settings.min_free_storage_gb * 1024**3)
            free_bytes = shutil.disk_usage(application.state.settings.runtime_root).free
            if free_bytes - declared_bytes < reserve_bytes:
                return JSONResponse({"detail": "本地存储空间不足，上传已停止"}, status_code=507)
            admission = application.state.upload_admission
            if admission.locked():
                return JSONResponse({"detail": "已有视频正在上传，请稍后重试"}, status_code=409)
            async with admission:
                return await call_next(request)
        return await call_next(request)

    @application.middleware("http")
    async def mark_legacy_analysis_routes_deprecated(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/analyses"):
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "Fri, 04 Dec 2026 00:00:00 GMT"
        return response

    frontend = app_settings.frontend_dist
    assets = frontend / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    def frontend_public_asset(name: str, media_type: str) -> FileResponse:
        """Serve only the two root assets referenced by the built document."""
        path = frontend / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @application.get("/theme-bootstrap.js", include_in_schema=False, response_model=None)
    def theme_bootstrap() -> FileResponse:
        return frontend_public_asset("theme-bootstrap.js", "application/javascript")

    @application.get("/favicon.svg", include_in_schema=False, response_model=None)
    def favicon() -> FileResponse:
        return frontend_public_asset("favicon.svg", "image/svg+xml")

    @application.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz", include_in_schema=False, response_model=None)
    def readyz():
        report = application.state.readiness.report()
        return JSONResponse(report, status_code=200 if report["ready"] else 503)

    @application.get("/{path:path}", include_in_schema=False, response_model=None)
    def frontend_fallback(path: str):
        normalized_path = path.rstrip("/")
        if path.startswith("api/") and normalized_path not in {"api", "api/docs", "api/keys"}:
            raise HTTPException(status_code=404, detail="Not found")
        index = frontend / "index.html"
        if index.is_file():
            return FileResponse(index)
        return {"message": "篮球课堂训练复盘 API", "docs": "/docs"}

    return application


app = create_app()
