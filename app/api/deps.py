import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
from app.security import JWT_ALGORITHM


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get("access_token")
    authorization = request.headers.get("Authorization", "")
    if token is None and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
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
    if user is None:
        raise _unauthorized()
    return user
