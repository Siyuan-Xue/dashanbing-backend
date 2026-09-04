import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "local-demo-secret-key-change-before-production")
JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRES_MINUTES = 30
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$MmQe3+JAl57f0Wy3ffOTgw$ieveehGfSL5dfPPt3qicvCWuNOxJOBur15kq/rnEoJI"
)
password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login/access-token", auto_error=False)


def normalize_identity(value: str) -> str:
    return value.strip().casefold()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    *,
    secret_key: str = JWT_SECRET_KEY,
) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=DEFAULT_TOKEN_EXPIRES_MINUTES)
    )
    return jwt.encode({"sub": subject, "exp": expires_at}, secret_key, algorithm=JWT_ALGORITHM)
