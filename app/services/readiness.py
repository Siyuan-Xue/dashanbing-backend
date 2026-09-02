import json
import math
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import AppSettings
from app.services.presets import MEDIA_FILES, PRESETS


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    ready: bool
    detail: str


class ReadinessService:
    """Cheap readiness inventory; deep GPU probes are cached by the worker at startup."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._cached_deep_check: dict | None = None
        self._deep_check_lock = threading.Lock()
        self._startup_queue_ready: bool | None = None

    @staticmethod
    def _valid_sync_file(path: Path) -> bool:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            offsets = payload["camera_time_offsets_ms"]
            cameras = {"cam_01", "cam_02", "cam_03", "cam_04"}
            return (
                payload.get("anchor_camera") == "cam_03"
                and cameras.issubset(offsets)
                and all(
                    isinstance(offsets[camera], (int, float))
                    and math.isfinite(float(offsets[camera]))
                    for camera in cameras
                )
                and float(offsets["cam_03"]) == 0.0
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def report(self) -> dict:
        if self.settings.simulation_mode:
            return {
                "ready": True,
                "mode": "simulation",
                "checks": [
                    {"name": "simulation", "ready": True, "detail": "开发模拟引擎已启用；不会执行真实推理。"}
                ],
            }
        required = {
            "yolox": self.settings.model_root / "detection" / "yolox_m" / "end2end.onnx",
            "rtmw": self.settings.model_root / "pose" / "rtmw_l" / "end2end.onnx",
            "yolo_pose": self.settings.model_root / "detection" / "yolo_pose" / "yolo11m-pose.pt",
            "osnet": self.settings.model_root / "reid" / "osnet_x1_0_msmt17.pth",
            "basketball": self.settings.model_root / "detection" / "yolo_ball" / "Basketball_v1.pt",
        }
        checks: list[ReadinessCheck] = []
        for name, path in required.items():
            found = path.is_file()
            checks.append(ReadinessCheck(name, found, f"{path.name} {'已找到' if found else '缺失'}"))
        buffalo = self.settings.model_root / "insightface" / "models" / "buffalo_l"
        buffalo_names = {path.name for path in buffalo.glob("*.onnx")} if buffalo.is_dir() else set()
        expected_buffalo = {
            "det_10g.onnx",
            "w600k_r50.onnx",
            "2d106det.onnx",
            "genderage.onnx",
            "1k3d68.onnx",
        }
        checks.append(
            ReadinessCheck(
                "buffalo_l",
                expected_buffalo.issubset(buffalo_names),
                "5 个本地 ONNX 文件已找到" if expected_buffalo.issubset(buffalo_names) else "buffalo_l 不完整",
            )
        )
        sync_ready = self._valid_sync_file(self.settings.sync_config)
        checks.append(
            ReadinessCheck(
                "sync_config",
                sync_ready,
                "现场同步配置有效" if sync_ready else "现场同步配置缺失或格式无效",
            )
        )
        sample_ready = True
        sample_inputs = self.settings.sample_root / "test_data_v3"
        for preset in PRESETS:
            group = self.settings.sample_root / "outputs" / "v3" / preset.group_id
            required_sample_files = [group / "report.json", group / "summary.json", group / "eval_vs_gt.json"]
            required_sample_files.extend(group / "viz" / filename for filename in MEDIA_FILES.values())
            required_sample_files.extend(
                sample_inputs / f"{preset.group_number}-{camera}.mkv"
                for camera in range(1, 5)
            )
            required_sample_files.append(sample_inputs / "0-2.mkv")
            preset_sync = sample_inputs / "sync" / f"group_{preset.group_number:02d}.json"
            required_sample_files.append(preset_sync)
            sample_ready = sample_ready and all(path.is_file() for path in required_sample_files)
            sample_ready = sample_ready and self._valid_sync_file(preset_sync)
        checks.append(
            ReadinessCheck(
                "sample_bundle",
                sample_ready,
                "四个预置组及复核视频完整" if sample_ready else "预置样例包不完整",
            )
        )
        credentials_ready = (
            self.settings.admin_password != "change-me-local-admin"
            and not self.settings.admin_password.startswith("replace-with")
            and self.settings.jwt_secret_key != "change-this-local-jwt-secret-before-deployment-please"
            and not self.settings.jwt_secret_key.startswith("replace-with")
        )
        checks.append(
            ReadinessCheck(
                "credentials",
                credentials_ready,
                "管理员密码与 JWT 密钥已配置" if credentials_ready else "仍在使用默认本地凭据",
            )
        )
        checks.append(ReadinessCheck("ffmpeg", shutil.which("ffmpeg") is not None, "ffmpeg executable"))
        usage = shutil.disk_usage(self.settings.runtime_root)
        free_gb = usage.free / (1024**3)
        checks.append(
            ReadinessCheck(
                "storage",
                free_gb >= self.settings.min_free_storage_gb,
                f"可用 {free_gb:.1f} GiB",
            )
        )
        try:
            import torch

            cuda_ready = bool(torch.cuda.is_available())
        except Exception:
            cuda_ready = False
        checks.append(ReadinessCheck("cuda", cuda_ready, "CUDA 可用" if cuda_ready else "CUDA 不可用"))
        if all(check.ready for check in checks):
            deep = self._deep_check()
            checks.append(
                ReadinessCheck(
                    "empty_frame_inference",
                    bool(deep.get("ready")),
                    deep.get("detail", "YOLOX + RTMW 空帧推理通过"),
                )
            )
        if self._startup_queue_ready is False:
            checks.append(
                ReadinessCheck(
                    "startup_preflight",
                    False,
                    "启动预检未通过；修正环境后请重启服务",
                )
            )
        return {
            "ready": all(check.ready for check in checks),
            "mode": "gpu",
            "checks": [check.__dict__ for check in checks],
        }

    def _deep_check(self) -> dict:
        with self._deep_check_lock:
            if self._cached_deep_check is not None:
                return self._cached_deep_check
            command = [
                sys.executable,
                "-m",
                "research_engine.product_runner",
                "--check-readiness",
                "--task-root",
                str(self.settings.runtime_root / "readiness"),
                "--model-root",
                str(self.settings.model_root),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=Path(__file__).resolve().parents[2],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )
                log_path = self.settings.runtime_root / "readiness" / "probe.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(completed.stdout, encoding="utf-8")
                if completed.returncode != 0:
                    result = {"ready": False, "detail": "运行时模型加载或空帧推理失败，请查看本地 readiness 日志"}
                else:
                    result = json.loads(completed.stdout.strip().splitlines()[-1])
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                result = {"ready": False, "detail": "运行时空帧探测未完成，请查看本地 readiness 日志"}
            self._cached_deep_check = result
            return result

    def preflight(self) -> dict:
        """Run and cache the strict probe before the GPU queue starts."""
        return self.report()

    def lock_queue_state(self, ready: bool) -> None:
        """Keep the queue stopped until restart after a failed startup probe."""
        self._startup_queue_ready = ready

    def require_ready(self) -> None:
        report = self.report()
        if not report["ready"]:
            missing = ", ".join(
                check["name"] for check in report["checks"] if not check["ready"]
            )
            raise RuntimeError(f"真实分析环境未就绪：{missing}")
