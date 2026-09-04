import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import Session

from app.config import AppSettings
from app.main import create_app
from app.models import Analysis, ApiKeyCreated, SubmissionEvent


@pytest.fixture
def client(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'api-keys.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        model_root=tmp_path / "models",
        sync_config=tmp_path / "sync.json",
        admin_username="admin",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
        simulation_mode=True,
        worker_enabled=False,
        auto_create_schema=True,
        min_free_storage_gb=0,
        enrollment_retention_days=8,
        raw_retention_days=31,
        result_retention_days=181,
    )
    with TestClient(create_app(settings=settings), raise_server_exceptions=False) as test_client:
        login = test_client.post(
            "/api/v1/login/access-token",
            data={"username": "admin", "password": "correct-password"},
        )
        assert login.status_code == 200
        yield test_client


def _register_and_token(client: TestClient, username: str) -> tuple[int, str]:
    registered = client.post(
        "/api/v1/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "new-password",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/login/access-token",
        data={"username": username, "password": "new-password"},
    )
    assert login.status_code == 200
    return registered.json()["id"], login.json()["access_token"]


def _create_key(client: TestClient, name: str = "Automation", **kwargs) -> dict:
    response = client.post("/api/v1/api-keys", json={"name": name}, **kwargs)
    assert response.status_code == 201
    return response.json()


def test_key_secret_is_disclosed_once_and_only_its_hmac_is_stored(client: TestClient):
    """Catches persisting or re-listing the bearer secret instead of a keyed verifier."""
    created = _create_key(client)
    secret = created["secret"]

    assert secret.startswith("dsb_live_")
    assert created["prefix"] == secret[:16]
    assert created["last_four"] == secret[-4:]
    assert 89 <= (
        datetime.fromisoformat(created["expires_at"].replace("Z", "+00:00"))
        - datetime.now(timezone.utc)
    ).days <= 90

    listed = client.get("/api/v1/api-keys")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "secret" not in listed.json()[0]
    assert secret not in listed.text
    assert secret not in repr(ApiKeyCreated.model_validate(created))

    with client.app.state.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT digest, prefix, last_four FROM api_key WHERE id = :id"
            ),
            {"id": created["id"]},
        ).one()
        columns = {column["name"] for column in inspect(connection).get_columns("api_key")}

    expected = hmac.new(
        client.app.state.settings.jwt_secret_key.encode(),
        secret.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert row == (expected, secret[:16], secret[-4:])
    assert secret not in row
    assert {"secret", "token", "plaintext"}.isdisjoint(columns)


def test_invalid_expired_and_revoked_keys_are_rejected(client: TestClient):
    """Catches accepting a key without an exact active database record."""
    assert client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer dsb_live_not-a-real-key"},
    ).status_code == 401

    expired = _create_key(client, "Expired")
    revoked = _create_key(client, "Revoked")
    with client.app.state.engine.begin() as connection:
        connection.execute(
            text("UPDATE api_key SET expires_at = '2000-01-01 00:00:00' WHERE id = :id"),
            {"id": expired["id"]},
        )
    assert client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired['secret']}"},
    ).status_code == 401

    deleted = client.delete(f"/api/v1/api-keys/{revoked['id']}")
    assert deleted.status_code == 204
    assert client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {revoked['secret']}"},
    ).status_code == 401


def test_api_key_listing_and_revocation_are_owner_scoped(client: TestClient):
    """Catches one tenant viewing or revoking another tenant's credentials."""
    admin_key = _create_key(client, "Admin key")
    _, other_token = _register_and_token(client, "othercoach")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    other_key = _create_key(client, "Other key", headers=other_headers)

    listed = client.get("/api/v1/api-keys", headers=other_headers)
    assert [item["id"] for item in listed.json()] == [other_key["id"]]
    assert client.delete(
        f"/api/v1/api-keys/{admin_key['id']}", headers=other_headers
    ).status_code == 404

    client.cookies.clear()
    assert client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_key['secret']}"},
    ).status_code == 200


