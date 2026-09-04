import json
import subprocess
from pathlib import Path

import pytest

from app.services.storage import InvalidVideoUpload, probe_video_file


def test_probe_video_file_accepts_supported_container_with_decodable_stream(
    tmp_path: Path,
    monkeypatch,
):
    source = tmp_path / "clip.mkv"
    source.write_bytes(b"\x1a\x45\xdf\xa3payload")
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {
                "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
                "format": {"format_name": "matroska,webm", "duration": "12.08"},
            }
        ),
        stderr="",
    )
    monkeypatch.setattr("app.services.storage.shutil.which", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr("app.services.storage.subprocess.run", lambda *_args, **_kwargs: completed)

    probe_video_file(source, "注册视频")


@pytest.mark.parametrize(
    ("returncode", "payload"),
    [
        (1, {}),
        (0, {"streams": [], "format": {"format_name": "matroska,webm", "duration": "12"}}),
        (
            0,
            {
                "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
                "format": {"format_name": "matroska,webm", "duration": "0"},
            },
        ),
        (
            0,
            {
                "streams": [{"codec_type": "video", "width": 1505, "height": 2128}],
                "format": {"format_name": "mjpeg_2000", "duration": "1"},
            },
        ),
    ],
)
def test_probe_video_file_rejects_spoofed_or_unusable_video(
    tmp_path: Path,
    monkeypatch,
    returncode: int,
    payload: dict,
):
    source = tmp_path / "spoofed.mkv"
    source.write_bytes(b"\x1a\x45\xdf\xa3not-a-real-video")
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="invalid data",
    )
    monkeypatch.setattr("app.services.storage.shutil.which", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr("app.services.storage.subprocess.run", lambda *_args, **_kwargs: completed)

    with pytest.raises(InvalidVideoUpload, match="注册视频"):
        probe_video_file(source, "注册视频")
