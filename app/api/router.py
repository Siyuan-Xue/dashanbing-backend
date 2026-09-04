from fastapi import APIRouter

from app.api.routes import account, analyses, api_keys, auth, presets, system, tasks


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(api_keys.router)
api_router.include_router(system.router)
api_router.include_router(presets.router)
api_router.include_router(analyses.router)
api_router.include_router(tasks.router)
