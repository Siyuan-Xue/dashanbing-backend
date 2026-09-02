import json
from pathlib import Path

import pytest

from app.services.presets import PresetCatalog


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    group = root / "outputs" / "v3" / "group_04"
    write_json(
        group / "report.json",
        {
            "clips": [
                {
                    "clip_id": "stu_00:1",
                    "student_id": "stu_00",
                    "action_type": "jump_shot",
                    "start_ms": 1_000,
                    "end_ms": 2_000,
                    "release_ms": 1_800,
                }
            ],
            "shot_outcomes": [{"clip_id": "stu_00:1", "made": True}],
            "shot_stats": {"attempts": 1, "makes": 1, "misses": 0, "undetermined": 0},
        },
    )
    write_json(
        group / "summary.json",
        {
            "group_id": "group_04",
            "student_ids": ["stu_00", "stu_01", "stu_02", "stu_03"],
            "clip_count": 1,
            "action_type_hist": {"jump_shot": 1},
        },
    )
    write_json(group / "eval_vs_gt.json", {"precision": 1.0, "recall": 1.0})
    write_json(
        root / "outputs" / "v3" / "manifest.json",
        {"groups": [{"group_id": "group_04", "clip_count": 99, "action_type_hist": {"layup": 99}}]},
    )
    viz = group / "viz"
    viz.mkdir()
    for name in (
        "cam_01_annotated.mp4",
        "cam_02_annotated.mp4",
        "cam_03_annotated.mp4",
        "cam_04_ball.mp4",
        "phases.mp4",
    ):
        (viz / name).write_bytes(b"video")
    inputs = root / "test_data_v3"
    inputs.mkdir(parents=True)
    for name in ("0-2.mkv", "4-1.mkv", "4-2.mkv", "4-3.mkv", "4-4.mkv"):
        (inputs / name).write_bytes(b"input")
    sync = inputs / "sync"
    sync.mkdir()
    (sync / "group_04.json").write_text("{}", encoding="utf-8")
    return root


def test_preset_result_uses_group_report_instead_of_stale_root_manifest(sample_root: Path):
    """Catches stale root manifest values overriding the final per-group result."""
    catalog = PresetCatalog(sample_root)

    result = catalog.result("quick-demo")

    assert result.action_counts.jump_shot == 1
    assert result.action_counts.layup == 0
    assert result.registered_participant_count == 4
    assert any("manifest" in warning for warning in result.warnings)


def test_preset_media_rejects_unknown_kinds_and_path_traversal(sample_root: Path):
    """Catches the media API being able to read arbitrary files from the sample bundle."""
    catalog = PresetCatalog(sample_root)

    assert catalog.media_path("quick-demo", "phases") == (
        sample_root / "outputs" / "v3" / "group_04" / "viz" / "phases.mp4"
    )
    with pytest.raises(KeyError):
        catalog.media_path("quick-demo", "../../report")
    with pytest.raises(KeyError):
        catalog.media_path("missing", "phases")


def test_preset_result_rejects_incomplete_review_media(sample_root: Path):
    (sample_root / "outputs" / "v3" / "group_04" / "viz" / "cam_01_annotated.mp4").unlink()

    with pytest.raises(FileNotFoundError):
        PresetCatalog(sample_root).result("quick-demo")


def test_preset_rerun_manifest_binds_registration_cameras_and_group_sync(sample_root: Path):
    """Catches reruns using the wrong registration camera or a shared sync file."""
    catalog = PresetCatalog(sample_root)

    manifest = catalog.rerun_manifest("quick-demo")

    assert manifest == {
        "enrollment_video": str(sample_root / "test_data_v3" / "0-2.mkv"),
        "cam_01": str(sample_root / "test_data_v3" / "4-1.mkv"),
        "cam_02": str(sample_root / "test_data_v3" / "4-2.mkv"),
        "cam_03": str(sample_root / "test_data_v3" / "4-3.mkv"),
        "cam_04": str(sample_root / "test_data_v3" / "4-4.mkv"),
        "sync": str(sample_root / "test_data_v3" / "sync" / "group_04.json"),
    }
