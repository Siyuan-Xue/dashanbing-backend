from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import ApiKey, ApiKeyPublic


MAX_ACTIVE_API_KEYS = 5


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def api_key_status(api_key: ApiKey, *, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if api_key.revoked_at is not None:
        return "revoked"
    if _aware(api_key.expires_at) <= current:
        return "expired"
    return "active"


def active_api_key_count(
    session: Session,
    owner_id: int,
    *,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    return session.exec(
        select(func.count())
        .select_from(ApiKey)
        .where(
            ApiKey.owner_id == owner_id,
            ApiKey.revoked_at.is_(None),
            ApiKey.expires_at > current,
        )
    ).one()


def api_key_public(api_key: ApiKey, *, now: datetime | None = None) -> ApiKeyPublic:
    return ApiKeyPublic(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        last_four=api_key.last_four,
        status=api_key_status(api_key, now=now),
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
    )
