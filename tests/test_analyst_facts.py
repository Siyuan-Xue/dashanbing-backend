import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


def sample_report():
    return {
        "clips": [
            {"clip_id": "private-a:1", "student_id": "private-a", "action_type": "jump_shot", "start_ms": 1000, "end_ms": 2000, "release_ms": 1500, "confidence": .8},
            {"clip_id": "private-b:1", "student_id": "private-b", "action_type": "layup", "start_ms": 3000, "end_ms": 4000, "release_ms": 3500},
            {"clip_id": "private-a:2", "student_id": "private-a", "action_type": "triple_threat", "start_ms": 5000, "end_ms": 6000},
        ],
        "shot_outcomes": [
            {"clip_id": "private-a:1", "student_id": "private-b", "made": True},
            {"clip_id": "private-b:1", "student_id": "private-b", "made": None},
            {"clip_id": "obsolete", "student_id": "private-a", "made": False},
        ],
        "shot_stats": {"attempts": 5, "makes": 2, "misses": 1, "undetermined": 2},
        "private_path": "/private/model/secret",
    }


def test_facts_join_final_clip_and_person_without_changing_independent_totals():
    from app.services.analyst_facts import build_analyst_facts, metrics_for_subject

    facts = build_analyst_facts(sample_report(), {"student_ids": ["private-b", "private-a", "private-c"]})
    assert [s.id for s in facts.subjects] == ["player_1", "player_2", "player_3"]
    assert facts.evidence[0].subject_id == "player_2"
    assert facts.evidence[0].id == "event-1"
    assert facts.evidence[0].result == "undetermined"
    assert facts.evidence[1].result == "undetermined"
    assert facts.metrics.shots.attempts == 5
    assert facts.metrics.shots.makes == 2
    assert facts.metrics.shots.unlinked_outcomes == 2
    assert facts.metrics.registered_participant_count == 3
    assert facts.metrics.event_count == 3
    person = metrics_for_subject(facts, "player_2")
    assert person.action_counts.jump_shot == 1
    assert person.action_counts.triple_threat == 1
    assert person.shots.attempts == 1
    assert person.shots.misses == 0
    assert person.shots.undetermined == 1
    assert metrics_for_subject(facts, "player_3").event_count == 0
    assert "private-" not in facts.model_dump_json()
    assert "/private" not in facts.model_dump_json()


def verified_pose():
    return {"schema_version": 1, "available": True, "time_basis": "common",
            "camera_offsets_ms": {"cam_01": 200, "cam_02": -100, "cam_03": 0},
            "provenance": {"verified": True, "calibration_verified": True, "identity_verified": True},
            "events": [{"clip_id": "private-a:1", "student_id": "private-a", "time_ms": 1500,
                        "angles": {"left_elbow": 90, "right_knee": 120, "wrist": 23},
                        "camera_count": 2, "reprojection_error_px": 1.2}]}


def test_pose_requires_positive_provenance_exact_identity_and_valid_angles():
    from app.services.analyst_facts import build_analyst_facts

    report = sample_report()
    pose = verified_pose()
    good = build_analyst_facts(report, {}, pose)
    assert good.pose_available is True
    assert good.evidence[0].angles == {"left_elbow": 90, "right_knee": 120}
    assert good.evidence[0].times_ms == {"phases": 1500, "cam_01": 1700, "cam_02": 1400, "cam_03": 1500}
    for mutation in (
        lambda p: p.update(provenance={}),
        lambda p: p["provenance"].update(calibration_verified=False),
        lambda p: p["events"][0].update(student_id="private-b"),
        lambda p: p["events"][0].update(clip_id="obsolete"),
        lambda p: p["events"][0].update(camera_count=1),
        lambda p: p["events"][0].update(reprojection_error_px=100),
        lambda p: p["events"][0].update(time_ms=9000),
        lambda p: p["events"][0].update(angles={"left_elbow": float("nan"), "right_knee": 181}),
    ):
        invalid = deepcopy(pose)
        mutation(invalid)
        facts = build_analyst_facts(report, {}, invalid)
        assert not facts.pose_available
        assert not any(event.angles for event in facts.evidence)


