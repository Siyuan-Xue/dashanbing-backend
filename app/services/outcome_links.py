"""Validate existing shot links; never infer a new player or clip at read time."""
from collections import Counter
import math


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def linked_outcomes(clips: list[dict], outcomes: list[dict], *, require_identity=False):
    counts = Counter(clip.get("clip_id") for clip in clips)
    by_id = {clip.get("clip_id"): clip for clip in clips if clip.get("clip_id") and counts[clip.get("clip_id")] == 1}
    joined, rejected = {}, []
    for outcome in outcomes:
        clip = by_id.get(outcome.get("clip_id"))
        if clip is None or not _compatible(clip, outcome, require_identity):
            rejected.append(outcome)
        else:
            joined.setdefault(clip["clip_id"], []).append(outcome)
    return joined, rejected


def _compatible(clip, outcome, require_identity):
    if clip.get("action_type") not in {"free_throw", "jump_shot", "layup"}:
        return False
    if outcome.get("action_type") and outcome["action_type"] != clip.get("action_type"):
        return False
    student = outcome.get("student_id")
    if require_identity and (not student or not clip.get("student_id")):
        return False
    if student and student != clip.get("student_id"):
        return False
    metadata = outcome.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    when = _number(outcome.get("anchor_timestamp_ms"))
    offset = _number(metadata.get("clock_offset_ms"))
    start, end = _number(clip.get("start_ms")), _number(clip.get("end_ms"))
    # The research clip scorer records ball-clock = action-clock + offset.
    # Its anchor is a ball segment, not the release frame. Allow the scoring
    # window/flight delay; reject gross conflicts caused by recycled indices.
    # Older outputs without clock provenance retain their legacy ID join.
    if str(metadata.get("source", "")).startswith("clip_") and all(v is not None for v in (when, offset, start, end)):
        if not start - 1500 <= when - offset <= end + 5000:
            return False
    return True
