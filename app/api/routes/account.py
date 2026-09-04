from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.database import get_session
from app.models import AccountUsage, Analysis, RetentionDescriptions, User, UsageQuota
from app.services.api_keys import MAX_ACTIVE_API_KEYS, active_api_key_count
from app.services.tasks import (
    DRAFT_STATUSES,
    MAX_DAILY_SUBMISSIONS,
    MAX_DRAFTS,
    MAX_UNFINISHED,
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
    unfinished = session.exec(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.owner_id == current_user.id, Analysis.status.in_(UNFINISHED_STATUSES))
    ).one()
    drafts = session.exec(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.owner_id == current_user.id, Analysis.status.in_(DRAFT_STATUSES))
    ).one()
    settings = request.app.state.settings
    return AccountUsage(
        submitted_today=UsageQuota(
            used=count_daily_submissions(session, current_user.id),
            limit=MAX_DAILY_SUBMISSIONS,
        ),
        unfinished_tasks=UsageQuota(used=unfinished, limit=MAX_UNFINISHED),
        drafts=UsageQuota(used=drafts, limit=MAX_DRAFTS),
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