def test_missing_pose_is_basic_stats_without_invented_calibration_or_private_warnings():
    from app.services.analyst_facts import build_analyst_facts

    facts = build_analyst_facts(sample_report(), {}, {"available": False, "reason": "/private/secret missing"})
    assert facts.pose_available is False
    assert facts.metrics.event_count == 3
    assert facts.evidence[0].times_ms == {"phases": 1500}
    assert facts.warnings
    assert "/private" not in facts.model_dump_json()


def test_fingerprint_streams_four_videos_ignores_paths_enrollment_and_models(tmp_path, monkeypatch):
    from app.services.analyst_facts import source_fingerprint

    cameras = {}
    for index in range(1, 5):
        path = tmp_path / f"{index}.mkv"
        path.write_bytes(bytes([index]) * 17)
        cameras[f"cam_{index:02d}"] = path
    enrollment = tmp_path / "enrollment.mkv"
    enrollment.write_bytes(b"enrolled")
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("must stream videos"))
    first = source_fingerprint(cameras, enrollment, task_id="first")
    moved = {}
    for slot, path in cameras.items():
        dest = path.with_suffix(".mov")
        path.rename(dest)
        moved[slot] = dest
    assert source_fingerprint(moved, enrollment, task_id="second") == first
    enrollment.write_bytes(b"different identity")
    assert source_fingerprint(moved, enrollment, task_id="second") == first
    moved["cam_01"].write_bytes(b"different camera input")
    assert source_fingerprint(moved, enrollment, task_id="second") != first
    moved["cam_01"].unlink()
    assert source_fingerprint(moved, enrollment, task_id="first") != source_fingerprint(moved, enrollment, task_id="second")


def test_task_loader_uses_actual_output_persists_facts_and_retains_content_fingerprint(tmp_path):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts

    root = tmp_path / "task"
    output = root / "output"
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(sample_report()))
    (output / "summary.json").write_text('{"student_ids":["private-a"]}')
    manifest = {}
    for slot in ("cam_01", "cam_02", "cam_03", "cam_04", "enrollment_video"):
        source = root / slot
        source.write_bytes(slot.encode())
        manifest[slot] = str(source)
    task = Analysis(id="task", owner_id=1, title="Task", status="completed", preset_id="quick-demo", input_manifest_json=json.dumps(manifest))
    app = SimpleNamespace(state=SimpleNamespace(storage=SimpleNamespace(analysis_root=lambda _: root)))
    first = load_task_facts(app, task)
    artifact = json.loads((output / "analyst_facts.json").read_text())
    assert artifact["metrics"]["event_count"] == 3
    assert artifact["fingerprint"] == first.fingerprint
    for path in manifest.values():
        Path(path).unlink()
    assert load_task_facts(app, task).fingerprint == first.fingerprint


def test_preset_loader_reads_correct_group_and_old_results_without_pose(tmp_path):
    from app.services.analyst_facts import load_preset_facts
    from app.services.presets import PresetCatalog

    output = tmp_path / "outputs/v3/group_04"
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(sample_report()))
    (output / "summary.json").write_text('{}')
    app = SimpleNamespace(state=SimpleNamespace(presets=PresetCatalog(tmp_path)))
    facts = load_preset_facts(app, "quick-demo")
    assert facts.metrics.event_count == 3
    assert facts.pose_available is False
    with pytest.raises((KeyError, FileNotFoundError)):
        load_preset_facts(app, "missing")


def test_pose_joins_common_time_and_camera_seeks_respect_nonzero_anchor_offset():
    from app.services.analyst_facts import build_analyst_facts

    report = sample_report()
    report["clips"][0]["anchor_camera"] = "cam_03"
    pose = verified_pose()
    pose["camera_offsets_ms"]["cam_03"] = 1000
    pose["events"][0]["time_ms"] = 500
    facts = build_analyst_facts(report, {}, pose)
    assert facts.pose_available is True
    assert facts.evidence[0].time_ms == 1500
    assert facts.evidence[0].times_ms == {"phases": 1500, "cam_01": 700, "cam_02": 400, "cam_03": 1500}


