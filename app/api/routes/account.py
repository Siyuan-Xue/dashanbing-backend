from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.database import get_session
from app.models import AccountUsage, Analysis, RetentionDescriptions, User, UsageQuota
from app.services.api_keys import MAX_ACTIVE_API_KEYS, active_api_key_count
from app.services.tasks import (
    DRAFT_STATUSES,
    UNFINISHED_STATUSES,
    count_daily_submissions,
    expire_drafts,
)


router = APIRouter(prefix="/account", tags=["account"])


@router.get("/usage", response_model=AccountUsage)
def account_usage(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccountUsage:
    expire_drafts(session, current_user.id, request.app.state.storage)
    from app.admin_models import AdminJobControl
    repair_ids = select(AdminJobControl.job_id).where(AdminJobControl.kind == "video", AdminJobControl.repair.is_(True))
    unfinished = session.exec(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.owner_id == current_user.id, Analysis.status.in_(UNFINISHED_STATUSES), Analysis.id.not_in(repair_ids))
    ).one()
    drafts = session.exec(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.owner_id == current_user.id, Analysis.status.in_(DRAFT_STATUSES))
    ).one()
    from app.services.admin import effective_quotas
    quotas = effective_quotas(session, current_user.id, request.app.state.settings)
    settings = request.app.state.settings
    return AccountUsage(
        submitted_today=UsageQuota(
            used=count_daily_submissions(session, current_user.id),
            limit=quotas["daily_video"],
        ),
        unfinished_tasks=UsageQuota(used=unfinished, limit=quotas["unfinished"]),
        drafts=UsageQuota(used=drafts, limit=quotas["drafts"]),
        active_api_keys=UsageQuota(
            used=active_api_key_count(session, current_user.id),
            limit=MAX_ACTIVE_API_KEYS,
        ),
        retention=RetentionDescriptions(
            drafts="24 hours",
            enrollment_data=f"{settings.enrollment_retention_days} days",
            raw_inputs=f"{settings.raw_retention_days} days",
            results=f"{settings.result_retention_days} days",
        ),
    )


@router.get("/limits")
def account_limits(request: Request, session: Session = Depends(get_session),
                   current_user: User = Depends(get_current_user)):
    from app.services.admin import effective_quotas
    from app.services.tasks import DRAFT_TTL
    settings = request.app.state.settings
    quotas = effective_quotas(session, current_user.id, settings)
    return {"quotas": quotas, "application": {
        "max_upload_size_gb": settings.max_upload_size_gb,
        "draft_ttl_hours": DRAFT_TTL.total_seconds() / 3600,
        "enrollment_retention_days": settings.enrollment_retention_days,
        "raw_retention_days": settings.raw_retention_days,
        "result_retention_days": settings.result_retention_days,
        "analyst_daily_limit": quotas["daily_ai"],
    }}
