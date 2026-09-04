from pathlib import Path

import pytest

from research_engine.src.utils.video_io import remux_to_mp4


def test_research_remux_never_disguises_non_mp4_when_ffmpeg_is_missing(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "camera.mkv"
    destination = tmp_path / "camera.mp4"
    source.write_bytes(b"matroska" * 200)
    destination.symlink_to(source)
    monkeypatch.setattr("research_engine.src.utils.video_io.shutil.which", lambda _name: None)

    with pytest.raises(RuntimeError, match="ffmpeg"):
        remux_to_mp4(source, destination)

    assert not destination.exists()