def test_null_clip_anchor_uses_known_action_camera_and_its_real_offset():
    from app.services.analyst_facts import build_analyst_facts

    report = sample_report()
    report["clips"][0]["anchor_camera"] = None
    pose = verified_pose()
    pose["camera_offsets_ms"]["cam_03"] = 700
    pose["events"][0]["time_ms"] = 800
    facts = build_analyst_facts(report, {}, pose)
    assert facts.pose_available is True
    assert facts.evidence[0].times_ms == {"phases": 1500, "cam_01": 1000, "cam_02": 700, "cam_03": 1500}


@pytest.mark.parametrize("camera", ["cam_01", "cam_03"])
def test_explicit_sync_changes_disable_pose_but_keep_current_camera_seeks(camera):
    from app.services.analyst_facts import build_analyst_facts

    pose = verified_pose()
    offsets = dict(pose["camera_offsets_ms"])
    offsets[camera] += 100
    facts = build_analyst_facts(sample_report(), {}, pose, camera_offsets_ms=offsets)
    assert facts.pose_available is False
    assert facts.evidence[0].angles == {}
    assert facts.evidence[0].times_ms["cam_01"] == (1800 if camera == "cam_01" else 1600)


def test_task_loader_hashes_once_per_file_version_and_never_reuses_changed_partial_inputs(tmp_path, monkeypatch):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts

    output = tmp_path / "output"
    output.mkdir()
    (output / "report.json").write_text(json.dumps(sample_report()))
    manifest = {}
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        path = tmp_path / camera
        path.write_bytes(camera.encode())
        manifest[camera] = str(path)
    app = SimpleNamespace(state=SimpleNamespace(storage=SimpleNamespace(analysis_root=lambda _: tmp_path)))
    task = Analysis(id="task", title="t", owner_id=1, input_manifest_json=json.dumps(manifest))
    first = load_task_facts(app, task)
    original_open = Path.open
    reads = []
    def record_open(path, *args, **kwargs):
        if path.name.startswith("cam_") and args and args[0] == "rb":
            reads.append(path.name)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", record_open)
    assert load_task_facts(app, task).fingerprint == first.fingerprint
    assert reads == []
    Path(manifest["cam_01"]).write_bytes(b"changed")
    changed = load_task_facts(app, task)
    assert changed.fingerprint != first.fingerprint
    assert reads == ["cam_01"]
    Path(manifest["cam_02"]).unlink()
    Path(manifest["cam_03"]).write_bytes(b"new partial input")
    assert load_task_facts(app, task).fingerprint.startswith("task:")


def test_unavailable_pose_uses_task_sync_and_phases_camera_instead_of_clip_anchor(tmp_path):
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts

    output = tmp_path / "output"
    output.mkdir()
    report = sample_report()
    report["clips"][0]["anchor_camera"] = "cam_01"
    (output / "report.json").write_text(json.dumps(report))
    (output / "analyst_pose.json").write_text('{"available":false,"reason":"missing calibration"}')
    sync = tmp_path / "sync.json"
    sync.write_text(json.dumps({"camera_time_offsets_ms": {"cam_01": 1000, "cam_02": -100, "cam_03": 200, "cam_04": 50}, "anchor_camera": "cam_03"}))
    task = Analysis(id="task", title="t", owner_id=1, input_manifest_json=json.dumps({"sync": str(sync)}))
    app = SimpleNamespace(state=SimpleNamespace(storage=SimpleNamespace(analysis_root=lambda _: tmp_path)))
    facts = load_task_facts(app, task)
    assert facts.pose_available is False
    assert facts.evidence[0].times_ms == {"phases": 700, "cam_01": 1500, "cam_02": 400, "cam_03": 700, "cam_04": 550}
    sync.write_text('{"camera_time_offsets_ms":{"cam_02":200}}')
    unknown = load_task_facts(app, task)
    assert "cam_02" not in unknown.evidence[0].times_ms


