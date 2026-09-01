import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "local-demo-secret-key-change-before-production")
JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRES_MINUTES = 30
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=DEFAULT_TOKEN_EXPIRES_MINUTES)
    )
    return jwt.encode({"sub": subject, "exp": expires_at}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
