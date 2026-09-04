#!/usr/bin/env python3
"""Strict product entrypoint around the proven v2/v3 research functions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


RESEARCH_ROOT = Path(__file__).resolve().parent
if str(RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(RESEARCH_ROOT))

from src.utils.files import link_or_copy_file


STAGE_MESSAGES = {
    "registering": "注册匿名参与者",
    "perception": "人体感知与匿名跟踪",
    "ball_tracking": "篮球与篮筐跟踪",
    "synchronizing": "多机位时间同步",
    "action_recognition": "动作识别",
    "outcome_detection": "投篮命中判定",
    "exporting": "导出分析结果",
    "visualizing": "生成复核视频",
}


def emit(stage: str) -> None:
    print(
        "PRODUCT_EVENT " + json.dumps(
            {"stage": stage, "message": STAGE_MESSAGES[stage]}, ensure_ascii=False
        ),
        flush=True,
    )


def configure_runtime(task_root: Path, model_root: Path) -> None:
    os.environ["BASKETBALL_DATA_ROOT"] = str((task_root / "data").resolve())
    os.environ["BASKETBALL_MODEL_ROOT"] = str(model_root.resolve())
    os.environ["BASKETBALL_INSIGHTFACE_ROOT"] = str((model_root / "insightface").resolve())
    os.environ["BASKETBALL_STRICT_RUNTIME"] = "1"
    os.environ.setdefault("YOLO_CONFIG_DIR", str((task_root / "data" / "yolo-config").resolve()))


def deep_runtime_check(model_root: Path) -> dict:
    """Load every active backend and execute YOLOX + RTMW on an empty frame."""
    import numpy as np
    import onnxruntime as ort
    import torch

    required = {
        "yolox": model_root / "detection" / "yolox_m" / "end2end.onnx",
        "rtmw": model_root / "pose" / "rtmw_l" / "end2end.onnx",
        "yolo_pose": model_root / "detection" / "yolo_pose" / "yolo11m-pose.pt",
        "osnet": model_root / "reid" / "osnet_x1_0_msmt17.pth",
        "basketball": model_root / "detection" / "yolo_ball" / "Basketball_v1.pt",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    buffalo = model_root / "insightface" / "models" / "buffalo_l"
    buffalo_files = {
        "det_10g.onnx",
        "w600k_r50.onnx",
        "2d106det.onnx",
        "genderage.onnx",
        "1k3d68.onnx",
    }
    if not buffalo.is_dir() or not buffalo_files.issubset({path.name for path in buffalo.glob("*.onnx")}):
        missing.append("buffalo_l")
    if missing:
        raise RuntimeError("Missing runtime models: " + ", ".join(missing))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("CUDAExecutionProvider is unavailable")

    from src.identity.embedders import create_body_embedder, create_face_embedder
    from src.perception.rtmlib_backend import RTMLibPerception
    from src.perception.yolo_pose_detector import YoloPosePersonDetector
    from src.shot.yolo_detector import YoloBallHoopDetector

    empty = np.zeros((640, 640, 3), dtype=np.uint8)
    perception = RTMLibPerception(
        det_model=str(required["yolox"]),
        pose_model=str(required["rtmw"]),
        device="cuda",
        backend="onnxruntime",
    )
    perception.detect_persons(empty)
    perception.estimate_pose133(empty, [100.0, 50.0, 400.0, 600.0])
    YoloPosePersonDetector(model_file=required["yolo_pose"], device="0").detect_persons(empty)
    YoloBallHoopDetector(model_file=required["basketball"], device="0").detect(empty)
    face = create_face_embedder()
    body = create_body_embedder()
    if face.__class__.__name__.startswith("Stub") or body.__class__.__name__.startswith("Stub"):
        raise RuntimeError("Strict runtime unexpectedly loaded a stub embedder")
    return {
        "ready": True,
        "cuda_device": torch.cuda.get_device_name(0),
        "onnx_providers": ort.get_available_providers(),
        "empty_frame_probe": ["yolox", "rtmw", "yolo_pose", "basketball"],
    }


def _install_original_review_videos(group_root: Path, viz_target: Path) -> None:
    """Copy remuxed source cameras into viz so product review is not the annotated mosaic tiles."""
    summary_path = group_root / "summary.json"
    if not summary_path.is_file():
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    session_id = summary.get("session_id")
    if not session_id:
        return
    from src.config import data_path

    raw_dir = data_path("sessions", str(session_id), "raw")
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        dest = viz_target / f"{camera}_original.mp4"
        if dest.is_file() and dest.stat().st_size > 1000:
            continue
        source = raw_dir / f"{camera}.mp4"
        if source.exists():
            link_or_copy_file(source.resolve(), dest)


def _copy_product_outputs(group_root: Path, output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    for name in ("report.json", "summary.json", "motion.json"):
        source = group_root / name
        if not source.is_file():
            raise RuntimeError(f"Research engine did not produce {source}")
        shutil.copy2(source, output_root / name)
    viz_source = group_root / "viz"
    viz_target = output_root / "viz"
    viz_target.mkdir(parents=True, exist_ok=True)
    phases_source = viz_source / "phases.mp4"
    if phases_source.is_file():
        shutil.copy2(phases_source, viz_target / phases_source.name)
    _install_original_review_videos(group_root, viz_target)
    expected = {
        "cam_01": "cam_01_original.mp4",
        "cam_02": "cam_02_original.mp4",
        "cam_03": "cam_03_original.mp4",
        "cam_04": "cam_04_original.mp4",
        "phases": "phases.mp4",
    }
    media = {kind: name for kind, name in expected.items() if (viz_target / name).is_file()}
    missing_media = sorted(set(expected) - set(media))
    if missing_media:
        raise RuntimeError("Research engine did not produce review media: " + ", ".join(missing_media))
    (output_root / "media_manifest.json").write_text(
        json.dumps(media, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_product_task(task_root: Path, manifest_path: Path, mode: str, model_root: Path) -> None:
    configure_runtime(task_root, model_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04", "sync")
    missing = [name for name in required if not Path(manifest.get(name, "")).is_file()]
    if missing:
        raise RuntimeError("Missing task inputs: " + ", ".join(missing))

    from scripts.run_v2_testset import process_action_group, run_enroll_group

    engine_output = task_root / "engine-output"
    if engine_output.exists():
        shutil.rmtree(engine_output)
    engine_output.mkdir(parents=True, exist_ok=True)
    emit("registering")
    enrollment = run_enroll_group(
        0,
        {"cam_02": Path(manifest["enrollment_video"])},
        engine_output,
        expected_persons=None,
        enroll_mode="sequential",
    )
    student_ids = list(enrollment.get("student_ids") or [])
    if not 1 <= len(student_ids) <= 6:
        raise RuntimeError(f"Registration requires 1–6 people; detected {len(student_ids)}")

    sync_data = task_root / "data" / "product-input"
    (sync_data / "sync").mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest["sync"], sync_data / "sync" / "group_01.json")
    videos = {camera: Path(manifest[camera]) for camera in ("cam_01", "cam_02", "cam_03", "cam_04")}
    process_action_group(
        1,
        videos,
        engine_output,
        data_dir=sync_data,
        stride=2,
        skip_viz=False,
        fast=mode == "quick",
        shot_ball_only=False,
        gallery_session_id=enrollment["session_id"],
        student_ids=student_ids,
        progress_callback=emit,
    )
    _copy_product_outputs(engine_output / "group_01", task_root / "output")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--mode", choices=["quick", "full"], default="full")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--check-readiness", action="store_true")
    args = parser.parse_args()

    probe_root = args.task_root or Path("/tmp/basketball-readiness")
    configure_runtime(probe_root, args.model_root)
    if args.check_readiness:
        print(json.dumps(deep_runtime_check(args.model_root), ensure_ascii=False))
        return
    if args.task_root is None or args.manifest is None:
        parser.error("--task-root and --manifest are required for a task")
    run_product_task(args.task_root.resolve(), args.manifest.resolve(), args.mode, args.model_root.resolve())


if __name__ == "__main__":
    main()
