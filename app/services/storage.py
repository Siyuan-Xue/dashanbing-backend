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
                with destination.open("wb") as target:
                    while chunk := uploads[field].read(1024 * 1024):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise ValueError("上传文件总大小超过本地配置上限")
                        if shutil.disk_usage(self.root).free - len(chunk) < reserve_bytes:
                            raise ValueError("本地存储空间不足，上传已停止")
                        target.write(chunk)
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
