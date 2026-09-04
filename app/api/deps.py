from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import ApiKey, User
from app.security import API_KEY_PREFIX, JWT_ALGORITHM, api_key_digest


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    authorization = request.headers.get("Authorization")
    if authorization is not None:
        token = _bearer_token(authorization)
        if token is None:
            raise _unauthorized()
        if token.startswith(API_KEY_PREFIX):
            return _get_api_key_user(request, session, token)
    else:
        token = request.cookies.get("access_token")
    if not token:
        raise _unauthorized()
    try:
        payload = jwt.decode(
            token,
            request.app.state.settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as error:
        raise _unauthorized() from error
    username = payload.get("sub")
    if not isinstance(username, str):
        raise _unauthorized()
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def _bearer_token(authorization: str) -> str | None:
    if len(authorization) < 8 or authorization[:7].lower() != "bearer ":
        return None
    token = authorization[7:]
    if not token or any(character.isspace() for character in token):
        return None
    return token


def _get_api_key_user(request: Request, session: Session, secret: str) -> User:
    digest = api_key_digest(secret, request.app.state.settings.jwt_secret_key)
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    api_key = session.exec(select(ApiKey).where(ApiKey.digest == digest)).first()
    now = datetime.now(timezone.utc)
    if api_key is None or api_key.revoked_at is not None or _aware(api_key.expires_at) <= now:
        session.rollback()
        raise _unauthorized()
    user = session.get(User, api_key.owner_id)
    if user is None or not user.is_active:
        session.rollback()
        raise _unauthorized()
    if api_key.last_used_at is None or _aware(api_key.last_used_at) < now:
        api_key.last_used_at = now
        session.add(api_key)
    session.commit()
    return user


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
