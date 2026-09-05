"""Build anonymized, evidence-linked facts from final research artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import OrderedDict
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from app.analyst_schemas import AnalystEvidence, AnalystFacts, AnalystMetrics, AnalystSubject
from app.services.results import ProductActionCounts, ProductShotSummary, SUPPORTED_ACTIONS


CAMERAS = ("cam_01", "cam_02", "cam_03", "cam_04")
ANGLES = ("left_elbow", "right_elbow", "left_knee", "right_knee")
_CACHE_LOCK = RLock()
_DIGEST_CACHE: OrderedDict[tuple, str] = OrderedDict()
_PRESET_CACHE: OrderedDict[str, dict] = OrderedDict()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _rows(value: object) -> list[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _identity(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _key(row: dict) -> tuple[str, str] | None:
    clip, student = _identity(row.get("clip_id")), _identity(row.get("student_id"))
    return (clip, student) if clip and student else None


def _pose_verified(pose: dict) -> bool:
    provenance = pose.get("provenance")
    return (
        pose.get("schema_version") == 1 and pose.get("available") is True
        and pose.get("time_basis") == "common" and isinstance(provenance, dict)
        and all(provenance.get(key) is True for key in ("verified", "calibration_verified", "identity_verified"))
    )


def _event_angles(pose: dict, clip: dict, start: float, end: float, time: float) -> dict[str, float]:
    if not _pose_verified(pose) or _key(clip) is None:
        return {}
    candidates = []
    for row in _rows(pose.get("events")):
        when = _number(row.get("time_ms"))
        cameras = _number(row.get("camera_count"))
        error = _number(row.get("reprojection_error_px"))
        if (_key(row) != _key(clip) or when is None or not start <= when <= end
                or cameras is None or cameras < 2 or error is None or not 0 <= error <= 8):
            continue
        angles = row.get("angles")
        if not isinstance(angles, dict):
            continue
        valid = {key: float(angles[key]) for key in ANGLES
                 if _number(angles.get(key)) is not None and 0 <= angles[key] <= 180}
        if valid:
            candidates.append((abs(when - time), valid))
    return min(candidates, key=lambda item: item[0])[1] if candidates else {}


def build_analyst_facts(
    report: dict, summary: dict, pose: dict | None = None,
    camera_offsets_ms: dict | None = None,
) -> AnalystFacts:
    """Keep aggregate shot statistics separate from exact clip/person evidence.

    player_N names are stable within the supplied enrollment order only. They
    never establish identity continuity between tasks.
    """
    clips = _rows(report.get("clips"))
    outcomes = _rows(report.get("shot_outcomes"))
    registered = list(dict.fromkeys(value for value in summary.get("student_ids", []) or [] if _identity(value)))
    identities = list(registered)
    for clip in clips:
        student = _identity(clip.get("student_id"))
        if student and student not in identities:
            identities.append(student)
    mapping = {student: f"player_{index}" for index, student in enumerate(identities, 1)}
    subjects = [AnalystSubject(id=public, label=f"球员 {index}") for index, public in enumerate(mapping.values(), 1)]
    final_keys = {_key(clip) for clip in clips if _key(clip) is not None}
    joined: dict[tuple[str, str], list[dict]] = {}
    for outcome in outcomes:
        if _key(outcome) in final_keys:
            joined.setdefault(_key(outcome), []).append(outcome)
    unlinked = sum(_key(outcome) not in final_keys for outcome in outcomes)
    counts = dict.fromkeys(SUPPORTED_ACTIONS, 0)
    evidence = []
    pose = pose if isinstance(pose, dict) else {}
    offsets = camera_offsets_ms if isinstance(camera_offsets_ms, dict) else (
        pose.get("camera_offsets_ms", {}) if _pose_verified(pose) else {}
    )
    offsets = offsets if isinstance(offsets, dict) else {}
    # Triangulation used the artifact's sync, so current seek offsets must not
    # silently shift its sample times or cross-camera geometry. Compare numeric
    # offsets rather than JSON bytes: formatting/notes do not change the clock.
    pose_offsets = pose.get("camera_offsets_ms")
    pose_offsets = pose_offsets if isinstance(pose_offsets, dict) else {}
    pose_sync_matches = {
        camera: _number(pose_offsets.get(camera)) for camera in CAMERAS
        if _number(pose_offsets.get(camera)) is not None
    } == {
        camera: _number(offsets.get(camera)) for camera in CAMERAS
        if _number(offsets.get(camera)) is not None
    }
    for clip in clips:
        action = clip.get("action_type")
        if action not in SUPPORTED_ACTIONS:
            continue
        counts[action] += 1
        start = max(0., _number(clip.get("start_ms")) or 0.)
        end = max(start, _number(clip.get("end_ms")) or start)
        release = _number(clip.get("release_ms"))
        time = min(end, max(start, release)) if release is not None else start
        results = {
            "make" if row.get("made") is True else "miss" if row.get("made") is False else "undetermined"
            for row in joined.get(_key(clip), [])
        }
        result = (next(iter(results)) if len(results) == 1 else "undetermined") if action != "triple_threat" else None
        confidence = _number(clip.get("confidence"))
        # Exported ActionClip anchors are nullable; the product's configured
        # action camera is cam_03. Its actual sync offset is still required.
        anchor = clip.get("anchor_camera") or "cam_03"
        anchor_offset = _number(offsets.get(anchor))
        common = time - anchor_offset if anchor_offset is not None else None
        times = {camera: common + offsets[camera] for camera in CAMERAS
                 if common is not None and _number(offsets.get(camera)) is not None and common + offsets[camera] >= 0}
        if "cam_03" in times:
            times["phases"] = times["cam_03"]
        elif anchor == "cam_03":
            times["phases"] = time
        event_index = len(evidence) + 1
        evidence.append(AnalystEvidence(
            id=f"event-{event_index}", event_index=event_index, subject_id=mapping.get(clip.get("student_id")),
            action_type=action, start_ms=start, end_ms=end, time_ms=time, result=result,
            confidence=confidence if confidence is not None and 0 <= confidence <= 1 else None,
            times_ms=times,
            angles=_event_angles(pose, clip, start - anchor_offset, end - anchor_offset, common)
                   if anchor_offset is not None and pose_sync_matches else {},
        ))
    stats = report.get("shot_stats") or {}
    totals = {key: max(0, int(_number(stats.get(key)) or 0)) for key in ("attempts", "makes", "misses", "undetermined")}
    available = any(event.angles for event in evidence)
    warnings = []
    if len(evidence) != len(clips):
        warnings.append("部分片段不属于当前支持的四类动作，未计入动作统计")
    if unlinked:
        warnings.append(f"{unlinked} 个投篮结果无法可靠关联到最终片段及球员")
    if not available:
        warnings.append("缺少经过验证的姿态、身份或标定数据，仅提供基础统计")
    if set(CAMERAS) - offsets.keys():
        warnings.append("部分摄像机缺少时间同步信息，未提供对应跳转时间")
    return AnalystFacts(
        metrics=AnalystMetrics(action_counts=ProductActionCounts(**counts),
            shots=ProductShotSummary(**totals, make_rate=totals["makes"] / totals["attempts"] if totals["attempts"] else None,
                                     unlinked_outcomes=unlinked),
            registered_participant_count=len(registered), event_count=len(evidence)),
        subjects=subjects, evidence=evidence, warnings=warnings, pose_available=available,
    )


def metrics_for_subject(facts: AnalystFacts, subject_id: str) -> AnalystMetrics:
    if subject_id not in {subject.id for subject in facts.subjects}:
        raise ValueError("Unknown subject")
    events = [event for event in facts.evidence if event.subject_id == subject_id]
    shots = [event for event in events if event.action_type != "triple_threat"]
    makes = sum(event.result == "make" for event in shots)
    misses = sum(event.result == "miss" for event in shots)
    return AnalystMetrics(
        action_counts=ProductActionCounts(**{action: sum(event.action_type == action for event in events) for action in SUPPORTED_ACTIONS}),
        shots=ProductShotSummary(attempts=len(shots), makes=makes, misses=misses,
            undetermined=len(shots) - makes - misses, make_rate=makes / len(shots) if shots else None),
        registered_participant_count=1, event_count=len(events),
    )


def _read_json(path: Path, *, optional: bool = False) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        if optional:
            return {}
        raise


def _signature(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev]


def _input_digests(paths: dict, previous: dict | None = None) -> tuple[dict[str, str], dict]:
    digests, signatures = {}, {}
    previous = previous or {}
    old_digests = previous.get("_source_digests", {})
    old_signatures = previous.get("_source_signatures", {})
    for slot in CAMERAS:
        if not isinstance(paths.get(slot), (str, Path)):
            continue
        path = Path(paths[slot])
        try:
            signature = _signature(path)
            cache_key = (str(path.absolute()), *signature)
            if old_signatures.get(slot) == signature and isinstance(old_digests.get(slot), str):
                value = old_digests[slot]
            else:
                with _CACHE_LOCK:
                    value = _DIGEST_CACHE.get(cache_key)
                if value is None:
                    digest = hashlib.sha256()
                    with path.open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            digest.update(chunk)
                    # A concurrent replacement is not a verified input version.
                    if _signature(path) != signature:
                        continue
                    value = digest.hexdigest()
                with _CACHE_LOCK:
                    _DIGEST_CACHE[cache_key] = value
                    _DIGEST_CACHE.move_to_end(cache_key)
                    while len(_DIGEST_CACHE) > 256:
                        _DIGEST_CACHE.popitem(last=False)
        except OSError:
            continue
        digests[slot], signatures[slot] = value, signature
    return digests, signatures


def _fingerprint(digests: dict, task_id: str) -> str:
    if len(digests) != 4:
        return "task:" + hashlib.sha256(task_id.encode()).hexdigest()
    return "sha256:" + hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def source_fingerprint(camera_paths: dict, enrollment_path: str | Path | None = None, *, task_id: str) -> str:
    """Stream the four videos only; enrollment/model data do not define a session.

    enrollment_path remains accepted for callers using the original signature.
    Missing camera inputs stay task-local instead of grouping unknown sources.
    """
    paths = dict(camera_paths)
    if enrollment_path is not None:
        paths["enrollment_video"] = enrollment_path
    return _fingerprint(_input_digests(paths)[0], task_id)


def _persist(path: Path, payload: dict) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            json.dump(payload, target, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_facts(output: Path, paths: dict, source_id: str, *, persist: bool) -> AnalystFacts:
    report = _read_json(output / "report.json")
    summary = _read_json(output / "summary.json", optional=True)
    pose = _read_json(output / "analyst_pose.json", optional=True)
    artifact = output / "analyst_facts.json"
    if persist:
        previous = _read_json(artifact, optional=True)
    else:
        with _CACHE_LOCK:
            previous = _PRESET_CACHE.get(str(output.absolute()), {})
        if not previous:
            previous = _read_json(artifact, optional=True)
    digests, signatures = _input_digests(paths, previous)
    fingerprint = _fingerprint(digests, source_id)
    old_digests = previous.get("_source_digests", {})
    if (len(digests) < 4 and len(old_digests) == 4
            and all(old_digests.get(key) == value for key, value in digests.items())):
        fingerprint = _fingerprint(old_digests, source_id)
        digests = old_digests
        signatures = {**previous.get("_source_signatures", {}), **signatures}
    provenance = pose.get("provenance") or {}
    videos = provenance.get("videos") if isinstance(provenance, dict) else None
    source_match = isinstance(videos, dict) and len(digests) == 4 and all(
        isinstance(videos.get(camera), dict) and videos[camera].get("sha256") == digests.get(camera) for camera in CAMERAS)
    sync_path = paths.get("sync")
    sync = _read_json(Path(sync_path), optional=True) if isinstance(sync_path, (str, Path)) else {}
    offsets = sync.get("camera_time_offsets_ms")
    if not isinstance(offsets, dict) and source_match:
        offsets = pose.get("camera_offsets_ms")
    offsets = {camera: float(offsets[camera]) for camera in CAMERAS if _number(offsets.get(camera)) is not None} if isinstance(offsets, dict) else None
    facts = build_analyst_facts(report, summary, pose if source_match else None, camera_offsets_ms=offsets)
    facts.fingerprint = fingerprint
    payload = {**facts.model_dump(mode="json"), "_source_digests": digests, "_source_signatures": signatures}
    if persist:
        if payload != previous:
            _persist(artifact, payload)
    else:
        with _CACHE_LOCK:
            key = str(output.absolute())
            _PRESET_CACHE[key] = payload
            _PRESET_CACHE.move_to_end(key)
            while len(_PRESET_CACHE) > 32:
                _PRESET_CACHE.popitem(last=False)
    return facts


def load_task_facts(app, task) -> AnalystFacts:
    """Use this task's final output even when it originated from a preset."""
    try:
        manifest = json.loads(task.input_manifest_json)
    except (TypeError, ValueError):
        manifest = {}
    return _load_facts(app.state.storage.analysis_root(task.id) / "output",
                       manifest if isinstance(manifest, dict) else {}, task.id, persist=True)


def load_preset_facts(app, preset_id: str) -> AnalystFacts:
    catalog = app.state.presets
    output = catalog.group_root(preset_id)
    try:
        manifest = catalog.rerun_manifest(preset_id)
    except FileNotFoundError:
        # Catalog's rerun check also requires enrollment/sync. Their expiry must
        # not hide the four still-available videos of this explicit preset group.
        definition = catalog._preset(preset_id)
        manifest = catalog._original_sources(definition)
        manifest["sync"] = catalog.sample_root / "test_data_v3" / "sync" / f"{definition.group_id}.json"
    return _load_facts(output, manifest, f"preset:{preset_id}", persist=False)
