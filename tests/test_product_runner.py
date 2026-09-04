import json
import sys
from pathlib import Path

from research_engine.product_runner import _copy_product_outputs


def test_product_output_keeps_only_original_cameras_and_processed_mosaic(
    tmp_path: Path,
    monkeypatch,
):
    group = tmp_path / "engine-output" / "group_01"
    viz = group / "viz"
    viz.mkdir(parents=True)
    (group / "report.json").write_text("{}", encoding="utf-8")
    (group / "summary.json").write_text(
        json.dumps({"session_id": "session-01"}),
        encoding="utf-8",
    )
    (group / "motion.json").write_text("{}", encoding="utf-8")
    (viz / "phases.mp4").write_bytes(b"processed-mosaic")
    for camera in ("cam_01", "cam_02", "cam_03"):
        (viz / f"{camera}_annotated.mp4").write_bytes(f"annotated-{camera}".encode())
    (viz / "cam_04_ball.mp4").write_bytes(b"annotated-cam_04")

    data_root = tmp_path / "data"
    raw = data_root / "sessions" / "session-01" / "raw"
    raw.mkdir(parents=True)
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        (raw / f"{camera}.mp4").write_bytes(f"original-{camera}".encode())

    monkeypatch.setenv("BASKETBALL_DATA_ROOT", str(data_root))
    sys.modules.pop("src.config", None)
    output = tmp_path / "product-output"

    _copy_product_outputs(group, output)

    assert {path.name for path in (output / "viz").iterdir()} == {
        "cam_01_original.mp4",
        "cam_02_original.mp4",
        "cam_03_original.mp4",
        "cam_04_original.mp4",
        "phases.mp4",
    }
    assert json.loads((output / "media_manifest.json").read_text()) == {
        "cam_01": "cam_01_original.mp4",
        "cam_02": "cam_02_original.mp4",
        "cam_03": "cam_03_original.mp4",
        "cam_04": "cam_04_original.mp4",
        "phases": "phases.mp4",
    }
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        assert (output / "viz" / f"{camera}_original.mp4").stat().st_ino == (
            raw / f"{camera}.mp4"
        ).stat().st_ino


def test_link_or_copy_falls_back_when_hard_links_are_unavailable(tmp_path: Path, monkeypatch):
    from src.utils.files import link_or_copy_file

    source = tmp_path / "source.mp4"
    destination = tmp_path / "other-device" / "destination.mp4"
    source.write_bytes(b"original-video")

    def cross_device_link(_source, _destination):
        raise OSError("cross-device link")

    monkeypatch.setattr("src.utils.files.os.link", cross_device_link)

    link_or_copy_file(source, destination)

    assert destination.read_bytes() == b"original-video"
    assert destination.stat().st_ino != source.stat().st_ino
