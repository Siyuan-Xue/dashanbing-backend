from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path


ORIGINAL_CAMERA_FILES = {
    "cam_01": "cam_01_original.mp4",
    "cam_02": "cam_02_original.mp4",
    "cam_03": "cam_03_original.mp4",
    "cam_04": "cam_04_original.mp4",
}

PHASES_FILE = "phases.mp4"

MEDIA_FILES = {
    **ORIGINAL_CAMERA_FILES,
    "phases": PHASES_FILE,
}

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def remux_to_browser_mp4(src: Path, dst: Path) -> Path:
    """Make a browser-playable MP4. Copy-stream when possible; copy as-is without ffmpeg."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(dst):
        if dst.is_file() and dst.stat().st_size > 0:
            return dst
        if not src.is_file():
            raise FileNotFoundError(src)
        if src.resolve() == dst.resolve():
            return dst
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
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
                    str(dst),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if copied.returncode == 0 and dst.is_file() and dst.stat().st_size > 1000:
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
                    str(dst),
                ],
                capture_output=True,
                text=True,
            )
            if encoded.returncode == 0 and dst.is_file() and dst.stat().st_size > 1000:
                return dst
            if dst.is_file():
                dst.unlink()
            detail = (encoded.stderr or encoded.stdout or "ffmpeg failed").strip().splitlines()
            tail = " ".join(detail[-6:]) if detail else "ffmpeg failed"
            raise RuntimeError(f"无法将 {src.name} 转为可播放的 MP4。{tail}")
        shutil.copy2(src, dst)
        return dst


def install_original_camera_videos(viz_dir: Path, sources: dict[str, Path]) -> None:
    viz_dir.mkdir(parents=True, exist_ok=True)
    for kind, filename in ORIGINAL_CAMERA_FILES.items():
        dest = viz_dir / filename
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        source = sources.get(kind)
        if source is None or not Path(source).is_file():
            continue
        remux_to_browser_mp4(Path(source), dest)


def resolve_review_media(
    viz_dir: Path,
    original_sources: dict[str, Path] | None = None,
) -> dict[str, Path]:
    """Map product media kinds to files.

    The four-camera mosaic stays on phases.mp4. Individual cameras prefer a
    remuxed original in viz/, then the source video — never the annotated
    overlays that were composed into the mosaic.
    """
    media: dict[str, Path] = {}
    phases = viz_dir / PHASES_FILE
    if phases.is_file():
        media["phases"] = phases
    sources = original_sources or {}
    for kind, filename in ORIGINAL_CAMERA_FILES.items():
        remuxed = viz_dir / filename
        if remuxed.is_file():
            media[kind] = remuxed
            continue
        source = sources.get(kind)
        if source is not None and Path(source).is_file():
            media[kind] = Path(source)
    return media