def test_readonly_preset_fingerprint_cache_avoids_reopening_unchanged_sources(tmp_path, monkeypatch):
    from app.services.analyst_facts import load_preset_facts
    from app.services.presets import PresetCatalog

    output = tmp_path / "outputs/v3/group_04"
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(sample_report()))
    inputs = tmp_path / "test_data_v3"
    inputs.mkdir()
    for index in range(1, 5):
        (inputs / f"4-{index}.mkv").write_bytes(f"camera-{index}".encode())
    # Enrollment and sync may already be expired; still hash the four sources.
    app = SimpleNamespace(state=SimpleNamespace(presets=PresetCatalog(tmp_path)))
    first = load_preset_facts(app, "quick-demo")
    assert first.fingerprint.startswith("sha256:")
    original_open = Path.open
    def no_video_reads(path, *args, **kwargs):
        if path.suffix == ".mkv" and args and args[0] == "rb":
            pytest.fail("preset poll must reuse cached video digests")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", no_video_reads)
    assert load_preset_facts(app, "quick-demo").fingerprint == first.fingerprint
    assert not (output / "analyst_facts.json").exists()


def test_task_pose_source_provenance_must_match_the_actual_four_video_digests(tmp_path):
    import hashlib
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts

    output = tmp_path / "output"
    output.mkdir()
    (output / "report.json").write_text(json.dumps(sample_report()))
    manifest, videos = {}, {}
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        path = tmp_path / camera
        path.write_bytes(camera.encode())
        manifest[camera] = str(path)
        videos[camera] = {"sha256": hashlib.sha256(camera.encode()).hexdigest(), "path": "/private/not-public"}
    pose = verified_pose()
    pose["provenance"]["videos"] = videos
    (output / "analyst_pose.json").write_text(json.dumps(pose))
    task = Analysis(id="task", title="t", owner_id=1, input_manifest_json=json.dumps(manifest))
    app = SimpleNamespace(state=SimpleNamespace(storage=SimpleNamespace(analysis_root=lambda _: tmp_path)))
    good = load_task_facts(app, task)
    assert good.pose_available is True
    assert "/private" not in good.model_dump_json()
    Path(manifest["cam_01"]).write_bytes(b"replacement-input")
    stale = load_task_facts(app, task)
    assert stale.pose_available is False
    assert stale.evidence[0].angles == {}


def test_task_sync_edit_invalidates_source_matched_pose_without_disabling_seek(tmp_path):
    import hashlib
    from app.models import Analysis
    from app.services.analyst_facts import load_task_facts

    output = tmp_path / "output"
    output.mkdir()
    (output / "report.json").write_text(json.dumps(sample_report()))
    manifest, videos = {}, {}
    for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
        path = tmp_path / camera
        path.write_bytes(camera.encode())
        manifest[camera] = str(path)
        videos[camera] = {"sha256": hashlib.sha256(camera.encode()).hexdigest()}
    pose = verified_pose()
    pose["provenance"]["videos"] = videos
    sync = tmp_path / "sync.json"
    sync.write_text(json.dumps({"camera_time_offsets_ms": pose["camera_offsets_ms"]}))
    pose["provenance"]["sync"] = {"sha256": hashlib.sha256(sync.read_bytes()).hexdigest()}
    (output / "analyst_pose.json").write_text(json.dumps(pose))
    manifest["sync"] = str(sync)
    task = Analysis(id="task", title="t", owner_id=1, input_manifest_json=json.dumps(manifest))
    app = SimpleNamespace(state=SimpleNamespace(storage=SimpleNamespace(analysis_root=lambda _: tmp_path)))
    assert load_task_facts(app, task).pose_available is True
    offsets = {**pose["camera_offsets_ms"], "cam_03": 100}
    sync.write_text(json.dumps({"camera_time_offsets_ms": offsets}))
    changed = load_task_facts(app, task)
    assert changed.pose_available is False
    assert changed.evidence[0].angles == {}
    assert changed.evidence[0].times_ms == {"phases": 1500, "cam_01": 1600, "cam_02": 1300, "cam_03": 1500}
