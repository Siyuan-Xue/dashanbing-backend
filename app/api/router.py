from fastapi import APIRouter

from app.api.routes import admin, account, analyses, api_keys, auth, presets, system, tasks
from app.api.routes import analyst, analyst_context, training_profiles


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(api_keys.router)
api_router.include_router(system.router)
api_router.include_router(presets.router)
api_router.include_router(analyses.router)
api_router.include_router(tasks.router)
api_router.include_router(analyst.router)
api_router.include_router(analyst_context.router)
api_router.include_router(training_profiles.router)

api_router.include_router(admin.router)

from app.api.routes import task_sync
api_router.include_router(task_sync.router)
