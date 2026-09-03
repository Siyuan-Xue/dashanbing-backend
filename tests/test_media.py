from pathlib import Path

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
    remuxed.write_bytes(b"remuxed")
    media = resolve_review_media(viz, {"cam_01": source})
    assert media["cam_01"] == remuxed


def test_remux_without_ffmpeg_copies_source_bytes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: None)
    src = tmp_path / "cam_01.mkv"
    dst = tmp_path / "viz" / "cam_01_original.mp4"
    src.write_bytes(b"source-bytes")

    result = remux_to_browser_mp4(src, dst)

    assert result == dst
    assert dst.read_bytes() == b"source-bytes"


def test_install_original_camera_videos_writes_product_filenames(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.services.media.shutil.which", lambda _name: None)
    viz = tmp_path / "viz"
    sources = {}
    for kind in ("cam_01", "cam_02", "cam_03", "cam_04"):
        path = tmp_path / f"{kind}.mkv"
        path.write_bytes(kind.encode())
        sources[kind] = path

    install_original_camera_videos(viz, sources)

    assert set(MEDIA_FILES) == {"cam_01", "cam_02", "cam_03", "cam_04", "phases"}
    assert (viz / "cam_02_original.mp4").read_bytes() == b"cam_02"
