from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.database import get_session
from app.models import ApiKey, ApiKeyCreate, ApiKeyCreated, ApiKeyPublic, User
from app.security import api_key_digest, create_api_key_secret
from app.services.api_keys import MAX_ACTIVE_API_KEYS, active_api_key_count, api_key_public
from app.services.tasks import begin_write, utc_now


router = APIRouter(prefix="/api-keys", tags=["API keys"])


@router.get("", response_model=list[ApiKeyPublic])
def list_api_keys(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ApiKeyPublic]:
    keys = session.exec(
        select(ApiKey)
        .where(ApiKey.owner_id == current_user.id)
        .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
    ).all()
    now = utc_now()
    return [api_key_public(api_key, now=now) for api_key in keys]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ApiKeyCreated:
    begin_write(session)
    now = utc_now()
    if active_api_key_count(session, current_user.id, now=now) >= MAX_ACTIVE_API_KEYS:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Active API key quota exceeded (maximum 5)",
        )
    secret = create_api_key_secret()
    api_key = ApiKey(
        owner_id=current_user.id,
        name=payload.name,
        digest=api_key_digest(secret, request.app.state.settings.jwt_secret_key),
        prefix=secret[:16],
        last_four=secret[-4:],
        created_at=now,
        expires_at=now + timedelta(days=payload.expires_in_days),
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    public = api_key_public(api_key, now=now)
    return ApiKeyCreated(**public.model_dump(), secret=secret)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    begin_write(session)
    api_key = session.exec(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.owner_id == current_user.id)
    ).first()
    if api_key is None:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = utc_now()
        session.add(api_key)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
