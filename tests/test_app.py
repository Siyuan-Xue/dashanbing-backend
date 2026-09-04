from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import AppSettings
from app.database import create_tables
from app.main import create_app
from app.models import Analysis, User, UserRegistration
from app.api.routes.auth import register
from app.security import JWT_ALGORITHM, create_access_token, hash_password, verify_password


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


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/register",
        "/workspace/new",
        "/workspace/tasks",
        "/workspace/tasks/example-id",
        "/api/docs",
        "/api/docs/",
        "/api/keys",
        "/api/keys/",
    ],
)
def test_same_origin_deep_links_serve_the_spa_without_server_redirects(
    client: TestClient, path: str
):
    """Catches deployments that work through client navigation but 404 on refresh."""
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>product</title>" in response.text


def test_frontend_fallback_never_swallows_unknown_api_routes(client: TestClient):
    """Catches an API typo returning index.html with HTTP 200."""
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not found"}


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


def test_registration_normalizes_identity_and_returns_a_public_user(client: TestClient):
    """Catches storing unnormalized credentials or exposing the password hash."""
    response = client.post(
        "/api/v1/register",
        json={"username": "  NewUser  ", "email": "  PERSON@Example.COM ", "password": "new-password"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 2,
        "username": "newuser",
        "email": "person@example.com",
        "is_active": True,
    }
    assert "password" not in response.text


def test_registration_rejects_duplicate_normalized_username_or_email(client: TestClient):
    """Catches a case or whitespace variant creating a second account."""
    first = {"username": "CourtCoach", "email": "coach@example.com", "password": "new-password"}
    assert client.post("/api/v1/register", json=first).status_code == 201

    duplicate_username = client.post(
        "/api/v1/register",
        json={"username": " courtcoach ", "email": "other@example.com", "password": "new-password"},
    )
    duplicate_email = client.post(
        "/api/v1/register",
        json={"username": "othercoach", "email": " COACH@example.COM ", "password": "new-password"},
    )

    assert duplicate_username.status_code == 409
    assert duplicate_email.status_code == 409


def test_registration_rejects_an_email_matching_an_existing_username(client: TestClient):
    """Catches an ambiguous login identity spanning username and email fields."""
    assert client.post(
        "/api/v1/register",
        json={"username": "identity", "email": "owner@example.com", "password": "new-password"},
    ).status_code == 201

    response = client.post(
        "/api/v1/register",
        json={"username": "othercoach", "email": " IDENTITY ", "password": "new-password"},
    )

    assert response.status_code == 409


def test_registration_returns_conflict_when_a_duplicate_wins_the_insert_race(
    client: TestClient,
    configured_app,
):
    """Catches surfacing a database uniqueness race as a 500 response."""
    app, _ = configured_app
    inserted = False

    def insert_competing_user(session, _flush_context, _instances) -> None:
        nonlocal inserted
        if inserted or not any(
            isinstance(item, User) and item.username == "racingcoach" for item in session.new
        ):
            return
        inserted = True
        with Session(app.state.engine) as competing_session:
            competing_session.add(
                User(
                    username="racingcoach",
                    email="racing@example.com",
                    hashed_password="other-hash",
                )
            )
            competing_session.commit()

    event.listen(Session, "before_flush", insert_competing_user)
    try:
        response = client.post(
            "/api/v1/register",
            json={"username": "racingcoach", "email": "racing@example.com", "password": "new-password"},
        )
    finally:
        event.remove(Session, "before_flush", insert_competing_user)

    assert response.status_code == 409


def test_registration_returns_conflict_when_swapped_identities_race(
    client: TestClient,
    configured_app,
):
    """Catches two transactions committing the same identities in opposite fields."""
    app, _ = configured_app
    competing_result = None
    inserted = False

    def register_competing_user(session, _flush_context, _instances) -> None:
        nonlocal competing_result, inserted
        if inserted or not any(
            isinstance(item, User) and item.username == "racingcoach" for item in session.new
        ):
            return
        inserted = True
        with Session(app.state.engine) as competing_session:
            competing_result = register(
                UserRegistration(
                    username="racing@example.com",
                    email="racingcoach",
                    password="new-password",
                ),
                session=competing_session,
            )

    event.listen(Session, "before_flush", register_competing_user)
    try:
        response = client.post(
            "/api/v1/register",
            json={"username": "racingcoach", "email": "racing@example.com", "password": "new-password"},
        )
    finally:
        event.remove(Session, "before_flush", register_competing_user)

    assert response.status_code == 409
    assert competing_result is not None
    with Session(app.state.engine) as session:
        users = list(
            session.exec(
                select(User).where(User.username.in_(["racingcoach", "racing@example.com"]))
            )
        )
    assert len(users) == 1


def test_mixed_case_bootstrap_username_can_log_in(tmp_path: Path):
    """Catches normalizing OAuth input differently from bootstrap account storage."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'mixed-case-bootstrap.db'}",
        runtime_root=tmp_path / "runtime",
        admin_username="Local_Admin",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )

    with TestClient(create_app(settings=settings)) as bootstrap_client:
        response = bootstrap_client.post(
            "/api/v1/login/access-token",
            data={"username": "LOCAL_admin", "password": "correct-password"},
        )

    assert response.status_code == 200


def test_preexisting_unicode_bootstrap_username_can_log_in(tmp_path: Path):
    """Catches using database lower() instead of the Python casefold contract for legacy users."""
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'unicode-bootstrap.db'}",
        runtime_root=tmp_path / "runtime",
        admin_username="STRASSE",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
    )
    app = create_app(settings=settings)
    create_tables(app.state.engine)
    with Session(app.state.engine) as session:
        session.add(User(username="Straße", hashed_password=hash_password("correct-password")))
        session.commit()

    with TestClient(app) as bootstrap_client:
        response = bootstrap_client.post(
            "/api/v1/login/access-token",
            data={"username": "STRASSE", "password": "correct-password"},
        )

    assert response.status_code == 200


def test_login_accepts_normalized_email(client: TestClient):
    """Catches looking up OAuth2's username field only as a username."""
    assert client.post(
        "/api/v1/register",
        json={"username": "emailcoach", "email": "coach@example.com", "password": "new-password"},
    ).status_code == 201

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": " COACH@EXAMPLE.COM ", "password": "new-password"},
    )

    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/users/me").json()["username"] == "emailcoach"


def test_login_rejects_an_inactive_user(client: TestClient, configured_app):
    """Catches authenticating an account after it has been administratively disabled."""
    app, _ = configured_app
    assert client.post(
        "/api/v1/register",
        json={"username": "inactive", "email": "inactive@example.com", "password": "new-password"},
    ).status_code == 201
    with Session(app.state.engine) as session:
        user = session.exec(select(User).where(User.username == "inactive")).one()
        user.is_active = False
        session.add(user)
        session.commit()

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "inactive@example.com", "password": "new-password"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_analysis_owner_is_required(configured_app):
    """Catches a new analysis silently falling back to the bootstrap tenant."""
    app, _ = configured_app
    with TestClient(app):
        with Session(app.state.engine) as session:
            session.add(Analysis(title="unowned", input_manifest_json="{}"))
            with pytest.raises(IntegrityError):
                session.commit()


def test_unknown_api_does_not_fall_back_to_spa(client: TestClient):
    assert client.get("/api/v1/not-real").status_code == 404


def test_liveness_and_simulation_readiness_are_distinct(client: TestClient):
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["mode"] == "simulation"
    worker = next(check for check in response.json()["checks"] if check["name"] == "worker")
    assert worker["ready"] is False
