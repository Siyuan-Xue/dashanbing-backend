from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.requests import Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_session
from app.models import Token, User, UserPublic, UserRegistration
from app.security import DUMMY_PASSWORD_HASH, create_access_token, hash_password, normalize_identity, verify_password
from app.services.identities import ensure_user_identities, find_user_by_identity


router = APIRouter(tags=["authentication"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegistration, session: Session = Depends(get_session)) -> User:
    if (
        find_user_by_identity(session, payload.username) is not None
        or find_user_by_identity(session, payload.email) is not None
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email is already registered")
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    session.add(user)
    try:
        session.flush()
        ensure_user_identities(session, user)
        session.commit()
    except (IntegrityError, ValueError) as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered",
        ) from error
    session.refresh(user)
    return user


@router.post("/login/access-token", response_model=Token)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    identity = normalize_identity(form_data.username)
    user = find_user_by_identity(session, identity)
    password_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    valid = verify_password(form_data.password, password_hash)
    if user is None or not user.is_active or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = request.app.state.settings
    token = create_access_token(
        user.username,
        timedelta(minutes=settings.access_token_minutes),
        secret_key=settings.jwt_secret_key,
    )
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_minutes * 60,
        path="/",
    )
    return Token(access_token=token, token_type="bearer")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie("access_token", path="/", httponly=True, samesite="lax")


@router.get("/users/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
