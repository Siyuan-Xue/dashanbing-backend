"""Browser-compatible video encoding helpers."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def remux_to_mp4(src: Path, dst: Path) -> Path:
    """Publish a browser-compatible MP4 atomically; never relabel another container."""
    src = Path(src)
    dst = Path(dst)
    if not src.is_file():
        raise FileNotFoundError(src)
    if src.absolute() == dst.absolute():
        return dst
    if dst.is_symlink():
        dst.unlink()
    if dst.is_file() and dst.stat().st_size > 1000:
        return dst
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found; cannot prepare browser-compatible MP4")

    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = dst.with_name(f".{dst.stem}.{uuid.uuid4().hex}.tmp{dst.suffix}")
    try:
        copied = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-c",
                "copy",
                "-an",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if copied.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 1000:
            temporary.replace(dst)
            return dst

        encoded = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            capture_output=True,
            text=True,
        )
        if encoded.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 1000:
            temporary.replace(dst)
            return dst
        detail = (encoded.stderr or encoded.stdout or "ffmpeg failed").strip().splitlines()
        tail = " ".join(detail[-6:]) if detail else "ffmpeg failed"
        raise RuntimeError(
            f"无法解码 {src.name}。请确认上传的是真实视频，而不是改过扩展名的文档。{tail}"
        )
    finally:
        temporary.unlink(missing_ok=True)


class H264VideoWriter:
    """Write MP4 with H.264 (yuv420p + faststart) for web/desktop players."""

    def __init__(self, path: str | Path, fps: float, frame_size: tuple[int, int]):
        if not ffmpeg_available():
            raise RuntimeError("ffmpeg not found; install ffmpeg for H.264 export")

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        width, height = frame_size
        self._proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-f",
                "rawvideo",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{width}x{height}",
                "-pix_fmt",
                "bgr24",
                "-r",
                str(fps),
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(self.path),
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def write(self, frame) -> None:
        if self._proc.stdin is None:
            raise RuntimeError("ffmpeg stdin closed")
        self._proc.stdin.write(frame.tobytes())

    def release(self) -> None:
        if self._proc.stdin is not None:
            self._proc.stdin.close()
        self._proc.wait()
        if self._proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to encode {self.path}")


def transcode_to_h264(src: Path, dst: Path | None = None) -> Path:
    """Re-encode an existing video to H.264 for compatibility."""
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg not found")

    src = Path(src)
    if dst is None:
        dst = src.with_name(f"{src.stem}_h264{src.suffix}")
    else:
        dst = Path(dst)

    tmp = dst.with_suffix(".tmp.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(tmp),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.replace(dst)
    return dst


def create_video_writer(path: str | Path, fps: float, frame_size: tuple[int, int]):
    """Prefer H.264 via ffmpeg; fall back to OpenCV mp4v + transcode."""
    try:
        return H264VideoWriter(path, fps, frame_size), "h264"
    except RuntimeError:
        import cv2

        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            frame_size,
        )
        return writer, "mp4v"
