"""Triangulate action-clip skeletons from multi-view video + court calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

# H36M indices
PELVIS, R_ANKLE, L_ANKLE = 0, 3, 6
R_HIP, L_HIP = 1, 4
R_KNEE, L_KNEE = 2, 5


def _bone_len(xyz: np.ndarray, a: int, b: int) -> float:
    if np.any(~np.isfinite(xyz[a])) or np.any(~np.isfinite(xyz[b])):
        return float("nan")
    return float(np.linalg.norm(xyz[a] - xyz[b]))


def skeleton_plausible(xyz: np.ndarray, conf: np.ndarray, conf_thr: float = 0.2) -> tuple[bool, str]:
    """Reject grossly wrong triangulations."""
    valid = np.isfinite(xyz[:, 0]) & (conf >= conf_thr)
    if int(valid.sum()) < 8:
        return False, "too_few_joints"
    if not (valid[PELVIS] and (valid[R_ANKLE] or valid[L_ANKLE])):
        return False, "missing_pelvis_or_feet"
    # Court bounds (meters) — loose
    # Full-court friendly (drives / breakthrough may leave FT/paint zone)
    if abs(float(xyz[PELVIS, 0])) > 12.0 or float(xyz[PELVIS, 1]) < -6.0 or float(xyz[PELVIS, 1]) > 30.0:
        return False, "pelvis_out_of_court"
    if float(xyz[PELVIS, 2]) < 0.2 or float(xyz[PELVIS, 2]) > 2.5:
        return False, "pelvis_height_bad"
    for a, b, lo, hi in (
        (R_HIP, R_KNEE, 0.25, 0.75),
        (R_KNEE, R_ANKLE, 0.25, 0.75),
        (L_HIP, L_KNEE, 0.25, 0.75),
        (L_KNEE, L_ANKLE, 0.25, 0.75),
    ):
        if valid[a] and valid[b]:
            L = _bone_len(xyz, a, b)
            if not (lo <= L <= hi):
                return False, f"bone_{a}_{b}={L:.2f}"
    # Foot height relative to pelvis (should be below)
    feet = []
    if valid[R_ANKLE]:
        feet.append(float(xyz[R_ANKLE, 2]))
    if valid[L_ANKLE]:
        feet.append(float(xyz[L_ANKLE, 2]))
    if feet and float(xyz[PELVIS, 2]) < max(feet) - 0.05:
        return False, "pelvis_below_feet"
    return True, "ok"


def mean_reproj_error_px(
    xyz: np.ndarray,
    conf: np.ndarray,
    kpts_by_cam: dict[str, np.ndarray],
    cameras: dict[str, dict[str, Any]],
    conf_thr: float = 0.25,
) -> float:
    """Average |proj - observed| over joints/views with valid 3D."""
    errs: list[float] = []
    for j in range(17):
        if not np.isfinite(xyz[j, 0]) or conf[j] < conf_thr:
            continue
        X = xyz[j].reshape(3, 1)
        for cid, k in kpts_by_cam.items():
            if cid not in cameras or k is None or len(k) <= j:
                continue
            c = float(k[j, 2]) if k.shape[1] > 2 else 1.0
            if c < conf_thr:
                continue
            cam = cameras[cid]
            K = cam["K"].copy()
            # projectPoints prefers |fy|; chirality uses signed fy in solve export
            K_use = K.copy()
            R, t = cam["R"], cam["t"]
            D = cam["D"]
            rvec, _ = cv2.Rodrigues(R)
            imgpts, _ = cv2.projectPoints(X.reshape(1, 1, 3), rvec, t.reshape(3, 1), K_use, D)
            u, v = float(imgpts[0, 0, 0]), float(imgpts[0, 0, 1])
            errs.append(float(np.hypot(u - float(k[j, 0]), v - float(k[j, 1]))))
    return float(np.mean(errs)) if errs else 1e9


def ground_by_feet(
    seq: np.ndarray,
    *,
    percentile: float = 20.0,
) -> tuple[np.ndarray, float]:
    """
    Subtract a floor height estimated from ankle Z percentile (standing/contact frames).
    Returns (grounded_seq, floor_z_world_before).
    """
    out = seq.copy()
    foot_z = []
    for fr in out:
        zs = []
        if np.isfinite(fr[R_ANKLE, 2]):
            zs.append(fr[R_ANKLE, 2])
        if np.isfinite(fr[L_ANKLE, 2]):
            zs.append(fr[L_ANKLE, 2])
        if zs:
            foot_z.append(float(np.mean(zs)))
    if not foot_z:
        return out, 0.0
    floor_z = float(np.nanpercentile(np.asarray(foot_z), percentile))
    out[:, :, 2] -= floor_z
    return out, floor_z


def process_group_action_skeletons(
    group_dir: Path,
    *,
    session_id: str | None = None,
    videos: dict[str, Path] | None = None,
    source_videos: dict[str, Path] | None = None,
    pose_paths: dict[str, Path] | None = None,
    sync_path: Path | None = None,
    calib_dir: Path | None = None,
    videos_dir: Path | None = None,
    group_id: int | None = None,
    stride: int = 2,
    pad_ms: float = 400.0,
) -> dict[str, Any]:
    """Export task-bound pose evidence, then expose the same raw 3D to viewers.

    Legacy videos_dir/stride/pad_ms remain accepted for old command invocations,
    but never select a dataset, trigger new inference, or expand sampling.
    Missing explicit task context produces an unavailable analyst artifact.
    """
    from src.pose.analyst_pose import export_analyst_pose

    scene = export_analyst_pose(
        group_dir, session_id=session_id, videos=videos, source_videos=source_videos,
        pose_paths=pose_paths, sync_path=sync_path, calib_dir=calib_dir, group_id=group_id,
    )
    if scene["frames"]:
        from src.viz.pose3d_scene import H36M_EDGES, H36M_NAMES, _court_mesh

        scene.update(
            joint_names=H36M_NAMES, edges=H36M_EDGES, court=_court_mesh(),
            coordinate_system={"space": "court_world", "unit": "meter",
                               "axes": "x_right, y_toward_center_line, z_up"},
            mode_note="Calibrated multiview; original tracked poses; no smoothing or grounding",
        )
    return scene
