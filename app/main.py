from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import DEFAULT_DATABASE_URL, create_database_engine, create_tables
from app.database import get_session
from app.models import Token, User, UserPublic, UserRegistration
from app.security import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
    hash_password,
    oauth2_scheme,
    verify_password,
)


def create_app(database_url: str = DEFAULT_DATABASE_URL) -> FastAPI:
    """Build the FastAPI application against the supplied database URL."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        create_tables(app.state.engine)
        yield

    application = FastAPI(title="FastAPI Auth Demo", lifespan=lifespan)
    application.state.engine = create_database_engine(database_url)

    @application.get("/")
    def root() -> dict[str, str]:
        return {"message": "FastAPI auth demo"}

    @application.post("/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
    def register_user(
        registration: UserRegistration,
        session: Session = Depends(get_session),
    ) -> User:
        user = User(
            username=registration.username,
            hashed_password=hash_password(registration.password),
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already registered",
            ) from error
        session.refresh(user)
        return user

    @application.post("/auth/token", response_model=Token)
    def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),
        session: Session = Depends(get_session),
    ) -> Token:
        user = session.exec(select(User).where(User.username == form_data.username)).first()
        if user is None or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Token(access_token=create_access_token(user.username), token_type="bearer")

    def get_current_user(
        token: str | None = Depends(oauth2_scheme),
        session: Session = Depends(get_session),
    ) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if token is None:
            raise credentials_exception
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
        except jwt.PyJWTError as error:
            raise credentials_exception from error
        if not isinstance(username, str):
            raise credentials_exception

        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            raise credentials_exception
        return user

    @application.get("/users/me", response_model=UserPublic)
    def read_current_user(current_user: User = Depends(get_current_user)) -> User:
        return current_user

    return application


app = create_app()
