import json
import sys
from pathlib import Path

from app.config import AppSettings
from app.services.readiness import ReadinessService


def test_simulation_readiness_is_explicitly_not_a_gpu_claim(tmp_path: Path):
    settings = AppSettings(
        runtime_root=tmp_path / "runtime",
        simulation_mode=True,
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
    )
    report = ReadinessService(settings).report()
    assert report["ready"] is True
    assert report["mode"] == "simulation"
    assert "不会执行真实推理" in report["checks"][0]["detail"]


def test_readiness_rejects_disabled_worker(tmp_path: Path):
    settings = AppSettings(
        runtime_root=tmp_path / "runtime",
        simulation_mode=True,
        worker_enabled=False,
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
    )

    report = ReadinessService(settings).report()
    worker = next(check for check in report["checks"] if check["name"] == "worker")

    assert report["ready"] is False
    assert worker["ready"] is False


def test_real_readiness_names_missing_active_models_and_sync(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setattr(
        "app.services.readiness.shutil.which",
        lambda executable: "/usr/bin/ffmpeg" if executable == "ffmpeg" else None,
    )
    settings = AppSettings(
        runtime_root=tmp_path / "runtime",
        model_root=tmp_path / "models",
        sync_config=tmp_path / "missing-sync.json",
        min_free_storage_gb=0,
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
    )
    settings.runtime_root.mkdir()
    report = ReadinessService(settings).report()
    failed = {item["name"] for item in report["checks"] if not item["ready"]}
    assert {
        "yolox",
        "rtmw",
        "yolo_pose",
        "osnet",
        "basketball",
        "buffalo_l",
        "sync_config",
        "ffprobe",
        "cuda",
    } <= failed
    assert "empty_frame_inference" not in {item["name"] for item in report["checks"]}


def test_sync_config_requires_cam03_anchor_and_finite_four_camera_offsets(tmp_path: Path):
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "anchor_camera": "cam_03",
                "camera_time_offsets_ms": {
                    "cam_01": 12.5,
                    "cam_02": -2,
                    "cam_03": 0,
                    "cam_04": 8,
                },
            }
        ),
        encoding="utf-8",
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            {
                "anchor_camera": "cam_02",
                "camera_time_offsets_ms": {
                    "cam_01": 0,
                    "cam_02": 0,
                    "cam_03": 1,
                    "cam_04": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    assert ReadinessService._valid_sync_file(valid)
    assert not ReadinessService._valid_sync_file(invalid)
