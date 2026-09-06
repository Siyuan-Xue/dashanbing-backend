"""Repair the reviewed legacy v3 bundle, never arbitrary uploaded task results.

Defaults to dry-run. --apply requires an unused --backup-dir. All candidates
must be unique after camera sync and cover every final shot exactly once.
Original scores, action timings and raw motion records remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

REVIEWED = {
    3: "2d03dc7445c339df3773f14075c8237c6913fd2c5fa9f21916f7860254bf26a1",
    6: "c62af95a194d62b1de1662a037b337a4df93e2c4046a1e39bbaeb72ffd1ca5a4",
}
SHOTS = {"free_throw", "jump_shot", "layup"}


def repair_report(report, ball_minus_action_ms):
    """Offline association for the hash-pinned, reviewed single-hoop samples."""
    result = deepcopy(report)
    shots = [c for c in report["clips"] if c["action_type"] in SHOTS]
    if len(shots) != len(report["shot_outcomes"]):
        raise ValueError("Every final shot must have exactly one recorded outcome")
    used, audit = set(), []
    for outcome in result["shot_outcomes"]:
        when = float(outcome["anchor_timestamp_ms"]) - ball_minus_action_ms
        candidates = [c for c in shots if c["action_type"] == outcome["action_type"]
                      and c.get("release_ms") is not None
                      and 0 <= when - float(c["release_ms"]) <= 3500]
        if not math.isfinite(when) or len(candidates) != 1:
            raise ValueError("Ambiguous or missing time evidence; manual review required")
        clip = candidates[0]
        if clip["clip_id"] in used:
            raise ValueError("Multiple outcomes would be assigned to the same final shot")
        used.add(clip["clip_id"])
        audit.append({"old_clip_id": outcome["clip_id"], "old_student_id": outcome["student_id"],
                      "clip_id": clip["clip_id"], "student_id": clip["student_id"],
                      "release_ms": clip["release_ms"], "ball_anchor_ms": outcome["anchor_timestamp_ms"],
                      "synced_delay_ms": when - clip["release_ms"], "made": outcome["made"]})
        outcome.update(clip_id=clip["clip_id"], student_id=clip["student_id"])
    if used != {c["clip_id"] for c in shots}:
        raise ValueError("Final shots are not covered one-to-one")
    return result, audit


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def plan(sample_root):
    base = sample_root / "outputs/v3"
    changes, audit = {}, {}
    manifest = json.loads((base / "manifest.json").read_text())
    for group_number, expected in REVIEWED.items():
        group = base / f"group_{group_number:02d}"
        raw = (group / "report.json").read_bytes()
        if _sha(raw) != expected:
            raise ValueError(f"group_{group_number:02d}: unreviewed report hash, refusing repair")
        report = json.loads(raw)
        sync = json.loads((sample_root / f"test_data_v3/sync/group_{group_number:02d}.json").read_text())
        offsets = sync["camera_time_offsets_ms"]
        repaired, audit[group.name] = repair_report(report, offsets["cam_04"] - offsets["cam_03"])
        changes[group / "report.json"] = _bytes(repaired)
        motion = json.loads((group / "motion.json").read_text())
        if motion["clips"] != report["clips"] or motion["metadata"]["shot_outcomes"] != report["shot_outcomes"]:
            raise ValueError("Motion source does not match the reviewed report")
        motion["metadata"]["shot_outcomes"] = repaired["shot_outcomes"]
        changes[group / "motion.json"] = _bytes(motion)
        # Some deployed bundles omit the unused research dashboard entirely.
        if not (group / "dashboard.json").exists():
            if (group / "dashboard.html").exists():
                raise ValueError("Archived dashboard HTML has no JSON source")
            continue
        dashboard = json.loads((group / "dashboard.json").read_text())
        by_clip = {o["clip_id"]: o for o in repaired["shot_outcomes"]}
        for shot in dashboard["shots"]:
            outcome = by_clip.get(shot["clip_id"], {})
            made = outcome.get("made")
            shot.update(made=made, result="MAKE" if made is True else "MISS" if made is False else "—",
                        confidence=round(outcome.get("confidence", 0), 2) if outcome else None,
                        reason=(outcome.get("metadata") or {}).get("reason"))
        for label, made in (("make", True), ("miss", False)):
            angles = {}
            for shot in dashboard["shots"]:
                if shot["made"] is made:
                    for key, value in (shot.get("release_angles") or {}).items():
                        if key in dashboard.get("release_angle_series", {}):
                            angles.setdefault(key, []).append(value)
            dashboard[f"mean_release_angles_{label}"] = {k: round(sum(v) / len(v), 1) for k, v in angles.items()}
        changes[group / "dashboard.json"] = _bytes(dashboard)
        # Preserve the archived dashboard template and relative media URLs.
        html = (group / "dashboard.html").read_text()
        match = re.search(r"^const DATA = (.+);$", html, re.MULTILINE)
        if not match:
            raise ValueError("Unexpected dashboard template")
        payload = json.loads(match[1]); payload.update(dashboard)
        html = html[:match.start(1)] + json.dumps(payload, ensure_ascii=False) + html[match.end(1):]
        changes[group / "dashboard.html"] = html.encode()
    for number in (3, 5, 6):
        summary = json.loads((base / f"group_{number:02d}/summary.json").read_text())
        report = json.loads(changes.get(base / f"group_{number:02d}/report.json", (base / f"group_{number:02d}/report.json").read_bytes()))
        if summary["clip_count"] != len(report["clips"]) or summary["action_type_hist"] != dict(Counter(c["action_type"] for c in report["clips"])):
            raise ValueError("Final summary and report disagree")
        entry = next(g for g in manifest["groups"] if g["group_id"] == summary["group_id"])
        entry.update(clip_count=summary["clip_count"], action_type_hist=summary["action_type_hist"])
    changes[base / "manifest.json"] = _bytes(manifest)
    return changes, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    changes, audit = plan(args.sample_root)
    record = {"associations": audit, "files": {str(p.relative_to(args.sample_root)):
              {"before": _sha(p.read_bytes()), "after": _sha(data)} for p, data in changes.items()}}
    if args.apply:
        if args.backup_dir is None or args.backup_dir.exists():
            parser.error("--apply requires a new --backup-dir")
        args.backup_dir.mkdir(parents=True)
        for path in changes:
            backup = args.backup_dir / path.relative_to(args.sample_root)
            backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, backup)
        (args.backup_dir / "repair-audit.json").write_bytes(_bytes(record))
        try:
            for path, data in changes.items():
                temp = path.with_name(path.name + ".repair-next")
                temp.write_bytes(data); temp.replace(path)
        except BaseException:
            for path in changes: shutil.copy2(args.backup_dir / path.relative_to(args.sample_root), path)
            raise
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
