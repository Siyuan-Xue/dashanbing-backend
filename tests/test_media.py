import subprocess
from pathlib import Path

import pytest

from app.services.media import (
    MEDIA_FILES,
    install_original_camera_videos,
    remux_to_browser_mp4,
    resolve_review_media,
)


def test_resolve_review_media_prefers_originals_over_annotated(tmp_path: Path):
    viz = tmp_path / "viz"
    viz.mkdir()
    (viz / "phases.mp4").write_bytes(b"mosaic")
    (viz / "cam_01_annotated.mp4").write_bytes(b"annotated")
    source = tmp_path / "cam_01.mkv"
    source.write_bytes(b"original")

    media = resolve_review_media(viz, {"cam_01": source})

    assert media["phases"] == viz / "phases.mp4"
    assert media["cam_01"] == source
    remuxed = viz / "cam_01_original.mp4"
    remuxed.write_bytes(b"partial")
    media = resolve_review_media(viz, {"cam_01": source})
    assert media["cam_01"] == source
    remuxed.write_bytes(b"r" * 1001)
    media = resolve_review_media(viz, {"cam_01": source})
    assert media["cam_01"] == remuxed


def test_remux_without_ffmpeg_rejects_non_mp4_source(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: None)
    src = tmp_path / "cam_01.mkv"
    dst = tmp_path / "viz" / "cam_01_original.mp4"
    src.write_bytes(b"source-bytes")

    with pytest.raises(RuntimeError, match="FFmpeg"):
        remux_to_browser_mp4(src, dst)


def test_remux_without_ffmpeg_copies_existing_mp4(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: None)
    src = tmp_path / "cam_01.mp4"
    dst = tmp_path / "viz" / "cam_01_original.mp4"
    src.write_bytes(b"source-bytes")

    result = remux_to_browser_mp4(src, dst)

    assert result == dst
    assert dst.read_bytes() == b"source-bytes"


def test_remux_publishes_completed_file_atomically(tmp_path: Path, monkeypatch):
    src = tmp_path / "cam_01.mkv"
    dst = tmp_path / "viz" / "cam_01_original.mp4"
    src.write_bytes(b"source")
    observed_outputs = []

    def successful_remux(command, **_kwargs):
        output = Path(command[-1])
        observed_outputs.append(output)
        assert output != dst
        output.write_bytes(b"x" * 1001)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.media.subprocess.run", successful_remux)

    result = remux_to_browser_mp4(src, dst)

    assert observed_outputs
    assert result == dst
    assert dst.read_bytes() == b"x" * 1001
    assert not any(path.exists() for path in observed_outputs)


def test_install_original_camera_videos_writes_product_filenames(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: None)
    viz = tmp_path / "viz"
    sources = {}
    for kind in ("cam_01", "cam_02", "cam_03", "cam_04"):
        path = tmp_path / f"{kind}.mp4"
        path.write_bytes(kind.encode())
        sources[kind] = path

    install_original_camera_videos(viz, sources)

    assert set(MEDIA_FILES) == {"cam_01", "cam_02", "cam_03", "cam_04", "phases"}
    assert (viz / "cam_02_original.mp4").read_bytes() == b"cam_02"
