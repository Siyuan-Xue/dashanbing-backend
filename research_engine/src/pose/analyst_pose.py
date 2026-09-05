"""Persist conservative analyst evidence from the current task's existing poses.

No inference, resampling, pseudo-depth, identity repair, or calibration solving.
See research_engine/ANALYST_POSE.md for the persisted contract and quality gates.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from bisect import bisect_left
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from src.action.halpe2h36m import wholebody133_to_h36m
from src.pose.angles import angle_at_joint
from src.pose.triangulate import load_camera_calibration, triangulate_skeleton17


ANGLE_JOINTS = {
    "left_elbow": (11, 12, 13), "right_elbow": (14, 15, 16),
    "left_knee": (4, 5, 6), "right_knee": (1, 2, 3),
}
REQUIRED_JOINTS = sorted({j for triplet in ANGLE_JOINTS.values() for j in triplet})
QUALITY = {"min_views": 2, "keypoint_confidence_min": .5,
           "max_reprojection_error_px": 8., "max_calibration_error_px": 8.,
           "max_time_delta_ms": 40., "min_ray_angle_deg": 2.,
           "identity_confidence": ["high"], "min_track_observations": 2}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unavailable_pose(reason: str, *, session_id: str | None = None) -> dict:
    return {"schema_version": 1, "available": False, "reason": reason, "events": [],
            "camera_offsets_ms": {}, "time_basis": "common", "provenance": {
                "session_id": session_id, "pose_source": "calibrated_multiview_triangulation",
                "verified": False, "calibration_verified": False, "identity_verified": False,
                "offset_convention": "common_ms = local_ms - offset_ms",
                "identity_method": "raw_detection_track_and_high_confidence_student_id",
                "sampling": "existing_anchor_pose_frames_only", "smoothing": "none",
                "quality_thresholds": dict(QUALITY), "videos": {}, "pose_files": {},
                "calibration": {"verified": False}, "sync": {}, "samples": [],
                "reference_ranges": [], "rejected": {}}}


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _declared_source(annotations: dict, cam: str, bundle: Path) -> Path | None:
    """Resolve a declared source, including the existing v3 brace-list notation.

    This does not infer other groups from shared_across_groups or dataset names.
    Only an exact video content match to the declared source is accepted.
    """
    import re

    sources = annotations.get("source_videos")
    source = sources.get(cam) if isinstance(sources, dict) else sources
    if not isinstance(source, str):
        return None
    if "{" in source:
        match = re.search(r"\{([0-9,]+)\}", source)
        number = str(int(cam.removeprefix("cam_")))
        if not match or number not in match[1].split(","):
            return None
        source = source[:match.start()] + number + source[match.end():]
    path = Path(source)
    candidates = [path] if path.is_absolute() else [parent / path for parent in bundle.parents]
    return next((p.resolve() for p in candidates if p.is_file()), None)


def _matching_calibration(calib_dir: Path | None, videos: dict[str, Path], provenance: dict) -> dict:
    if calib_dir is None:
        return {}
    path = Path(calib_dir)
    bundle = path / "cameras.json" if path.is_dir() else path
    if bundle.name != "cameras.json" or not bundle.is_file():
        return {}
    doc = _read(bundle)
    annotations = doc.get("annotations") or {}
    expected_hashes = annotations.get("source_video_sha256") or {}
    solved = (doc.get("solved") or {}).get("cameras") or {}
    cameras = load_camera_calibration(bundle.parent)
    matched = {}
    detail = {"path": str(bundle.resolve()), "sha256": file_sha256(bundle),
              "verified": False, "source_match": "sha256", "cameras": {}}
    provenance["calibration"] = detail
    for cam, camera in cameras.items():
        if cam not in videos:
            continue
        expected = expected_hashes.get(cam)
        declared = _declared_source(annotations, cam, bundle) if expected is None else None
        if declared is not None:
            expected = file_sha256(declared)
        actual = provenance["videos"][cam]["sha256"]
        if not expected or actual != expected:
            detail["cameras"][cam] = {"verified": False, "reason": "source_mismatch"}
            continue
        try:
            K, R, t, D = (camera[k] for k in ("K", "R", "t", "D"))
            intr = solved[cam]["intrinsics"]
            error = float(solved[cam]["reproj_error_px"]["mean"])
            size = [int(intr["width"]), int(intr["height"])]
            valid = (K.shape == R.shape == (3, 3) and t.shape == (3, 1)
                     and all(np.isfinite(x).all() for x in (K, R, t, D))
                     and abs(np.linalg.det(K)) > 1e-6
                     and np.allclose(R @ R.T, np.eye(3), atol=1e-4)
                     and abs(np.linalg.det(R) - 1) < 1e-4 and min(size) > 0
                     and np.isfinite(error) and 0 <= error <= QUALITY["max_calibration_error_px"])
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            detail["cameras"][cam] = {"verified": False, "reason": "invalid_calibration"}
            continue
        matched[cam] = {**camera, "image_size": size}
        detail["cameras"][cam] = {"verified": True, "source_sha256": actual,
                                   "reprojection_error_px": error, "image_size": size}
    detail["verified"] = len(matched) >= 2
    return matched


def find_task_calibration(videos: dict[str, Path]) -> Path | None:
    """Find an existing source-bound bundle beside task source datasets only.

    Product temp group numbers, global reference directories, shared-court
    declarations, and filenames alone never establish a calibration match.
    """
    roots = {Path(v).resolve().parent.parent / "calibration" for v in videos.values()}
    candidates = sorted({p for root in roots for p in root.glob("*/cameras.json")})
    if not candidates:
        return None
    try:
        provenance = {"videos": {cam: {"sha256": file_sha256(path)} for cam, path in videos.items()}}
        matches = []
        for path in candidates:
            try:
                if len(_matching_calibration(path, videos, provenance)) >= 2:
                    matches.append(path.resolve())
            except (OSError, ValueError, TypeError, KeyError, cv2.error):
                continue
        # Multiple valid bundles are ambiguous; never choose by directory order.
        return matches[0] if len(matches) == 1 else None
    except OSError:
        return None


def _timeline(pose_path: Path, video: Path, cam: str, session_id: str, camera: dict) -> dict:
    doc = _read(pose_path)
    if (doc.get("session_id") != session_id or doc.get("camera_id") != cam
            or not doc.get("source_video") or Path(doc["source_video"]).resolve() != video.resolve()
            or doc.get("image_size") != camera["image_size"]):
        return {}
    fps = float(doc.get("fps") or 0)
    if not np.isfinite(fps) or fps <= 0:
        return {}
    # Spatial/majority/solo repair rewrites pose IDs; use original detection IDs.
    det_path = pose_path.with_name("detections.jsonl")
    detections = [json.loads(line) for line in det_path.read_text().splitlines() if line.strip()]
    identities, counts = defaultdict(set), Counter()
    by_frame = defaultdict(list)
    for det in detections:
        tid, sid = det.get("track_id"), det.get("student_id")
        if tid is not None and sid:
            identities[tid].add(sid)
        by_frame[int(det["frame"])].append(det)
    frames = []
    for fr in doc.get("frames") or []:
        fidx = int(fr["frame"])
        ts = float(fr.get("timestamp_ms", fidx / fps * 1000))
        if not np.isfinite(ts) or ts < 0 or abs(ts - fidx / fps * 1000) > .5:
            continue
        dets = by_frame[fidx]
        sid_counts = Counter(d.get("student_id") for d in dets if d.get("student_id"))
        tid_counts = Counter(p.get("track_id") for p in fr.get("persons") or [])
        people = {}
        for pose in fr.get("persons") or []:
            tid = pose.get("track_id")
            matches = [d for d in dets if d.get("track_id") == tid]
            if tid is None or tid_counts[tid] != 1 or len(matches) != 1 or len(identities[tid]) != 1:
                continue
            det = matches[0]
            sid = det.get("student_id")
            if (not sid or sid_counts[sid] != 1 or det.get("identity_confidence") != "high"
                    or pose.get("pose_source") not in {"rtmw", "yolo_pose"}):
                continue
            k = np.asarray(pose.get("keypoints"), dtype=np.float64)
            if k.ndim != 2 or k.shape[0] < 17 or k.shape[1] != 3:
                continue
            k = k.copy()
            k[~np.isfinite(k).all(axis=1), :] = 0
            h36m = wholebody133_to_h36m(k)
            people[sid] = {"keypoints": h36m, "track_id": tid, "frame": fidx, "local_ms": ts}
            counts[tid] += 1
        frames.append({"local_ms": ts, "people": people})
    for fr in frames:
        fr["people"] = {sid: p for sid, p in fr["people"].items()
                        if counts[p["track_id"]] >= QUALITY["min_track_observations"]}
    frames.sort(key=lambda fr: fr["local_ms"])
    return {"fps": fps, "frames": frames, "times": [fr["local_ms"] for fr in frames]}


def _triangulate(observations: dict, cameras: dict) -> tuple | None:
    """All four angles must have the same >=2 complete views; reject bad geometry."""
    used = {cam: obs for cam, obs in observations.items()
            if np.all(obs["keypoints"][REQUIRED_JOINTS, 2] >= QUALITY["keypoint_confidence_min"])}
    if len(used) < 2:
        return None
    kpts = {cam: obs["keypoints"] for cam, obs in used.items()}
    xyz, conf = triangulate_skeleton17(kpts, {c: cameras[c] for c in used},
                                     conf_thr=QUALITY["keypoint_confidence_min"], min_views=2)
    if not np.isfinite(xyz[REQUIRED_JOINTS]).all():
        return None
    errors = []
    centers = {c: (-cameras[c]["R"].T @ cameras[c]["t"]).reshape(3) for c in used}
    for j in REQUIRED_JOINTS:
        rays = []
        for cam in used:
            camera = cameras[cam]
            point = xyz[j]
            if (camera["R"] @ point + camera["t"].reshape(3))[2] <= 0:
                return None
            ray = point - centers[cam]
            rays.append(ray / max(np.linalg.norm(ray), 1e-12))
            projected, _ = cv2.projectPoints(point.reshape(1, 3), cv2.Rodrigues(camera["R"])[0],
                                             camera["t"], camera["K"], camera["D"])
            error = float(np.linalg.norm(projected.reshape(2) - kpts[cam][j, :2]))
            if not np.isfinite(error) or error > QUALITY["max_reprojection_error_px"]:
                return None
            errors.append(error)
        ray_angles = [np.degrees(np.arccos(np.clip(abs(np.dot(a, b)), 0, 1)))
                      for i, a in enumerate(rays) for b in rays[i + 1:]]
        if max(ray_angles) < QUALITY["min_ray_angle_deg"]:
            return None
    # Broad adult/child body constraints, before any smoothing or grounding.
    for a, b, lo, hi in ((1, 2, .15, .8), (2, 3, .15, .8), (4, 5, .15, .8), (5, 6, .15, .8),
                         (11, 12, .1, .6), (12, 13, .1, .6), (14, 15, .1, .6), (15, 16, .1, .6)):
        if not lo <= np.linalg.norm(xyz[a] - xyz[b]) <= hi:
            return None
    angles = {name: angle_at_joint(*(xyz[j] for j in joints)) for name, joints in ANGLE_JOINTS.items()}
    if not all(np.isfinite(v) for v in angles.values()):
        return None
    return angles, float(np.mean(errors)), xyz, conf, used


def _references(clip: dict) -> list[dict]:
    """Reference ranges are metadata, never a measured score or default pose."""
    from src.config import load_yaml

    action = clip.get("action_type")
    if action not in {"free_throw", "jump_shot", "layup", "triple_threat"}:
        return []
    path = f"actions/{action}.yaml"
    refs = []
    for phase in load_yaml(path).get("phases") or []:
        for metric in (phase.get("metrics") or {}).values():
            joint = metric.get("joint")
            if joint == "shooting_elbow" and clip.get("shooting_hand") in {"left", "right"}:
                joint = f"{clip['shooting_hand']}_elbow"
            if joint in ANGLE_JOINTS and metric.get("unit") == "deg":
                refs.append({"clip_id": clip["clip_id"], "action_type": action, "phase": phase["name"],
                             "joint": joint, "min": metric["min"], "max": metric["max"],
                             "unit": "deg", "source": f"configs/{path}"})
    return refs


def export_analyst_pose(group_dir: Path, *, session_id: str | None = None,
                        videos: dict[str, Path] | None = None, source_videos: dict[str, Path] | None = None,
                        pose_paths: dict[str, Path] | None = None, sync_path: Path | None = None,
                        calib_dir: Path | None = None, group_id: int | None = None) -> dict:
    """Always persist a v1 artifact; quality failure cannot break original results."""
    artifact = unavailable_pose("missing_task_context", session_id=session_id)
    frames = []
    try:
        if session_id and videos and pose_paths and sync_path:
            frames = _build(artifact, Path(group_dir), session_id, videos, source_videos or videos,
                            pose_paths, Path(sync_path), calib_dir)
    except (OSError, ValueError, TypeError, KeyError, cv2.error, np.linalg.LinAlgError) as exc:
        artifact.update(available=False, reason="invalid_pose_evidence", events=[])
        artifact["provenance"].update(error_type=type(exc).__name__, samples=[], reference_ranges=[],
                                      verified=False, identity_verified=False)
        frames = []
    Path(group_dir).mkdir(parents=True, exist_ok=True)
    path = Path(group_dir) / "analyst_pose.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
    return {"group_id": group_id, "session_id": session_id, "status": "ok" if artifact["available"] else "unavailable",
            "reason": artifact["reason"], "mode": "triangulated" if artifact["available"] else "unavailable",
            "time_basis": "common", "offsets_ms": artifact["camera_offsets_ms"],
            "frames": frames, "n_frames": len(frames), "provenance": artifact["provenance"]}


def _build(artifact, group_dir, session_id, videos, source_videos, pose_paths, sync_path, calib_dir):
    provenance = artifact["provenance"]
    motion = _read(group_dir / "motion.json")
    if motion.get("session_id") != session_id:
        artifact["reason"] = "session_mismatch"
        return []
    sync = _read(sync_path)
    offsets = {cam: float(value) for cam, value in (sync.get("camera_time_offsets_ms") or {}).items()
               if cam in videos and np.isfinite(float(value))}
    artifact["camera_offsets_ms"] = offsets
    provenance["sync"] = {"path": str(sync_path.resolve()), "sha256": file_sha256(sync_path),
                          "source": sync.get("source") or sync.get("offset_source") or "task_sync"}
    for cam, path in source_videos.items():
        provenance["videos"][cam] = {"path": str(Path(path).resolve()), "sha256": file_sha256(path)}
    cameras = _matching_calibration(calib_dir, source_videos, provenance)
    provenance["calibration_verified"] = len(cameras) >= 2
    if len(cameras) < 2:
        artifact["reason"] = "calibration_unverified"
        return []
    timelines = {}
    for cam in cameras.keys() & pose_paths.keys() & videos.keys() & offsets.keys():
        if not Path(videos[cam]).is_file():
            continue
        path = Path(pose_paths[cam])
        try:
            timeline = _timeline(path, Path(videos[cam]), cam, session_id, cameras[cam])
        except (OSError, ValueError, TypeError, KeyError):
            timeline = {}
        if timeline:
            timelines[cam] = timeline
            provenance["pose_files"][cam] = {"path": str(path.resolve()), "sha256": file_sha256(path),
                "video_path": str(Path(videos[cam]).resolve()), "fps": timeline["fps"],
                "detections_sha256": file_sha256(path.with_name("detections.jsonl"))}
    if len(timelines) < 2:
        artifact["reason"] = "insufficient_matching_pose_views"
        return []
    rejected, frames = Counter(), []
    for clip in motion.get("clips") or []:
        anchor = clip.get("anchor_camera") or (motion.get("metadata") or {}).get("anchor_camera")
        sid, clip_id = clip.get("student_id"), clip.get("clip_id")
        if not sid or not clip_id or anchor not in timelines:
            rejected["missing_clip_identity_or_anchor"] += 1
            continue
        start, end = float(clip["start_ms"]), float(clip["end_ms"])
        if not np.isfinite([start, end]).all() or start > end:
            rejected["invalid_clip_time"] += 1
            continue
        # Action windows and phases use the action camera's local clock.
        anchor_frames = [f for f in timelines[anchor]["frames"] if start <= f["local_ms"] <= end]
        track_sets = defaultdict(set)
        candidates = []
        for anchor_frame in anchor_frames:
            common = anchor_frame["local_ms"] - offsets[anchor]
            if common < 0:
                continue
            observations = {}
            for cam, timeline in timelines.items():
                target = common + offsets[cam]
                index = bisect_left(timeline["times"], target)
                nearby = timeline["frames"][max(0, index - 1):index + 1]
                nearest = min(nearby, key=lambda f: abs(f["local_ms"] - target), default=None)
                if nearest is None or abs(nearest["local_ms"] - offsets[cam] - common) > QUALITY["max_time_delta_ms"]:
                    continue
                person = nearest["people"].get(sid)
                if person:
                    observations[cam] = person
                    track_sets[cam].add(person["track_id"])
            candidates.append((common, observations))
        before = len(frames)
        for common, observations in candidates:
            observations = {c: p for c, p in observations.items() if len(track_sets[c]) == 1}
            if anchor not in observations or len(observations) < 2:
                rejected["insufficient_identity_or_sync"] += 1
                continue
            observed_times = [p["local_ms"] - offsets[c] for c, p in observations.items()]
            if max(observed_times) - min(observed_times) > QUALITY["max_time_delta_ms"]:
                rejected["camera_time_gap"] += 1
                continue
            result = _triangulate(observations, cameras)
            if result is None:
                rejected["unreliable_geometry"] += 1
                continue
            angles, error, xyz, conf, used = result
            event = {"clip_id": clip_id, "student_id": sid, "time_ms": round(common, 3),
                     "angles": angles, "camera_count": len(used), "reprojection_error_px": error}
            artifact["events"].append(event)
            provenance["samples"].append({"clip_id": clip_id, "student_id": sid, "time_ms": event["time_ms"],
                "anchor_camera": anchor, "track_ids": {c: p["track_id"] for c, p in used.items()},
                "frames": {c: p["frame"] for c, p in used.items()},
                "local_times_ms": {c: p["local_ms"] for c, p in used.items()}})
            frames.append({"clip_id": clip_id, "student_id": sid, "action_type": clip.get("action_type"),
                "t_ms": event["time_ms"], "joints": [[float(x) if np.isfinite(x) else None for x in j] for j in xyz],
                "conf": conf.tolist(), "n_views": len(used), "reproj_px": error, "views": sorted(used)})
        if len(frames) > before:
            provenance["reference_ranges"].extend(_references(clip))
    provenance["rejected"] = dict(rejected)
    provenance.update(verified=bool(frames), identity_verified=bool(frames))
    artifact.update(available=bool(frames), reason="ok" if frames else "no_reliable_pose_events")
    return frames
