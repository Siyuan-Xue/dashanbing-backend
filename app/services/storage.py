import json
import shutil
import threading
from pathlib import Path
from typing import BinaryIO

from app.config import AppSettings


UPLOAD_NAMES = {
    "enrollment_video": "enrollment.mkv",
    "cam_01": "cam_01.mkv",
    "cam_02": "cam_02.mkv",
    "cam_03": "cam_03.mkv",
    "cam_04": "cam_04.mkv",
}

UPLOAD_TITLES = {
    "enrollment_video": "注册视频",
    "cam_01": "cam01 视频",
    "cam_02": "cam02 视频",
    "cam_03": "cam03 视频",
    "cam_04": "cam04 视频",
}


class InvalidVideoUpload(ValueError):
    """Raised when an uploaded file is not a recognizable video container."""


def looks_like_video_header(header: bytes) -> bool:
    if len(header) < 4:
        return False
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return True
    if header.startswith(b"FLV"):
        return True
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return True
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return True
    if header.startswith(b"\x00\x00\x01\xba") or header.startswith(b"\x00\x00\x01\xb3"):
        return True
    return False


class AnalysisStorage:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.root = settings.runtime_root.resolve() / "analyses"
        self._upload_lock = threading.Lock()

    def analysis_root(self, analysis_id: str) -> Path:
        candidate = (self.root / analysis_id).resolve()
        if candidate.parent != self.root or candidate.name != analysis_id:
            raise ValueError("Invalid analysis id")
        return candidate

    def prepare(self, analysis_id: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        root = self.analysis_root(analysis_id)
        for name in ("input", "data", "output", "logs"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def save_uploads(self, analysis_id: str, uploads: dict[str, BinaryIO]) -> dict[str, str]:
        with self._upload_lock:
            root = self.prepare(analysis_id)
            manifest: dict[str, str] = {}
            total_bytes = 0
            max_bytes = int(self.settings.max_upload_size_gb * 1024**3)
            reserve_bytes = int(self.settings.min_free_storage_gb * 1024**3)
            for field, filename in UPLOAD_NAMES.items():
                destination = root / "input" / filename
                header = b""
                with destination.open("wb") as target:
                    while chunk := uploads[field].read(1024 * 1024):
                        if not header:
                            header = chunk[:16]
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise ValueError("上传文件总大小超过本地配置上限")
                        if shutil.disk_usage(self.root).free - len(chunk) < reserve_bytes:
                            raise ValueError("本地存储空间不足，上传已停止")
                        target.write(chunk)
                if not looks_like_video_header(header):
                    title = UPLOAD_TITLES[field]
                    raise InvalidVideoUpload(
                        f"{title} 不是可识别的视频文件。请上传 mkv/mp4/mov/webm，不要改扩展名后上传 PDF 或其他文档。"
                    )
                manifest[field] = str(destination)
            sync_destination = root / "input" / "sync.json"
            shutil.copy2(self.settings.sync_config, sync_destination)
            manifest["sync"] = str(sync_destination)
            self.write_manifest(root, manifest)
            return manifest

    def prepare_preset(self, analysis_id: str, manifest: dict[str, str]) -> None:
        root = self.prepare(analysis_id)
        self.write_manifest(root, manifest)

    @staticmethod
    def write_manifest(root: Path, manifest: dict[str, str]) -> None:
        (root / "input_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def delete(self, analysis_id: str) -> None:
        root = self.analysis_root(analysis_id)
        if root.exists():
            shutil.rmtree(root)