def test_only_five_active_keys_are_allowed_per_user(client: TestClient):
    """Catches quota checks that count the wrong owner or revoked/expired keys."""
    keys = [_create_key(client, f"Key {index}") for index in range(5)]
    limited = client.post("/api/v1/api-keys", json={"name": "Sixth"})
    assert limited.status_code == 429

    assert client.delete(f"/api/v1/api-keys/{keys[0]['id']}").status_code == 204
    replacement = client.post("/api/v1/api-keys", json={"name": "Replacement"})
    assert replacement.status_code == 201

    with client.app.state.engine.begin() as connection:
        connection.execute(
            text("UPDATE api_key SET expires_at = '2000-01-01 00:00:00' WHERE id = :id"),
            {"id": keys[1]["id"]},
        )
    assert client.post("/api/v1/api-keys", json={"name": "After expiry"}).status_code == 201


def test_authorization_header_deterministically_precedes_browser_cookie(client: TestClient):
    """Catches a stale browser cookie overriding an explicit API-tooling bearer token."""
    other_id, other_token = _register_and_token(client, "headercoach")
    admin_login = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "correct-password"},
    )
    assert admin_login.status_code == 200

    jwt_user = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert jwt_user.status_code == 200
    assert jwt_user.json()["id"] == other_id

    invalid_api_key = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer dsb_live_invalid"},
    )
    assert invalid_api_key.status_code == 401


def test_api_key_authenticates_task_access_and_updates_last_used(client: TestClient):
    """Catches API-key auth losing tenant scope or omitting auditable use tracking."""
    other_id, other_token = _register_and_token(client, "toolcoach")
    client.cookies.clear()
    key = _create_key(
        client,
        headers={"Authorization": f"Bearer {other_token}"},
    )

    admin_login = client.post(
        "/api/v1/login/access-token",
        data={"username": "admin", "password": "correct-password"},
    )
    assert admin_login.status_code == 200
    created = client.post(
        "/api/v1/tasks",
        json={"title": "API-created draft", "mode": "quick"},
        headers={"Authorization": f"Bearer {key['secret']}"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    with Session(client.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        assert task.owner_id == other_id
        last_used_at = session.exec(
            text("SELECT last_used_at FROM api_key WHERE id = :id").bindparams(id=key["id"])
        ).one()
    assert last_used_at is not None


def test_account_usage_uses_owner_scoped_server_side_counts(client: TestClient):
    """Catches quota cards using mutable task timestamps, global rows, or client counts."""
    registered = client.post(
        "/api/v1/register",
        json={
            "username": "usageother",
            "email": "usageother@example.com",
            "password": "new-password",
        },
    )
    assert registered.status_code == 201
    other_id = registered.json()["id"]
    now = datetime.now(timezone.utc)
    with Session(client.app.state.engine) as session:
        session.add(
            Analysis(
                id="admin-draft",
                title="Draft",
                status="draft",
                input_manifest_json="{}",
                owner_id=1,
            )
        )
        session.add(
            Analysis(
                id="admin-queued",
                title="Queued",
                status="queued",
                input_manifest_json="{}",
                owner_id=1,
                submitted_at=now,
            )
        )
        session.add(
            SubmissionEvent(
                task_id="deleted-admin-task",
                owner_id=1,
                kind="retry",
                submitted_at=now,
            )
        )
        session.add(
            Analysis(
                id="other-draft",
                title="Other",
                status="draft",
                input_manifest_json="{}",
                owner_id=other_id,
            )
        )
        session.commit()
    _create_key(client)

    response = client.get("/api/v1/account/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["submitted_today"] == {"used": 2, "limit": 20}
    assert payload["unfinished_tasks"] == {"used": 2, "limit": 5}
    assert payload["drafts"] == {"used": 1, "limit": 3}
    assert payload["active_api_keys"] == {"used": 1, "limit": 5}
    assert payload["retention"] == {
        "drafts": "24 hours",
        "enrollment_data": "8 days",
        "raw_inputs": "31 days",
        "results": "181 days",
    }

def test_api_key_and_usage_endpoints_require_authentication(client: TestClient):
    """Catches accidentally publishing credential management or account metrics."""
    client.cookies.clear()
    assert client.get("/api/v1/api-keys").status_code == 401
    assert client.post("/api/v1/api-keys", json={"name": "Nope"}).status_code == 401
    assert client.get("/api/v1/account/usage").status_code == 401


@pytest.mark.parametrize("name", ["   ", 17])
def test_api_key_name_validation_returns_a_client_error(client: TestClient, name):
    """Catches malformed names escaping validation as empty records or server errors."""
    response = client.post("/api/v1/api-keys", json={"name": name})
    assert response.status_code == 422
