"""Opt-in setup for legacy business API tests under the role/sync contracts."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.input_preview import timeline_metadata
from app.services.storage import looks_like_video_header


BUSINESS_USERNAME = "fixturecoach"
BUSINESS_PASSWORD = "correct-password"
CAMERAS = ("cam_01", "cam_02", "cam_03", "cam_04")
SELECTED_TIMESTAMPS_MS = dict(zip(CAMERAS, (200, 240, 160, 200)))
PRESET_SYNC = {
    "anchor_camera": "cam_03",
    "camera_time_offsets_ms": dict(zip(CAMERAS, (40, 80, 0, 40))),
}


def register_business_user(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/register",
        json={
            "username": BUSINESS_USERNAME,
            "email": f"{BUSINESS_USERNAME}@example.com",
            "password": BUSINESS_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    user = response.json()
    assert user["role"] == "user"
    return user


def login_business_user(client: TestClient):
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": BUSINESS_USERNAME, "password": BUSINESS_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.cookies.get("access_token")
    return response


def install_mock_video_probe(client: TestClient, monkeypatch) -> None:
    """Replace media decoding only; retain file, version and sync validation.

    Synthetic byte fixtures model 50 frames at 25 fps with a nonzero source PTS.
    Every selected timestamp is an actual frame in this two-second timeline.
    This is local to the requesting fixture and restored by monkeypatch.
    """
    def probe(path: Path, _title: str) -> None:
        assert looks_like_video_header(path.read_bytes()[:16])

    def inspect(path: Path) -> dict:
        assert path.is_file() and path.stat().st_size > 0
        return timeline_metadata([4000 + index * 40 for index in range(50)], 25)

    monkeypatch.setattr(client.app.state.storage, "video_probe", probe)
    monkeypatch.setattr("app.services.input_preview.inspect_video", inspect)


def upload_form(title: str, mode: str = "quick") -> dict:
    return {
        "title": title,
        "mode": mode,
        "enrollment_mode": "sequential",
        "expected_persons": "4",
        "analyst_locale": "zh",
        "sync": json.dumps({"selected_timestamps_ms": SELECTED_TIMESTAMPS_MS}),
    }


def confirm_task_sync(client: TestClient, task_id: str) -> dict:
    current = client.get(f"/api/v1/tasks/{task_id}/sync")
    assert current.status_code == 200, current.text
    versions = current.json()["source_versions"]
    assert set(versions) == set(CAMERAS)
    response = client.put(
        f"/api/v1/tasks/{task_id}/sync",
        json={"input_versions": versions, "selected_timestamps_ms": SELECTED_TIMESTAMPS_MS},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    assert response.json()["config"]["input_versions"] == versions
    return response.json()["config"]
