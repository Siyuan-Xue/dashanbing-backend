from importlib import import_module
from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from app.security import JWT_ALGORITHM, JWT_SECRET_KEY, create_access_token


@pytest.fixture
def client(tmp_path: Path):
    """Create an isolated database-backed application for each test."""
    main = import_module("app.main")
    database_url = f"sqlite:///{tmp_path / 'auth-demo.db'}"
    with TestClient(main.create_app(database_url), raise_server_exceptions=False) as test_client:
        yield test_client


def test_root_returns_the_demo_message(client: TestClient):
    """Catches a missing or incorrectly shaped public status response."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "FastAPI auth demo"}


def test_register_creates_a_public_user_without_password_fields(client: TestClient):
    """Catches registration returning the secret or failing to persist a user."""
    response = client.post(
        "/auth/register",
        json={"username": "new_user", "password": "safe-password"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": 1, "username": "new_user"}


def test_registration_stores_an_argon2_hash_that_verifies(client: TestClient):
    """Catches registration persisting a plaintext password or unusable hash."""
    response = client.post(
        "/auth/register",
        json={"username": "hashed_user", "password": "safe-password"},
    )

    from sqlmodel import Session, select

    from app.models import User
    from app.security import verify_password

    with Session(client.app.state.engine) as session:
        user = session.exec(select(User).where(User.username == "hashed_user")).one()

    assert response.status_code == 201
    assert user.hashed_password != "safe-password"
    assert verify_password("safe-password", user.hashed_password)


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", "safe-password"),
        ("u" * 51, "safe-password"),
        ("valid_user", "short7!"),
        ("valid_user", "p" * 129),
    ],
)
def test_registration_rejects_credentials_outside_the_required_length_bounds(
    client: TestClient,
    username: str,
    password: str,
):
    """Catches accepting usernames or passwords outside the API's safe bounds."""
    response = client.post("/auth/register", json={"username": username, "password": password})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("username", "password"),
    [("abc", "p" * 8), ("u" * 50, "p" * 128)],
)
def test_registration_accepts_credentials_at_the_required_length_bounds(
    client: TestClient,
    username: str,
    password: str,
):
    """Catches validation excluding credentials at the documented inclusive bounds."""
    response = client.post("/auth/register", json={"username": username, "password": password})

    assert response.status_code == 201


def test_registration_rejects_a_duplicate_username(client: TestClient):
    """Catches exposing a database error instead of reporting a registration conflict."""
    payload = {"username": "already_taken", "password": "safe-password"}
    assert client.post("/auth/register", json=payload).status_code == 201

    response = client.post("/auth/register", json=payload)

    assert response.status_code == 409


def test_login_returns_a_bearer_access_token_for_valid_credentials(client: TestClient):
    """Catches a token endpoint that cannot authenticate valid registered credentials."""
    assert client.post(
        "/auth/register",
        json={"username": "login_user", "password": "safe-password"},
    ).status_code == 201

    response = client.post(
        "/auth/token",
        data={"username": "login_user", "password": "safe-password"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert isinstance(response.json()["access_token"], str)
    assert response.json()["access_token"]


def test_login_token_contains_its_subject_and_a_thirty_minute_expiration(client: TestClient):
    """Catches issued JWTs missing their subject or using the wrong default expiration."""
    assert client.post(
        "/auth/register",
        json={"username": "expiring_user", "password": "safe-password"},
    ).status_code == 201
    issued_after = datetime.now(timezone.utc)
    token = client.post(
        "/auth/token",
        data={"username": "expiring_user", "password": "safe-password"},
    ).json()["access_token"]
    issued_before = datetime.now(timezone.utc)

    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    expiration = datetime.fromtimestamp(payload["exp"], timezone.utc)

    assert payload["sub"] == "expiring_user"
    assert issued_after + timedelta(minutes=29) <= expiration <= issued_before + timedelta(minutes=31)


@pytest.mark.parametrize(
    ("username", "password", "register_first"),
    [
        ("unknown_user", "safe-password", False),
        ("known_user", "wrong-password", True),
    ],
)
def test_login_rejects_unknown_or_wrong_credentials_with_a_bearer_challenge(
    client: TestClient,
    username: str,
    password: str,
    register_first: bool,
):
    """Catches credential failures being accepted or missing the OAuth bearer challenge."""
    if register_first:
        assert client.post(
            "/auth/register",
            json={"username": username, "password": "safe-password"},
        ).status_code == 201

    response = client.post("/auth/token", data={"username": username, "password": password})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_current_user_returns_the_authenticated_public_user(client: TestClient):
    """Catches a valid bearer token failing to identify its registered user."""
    assert client.post(
        "/auth/register",
        json={"username": "current_user", "password": "safe-password"},
    ).status_code == 201
    access_token = client.post(
        "/auth/token",
        data={"username": "current_user", "password": "safe-password"},
    ).json()["access_token"]

    response = client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json() == {"id": 1, "username": "current_user"}


@pytest.mark.parametrize(
    "token",
    [
        None,
        "not-a-jwt",
        jwt.encode(
            {"sub": "forged", "exp": 4_102_444_800},
            "wrong-secret-key-with-at-least-32-bytes",
            algorithm="HS256",
        ),
        create_access_token(
            "expired",
            expires_delta=timedelta(seconds=-1),
        ),
    ],
    ids=["missing", "malformed", "forged", "expired"],
)
def test_current_user_rejects_missing_forged_or_expired_tokens(
    client: TestClient,
    token: str | None,
):
    """Catches a protected endpoint accepting invalid bearer credentials."""
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}

    response = client.get("/users/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Could not validate credentials"}
