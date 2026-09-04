import json
import math
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

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


class UploadTooLarge(ValueError):
    """Raised when streamed uploads exceed the configured aggregate limit."""


class InsufficientStorage(RuntimeError):
    """Raised when accepting another upload would consume the storage reserve."""


class VideoProbeUnavailable(RuntimeError):
    """Raised when the server cannot perform authoritative media validation."""


@dataclass(frozen=True)
class InstalledUpload:
    destination: Path
    byte_size: int
    backup: Path | None
    marker: Path
    operation_id: str


def looks_like_video_header(header: bytes) -> bool:
    if len(header) < 4:
        return False
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return True
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return True
    return False


def _invalid_video_message(title: str) -> str:
    return (
        f"{title} 不是可读取的 MKV/MP4/MOV/WebM 视频。"
        "请上传真实视频，不要仅修改 PDF 或其他文件的扩展名。"
    )


def probe_video_file(path: Path, title: str) -> None:
    """Verify a supported container has a usable, finite-duration video stream."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise VideoProbeUnavailable("服务端缺少 ffprobe，暂时无法安全校验上传视频。")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type,width,height:format=format_name,duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as error:
        raise VideoProbeUnavailable(
            "服务端无法运行 ffprobe，暂时无法安全校验上传视频。"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise InvalidVideoUpload(_invalid_video_message(title)) from error

    try:
        payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
        stream = payload["streams"][0]
        format_info = payload["format"]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(format_info["duration"])
        format_names = set(str(format_info["format_name"]).split(","))
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise InvalidVideoUpload(_invalid_video_message(title)) from None

    supported_formats = {"matroska", "webm", "mov", "mp4"}
    if (
        stream.get("codec_type") != "video"
        or width <= 0
        or height <= 0
        or not math.isfinite(duration)
        or duration <= 0
        or format_names.isdisjoint(supported_formats)
    ):
        raise InvalidVideoUpload(_invalid_video_message(title))


class AnalysisStorage:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.root = settings.runtime_root.resolve() / "analyses"
        self._upload_lock = threading.Lock()
        self.video_probe = probe_video_file

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
                    first_chunk = True
                    while chunk := uploads[field].read(1024 * 1024):
                        if first_chunk:
                            first_chunk = False
                            if not looks_like_video_header(chunk[:16]):
                                raise InvalidVideoUpload(_invalid_video_message(UPLOAD_TITLES[field]))
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise UploadTooLarge("上传文件总大小超过本地配置上限")
                        if shutil.disk_usage(self.root).free - len(chunk) < reserve_bytes:
                            raise InsufficientStorage("本地存储空间不足，上传已停止")
                        target.write(chunk)
                if first_chunk:
                    raise InvalidVideoUpload(_invalid_video_message(UPLOAD_TITLES[field]))
                self.video_probe(destination, UPLOAD_TITLES[field])
                manifest[field] = str(destination)
            sync_destination = root / "input" / "sync.json"
            shutil.copy2(self.settings.sync_config, sync_destination)
            manifest["sync"] = str(sync_destination)
            self.write_manifest(root, manifest)
            return manifest

    def replace_task_input(
        self,
        analysis_id: str,
        slot: str,
        upload: BinaryIO,
        *,
        existing_bytes: int,
    ) -> InstalledUpload:
        if slot not in UPLOAD_NAMES:
            raise ValueError("Invalid input slot")
        with self._upload_lock:
            root = self.prepare(analysis_id)
            destination = root / "input" / UPLOAD_NAMES[slot]
            operation_id = uuid4().hex
            temporary = root / "input" / f".{slot}-{operation_id}.tmp"
            backup = root / "input" / f".{slot}-{operation_id}.bak"
            marker = root / "input" / f".{slot}-{operation_id}.pending"
            total_bytes = existing_bytes
            byte_size = 0
            max_bytes = int(self.settings.max_upload_size_gb * 1024**3)
            reserve_bytes = int(self.settings.min_free_storage_gb * 1024**3)
            try:
                with temporary.open("wb") as target:
                    first_chunk = True
                    while chunk := upload.read(1024 * 1024):
                        if first_chunk:
                            first_chunk = False
                            if not looks_like_video_header(chunk[:16]):
                                raise InvalidVideoUpload(_invalid_video_message(UPLOAD_TITLES[slot]))
                        total_bytes += len(chunk)
                        byte_size += len(chunk)
                        if total_bytes > max_bytes:
                            raise UploadTooLarge("上传文件总大小超过本地配置上限")
                        if shutil.disk_usage(self.root).free - len(chunk) < reserve_bytes:
                            raise InsufficientStorage("本地存储空间不足，上传已停止")
                        target.write(chunk)
                if first_chunk:
                    raise InvalidVideoUpload(_invalid_video_message(UPLOAD_TITLES[slot]))
                self.video_probe(temporary, UPLOAD_TITLES[slot])
                marker.write_text(slot, encoding="utf-8")
                installed_backup = None
                if destination.exists():
                    destination.replace(backup)
                    installed_backup = backup
                temporary.replace(destination)
                return InstalledUpload(
                    destination,
                    byte_size,
                    installed_backup,
                    marker,
                    operation_id,
                )
            except Exception:
                temporary.unlink(missing_ok=True)
                if backup.exists():
                    destination.unlink(missing_ok=True)
                    backup.replace(destination)
                marker.unlink(missing_ok=True)
                raise

    @staticmethod
    def mark_task_input_committed(upload: InstalledUpload) -> InstalledUpload:
        committed_marker = upload.marker.with_suffix(".committed")
        upload.marker.replace(committed_marker)
        return InstalledUpload(
            destination=upload.destination,
            byte_size=upload.byte_size,
            backup=upload.backup,
            marker=committed_marker,
            operation_id=upload.operation_id,
        )

    @staticmethod
    def finalize_task_input(upload: InstalledUpload) -> None:
        if upload.backup is not None:
            upload.backup.unlink(missing_ok=True)
        upload.marker.unlink(missing_ok=True)

    @staticmethod
    def rollback_task_input(upload: InstalledUpload) -> None:
        upload.destination.unlink(missing_ok=True)
        if upload.backup is not None and upload.backup.exists():
            upload.backup.replace(upload.destination)
        upload.marker.unlink(missing_ok=True)

    def recover_task_input_uploads(
        self,
        analysis_id: str,
        *,
        status: str,
        valid_slots: set[str],
        committed_operations: dict[str, str] | None = None,
    ) -> None:
        input_root = self.analysis_root(analysis_id) / "input"
        if not input_root.is_dir():
            return
        for slot, filename in UPLOAD_NAMES.items():
            temporary_files = list(input_root.glob(f".{slot}-*.tmp"))
            backup_files = sorted(
                input_root.glob(f".{slot}-*.bak"),
                key=lambda path: path.stat().st_mtime_ns,
            )
            marker_files = list(input_root.glob(f".{slot}-*.pending"))
            marker_files.extend(input_root.glob(f".{slot}-*.committed"))
            latest_marker = max(
                marker_files,
                key=lambda path: path.stat().st_mtime_ns,
                default=None,
            )
            marker_operation_id = None
            if latest_marker is not None:
                marker_operation_id = latest_marker.name.removeprefix(
                    f".{slot}-"
                ).removesuffix(latest_marker.suffix)
            correlated_operation_id = (committed_operations or {}).get(slot)
            if latest_marker is None:
                committed = status not in {"uploading", "canceled"}
            elif latest_marker.suffix == ".committed":
                committed = True
            elif correlated_operation_id is not None:
                committed = marker_operation_id == correlated_operation_id
            elif slot in valid_slots:
                committed = status not in {"uploading", "canceled"}
            else:
                committed = False
            destination = input_root / filename
            if committed:
                for backup in backup_files:
                    backup.unlink(missing_ok=True)
            elif backup_files:
                destination.unlink(missing_ok=True)
                latest = backup_files.pop()
                latest.replace(destination)
                for backup in backup_files:
                    backup.unlink(missing_ok=True)
            elif slot not in valid_slots and (
                status == "uploading" or marker_files or temporary_files
            ):
                destination.unlink(missing_ok=True)
            for artifact in (*temporary_files, *marker_files):
                artifact.unlink(missing_ok=True)

    def prepare_task_submission(self, analysis_id: str, manifest: dict[str, str]) -> dict[str, str]:
        root = self.prepare(analysis_id)
        sync_destination = root / "input" / "sync.json"
        sync_temporary = root / "input" / ".sync.json.tmp"
        shutil.copy2(self.settings.sync_config, sync_temporary)
        sync_temporary.replace(sync_destination)
        completed = dict(manifest)
        completed["sync"] = str(sync_destination)
        self.write_manifest(root, completed)
        return completed

    def prepare_preset(self, analysis_id: str, manifest: dict[str, str]) -> None:
        root = self.prepare(analysis_id)
        self.write_manifest(root, manifest)

    @staticmethod
    def write_manifest(root: Path, manifest: dict[str, str]) -> None:
        (root / "input_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def deletion_target_path(self, analysis_id: str, target: str) -> Path:
        root = self.analysis_root(analysis_id)
        suffixes = {
            "analysis_root": (),
            "enrollment": ("data", "enrollment"),
            "input": ("input",),
            "data": ("data",),
            "engine_output": ("engine-output",),
        }
        if target not in suffixes:
            raise ValueError("Invalid storage deletion target")
        candidate = root
        for component in suffixes[target]:
            candidate /= component
            if candidate.is_symlink():
                raise ValueError("Storage deletion target contains a symbolic link")
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("Storage deletion target escapes analysis root")
        return candidate

    def remove_deletion_target(self, analysis_id: str, target: str) -> None:
        path = self.deletion_target_path(analysis_id, target)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()

    def delete(self, analysis_id: str) -> None:
        self.remove_deletion_target(analysis_id, "analysis_root")
