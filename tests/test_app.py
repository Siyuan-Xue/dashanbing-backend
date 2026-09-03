from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import AppSettings
from app.main import create_app
from app.models import User
from app.security import JWT_ALGORITHM, create_access_token, verify_password


@pytest.fixture
def configured_app(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><title>product</title>", encoding="utf-8")
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        model_root=tmp_path / "models",
        sync_config=tmp_path / "sync.json",
        frontend_dist=frontend,
        admin_username="local_admin",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        access_token_minutes=30,
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    return create_app(settings=settings), settings


@pytest.fixture
def client(configured_app):
    app, _ = configured_app
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_same_origin_root_serves_the_built_frontend(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>product</title>" in response.text


def test_first_start_bootstraps_one_argon2_admin(configured_app):
    app, _ = configured_app
    with TestClient(app):
        with Session(app.state.engine) as session:
            users = list(session.exec(select(User)).all())
    assert len(users) == 1
    assert users[0].username == "local_admin"
    assert users[0].hashed_password != "correct-password"
    assert verify_password("correct-password", users[0].hashed_password)


def test_default_credentials_do_not_bootstrap_admin(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'default-credentials.db'}",
        runtime_root=tmp_path / "runtime",
        admin_password="change-me-local-admin",
        jwt_secret_key="change-this-local-jwt-secret-before-deployment-please",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)

    with TestClient(app):
        with Session(app.state.engine) as session:
            users = list(session.exec(select(User)).all())

    assert users == []


def test_readiness_rejects_admin_password_that_does_not_match_database(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'credential-mismatch.db'}"
    original = AppSettings(
        database_url=database_url,
        runtime_root=tmp_path / "runtime",
        admin_username="local_admin",
        admin_password="original-secure-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    with TestClient(create_app(settings=original)):
        pass

    changed = original.model_copy(
        update={"admin_password": "different-secure-password", "worker_enabled": True}
    )
    with TestClient(create_app(settings=changed)) as client:
        response = client.get("/readyz")

    credentials = next(
        check for check in response.json()["checks"] if check["name"] == "credentials"
    )
    assert response.status_code == 503
    assert credentials["ready"] is False
    assert "数据库" in credentials["detail"]


def test_login_issues_configured_expiring_token_and_cookie(client: TestClient, configured_app):
    _, settings = configured_app
    issued_after = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "local_admin", "password": "correct-password"},
    )
    issued_before = datetime.now(timezone.utc)
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
    expiration = datetime.fromtimestamp(payload["exp"], timezone.utc)
    assert payload["sub"] == "local_admin"
    assert issued_after + timedelta(minutes=29) <= expiration <= issued_before + timedelta(minutes=31)
    assert "httponly" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize("username,password", [("missing", "correct-password"), ("local_admin", "wrong-password")])
def test_login_rejects_unknown_or_wrong_credentials(client: TestClient, username: str, password: str):
    response = client.post("/api/v1/login/access-token", data={"username": username, "password": password})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_current_user_accepts_bearer_for_api_tooling(client: TestClient, configured_app):
    _, settings = configured_app
    token = create_access_token("local_admin", secret_key=settings.jwt_secret_key)
    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "local_admin"


@pytest.mark.parametrize("kind", ["missing", "malformed", "forged", "expired", "no_exp"])
def test_current_user_rejects_invalid_tokens(client: TestClient, configured_app, kind: str):
    _, settings = configured_app
    token = None
    if kind == "malformed":
        token = "not-a-jwt"
    elif kind == "forged":
        token = jwt.encode(
            {"sub": "local_admin", "exp": 4_102_444_800},
            "wrong-secret-key-with-at-least-thirty-two-characters",
            algorithm="HS256",
        )
    elif kind == "expired":
        token = create_access_token(
            "local_admin",
            expires_delta=timedelta(seconds=-1),
            secret_key=settings.jwt_secret_key,
        )
    elif kind == "no_exp":
        token = jwt.encode({"sub": "local_admin"}, settings.jwt_secret_key, algorithm="HS256")
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401


def test_no_registration_and_unknown_api_does_not_fall_back_to_spa(client: TestClient):
    assert client.post("/auth/register", json={"username": "x", "password": "password"}).status_code in {404, 405}
    assert client.get("/api/v1/not-real").status_code == 404


def test_liveness_and_simulation_readiness_are_distinct(client: TestClient):
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["mode"] == "simulation"
    worker = next(check for check in response.json()["checks"] if check["name"] == "worker")
    assert worker["ready"] is False
