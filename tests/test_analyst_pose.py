"""Regression tests for task-bound, identity-bound calibrated analyst evidence."""

import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_engine"))

from src.pose.action_skeleton3d import process_group_action_skeletons


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


@pytest.fixture
def pose_task(tmp_path):
    group = tmp_path / "group_01"
    session_id = "current-task-session"
    # World-space COCO body, with 90-degree elbows and 180-degree knees.
    xyz = np.zeros((133, 3))
    xyz[:, 1] = 4
    xyz[0] = [0, 4, 1.9]
    for shoulder, elbow, wrist, hip, knee, ankle, side in (
        (5, 7, 9, 11, 13, 15, -1), (6, 8, 10, 12, 14, 16, 1),
    ):
        xyz[shoulder] = [side * .2, 4, 1.6]
        xyz[elbow] = [side * .5, 4, 1.6]
        xyz[wrist] = [side * .5, 4, 1.9]
        xyz[hip] = [side * .15, 4, 1.0]
        xyz[knee] = [side * .15, 4, .55]
        xyz[ankle] = [side * .15, 4, .10]
    # Look forward along world +y; world +z is image up.
    rotation = np.array([[1., 0, 0], [0, 0, -1.], [0, 1., 0]])
    intrinsic = np.array([[1000., 0, 960], [0, 1000., 540], [0, 0, 1.]])
    offsets = {"cam_01": -300., "cam_02": 200., "cam_03": 700.}
    videos, pose_paths, solved, hashes = {}, {}, {}, {}
    for ci, (cam, offset) in enumerate(offsets.items()):
        video = tmp_path / "uploads" / f"random-upload-{ci}.mp4"
        video.parent.mkdir(exist_ok=True)
        video.write_bytes(f"task-video-{ci}".encode())
        videos[cam] = video
        hashes[cam] = hashlib.sha256(video.read_bytes()).hexdigest()
        center = np.array([(ci - 1) * 2., -4, 2.])
        translation = -rotation @ center
        solved[cam] = {
            "status": "ok", "rotation_matrix": rotation.tolist(), "tvec": translation.tolist(),
            "intrinsics": {"camera_matrix": intrinsic.tolist(), "dist_coeffs": [0.] * 5,
                           "width": 1920, "height": 1080},
            "reproj_error_px": {"mean": .5},
        }
        uv, _ = cv2.projectPoints(xyz, cv2.Rodrigues(rotation)[0], translation, intrinsic, np.zeros(5))
        keypoints = np.column_stack([uv.reshape(-1, 2), np.ones(133) * .95]).tolist()
        frames, detections = [], []
        for common_ms in (1000., 1100., 1200.):
            local = common_ms + offset
            frame = round(local / 1000 * 30)
            person = {"student_id": "stu_A", "track_id": 10 + ci, "keypoints": keypoints,
                      "pose_source": "rtmw", "identity_confidence": "high", "bbox": [1, 1, 10, 10]}
            distractor = {**person, "student_id": "stu_B", "track_id": 100 + ci,
                          "bbox": [0, 0, 1900, 1000], "keypoints": np.zeros((133, 3)).tolist()}
            frames.append({"frame": frame, "timestamp_ms": local, "persons": [distractor, person]})
            for p in (distractor, person):
                detections.append({"frame": frame, "timestamp_ms": local, **{k: p[k] for k in
                                   ("student_id", "track_id", "identity_confidence", "bbox")}})
        pose_path = tmp_path / "sessions" / session_id / "perception" / cam / "pose2d.json"
        write_json(pose_path, {"session_id": session_id, "camera_id": cam, "fps": 30., "stride": 3,
                              "source_video": str(video.resolve()), "image_size": [1920, 1080],
                              "processing": "per_camera_isolated", "frames": frames})
        pose_path.with_name("detections.jsonl").write_text("\n".join(json.dumps(d) for d in detections))
        pose_paths[cam] = pose_path
    calibration = tmp_path / "existing-calibration"
    write_json(calibration / "cameras.json", {"solved": {"cameras": solved}, "annotations": {
        "source_video_sha256": hashes, "image_size": {cam: [1920, 1080] for cam in videos}}})
    sync_path = tmp_path / "input" / "sync.json"
    write_json(sync_path, {"camera_time_offsets_ms": offsets, "anchor_camera": "cam_01", "source": "manual_gui"})
    write_json(group / "motion.json", {"session_id": session_id, "metadata": {"anchor_camera": "cam_03"},
               "records": [{"pose_source": "pseudo3d"}], "clips": [{
                   "clip_id": "clip_A", "student_id": "stu_A", "anchor_camera": "cam_03",
                   "start_ms": 1700., "end_ms": 1900., "release_ms": 1800.,
                   "action_type": "free_throw", "phases": [{"name": "set", "start_ms": 1700., "end_ms": 1900.}]}]})
    return {"group_dir": group, "session_id": session_id, "videos": videos, "pose_paths": pose_paths,
            "sync_path": sync_path, "calib_dir": calibration}


def run_pose(task):
    scene = process_group_action_skeletons(**task)
    artifact = json.loads((task["group_dir"] / "analyst_pose.json").read_text())
    return artifact, scene


def test_actual_pose_chain_uses_current_sources_player_and_common_clock(pose_task):
    artifact, scene = run_pose(pose_task)
    assert artifact["schema_version"] == 1
    assert artifact["available"] is True
    assert artifact["reason"] == "ok"
    assert artifact["time_basis"] == "common"
    assert artifact["camera_offsets_ms"] == {"cam_01": -300., "cam_02": 200., "cam_03": 700.}
    assert [e["time_ms"] for e in artifact["events"]] == [1000., 1100., 1200.]
    for event in artifact["events"]:
        assert (event["clip_id"], event["student_id"]) == ("clip_A", "stu_A")
        assert event["angles"] == pytest.approx({"left_elbow": 90., "right_elbow": 90.,
                                                "left_knee": 180., "right_knee": 180.}, abs=.001)
        assert event["camera_count"] == 3
        assert event["reprojection_error_px"] < .001
    assert scene["time_basis"] == "common"
    assert [f["t_ms"] for f in scene["frames"]] == [1000., 1100., 1200.]
    assert all(f["student_id"] == "stu_A" for f in scene["frames"])
    assert artifact["provenance"]["pose_source"] == "calibrated_multiview_triangulation"
    assert all(artifact["provenance"][k] is True for k in ("verified", "calibration_verified", "identity_verified"))
    assert artifact["provenance"]["samples"][0]["track_ids"] == {"cam_01": 10, "cam_02": 11, "cam_03": 12}
    refs = artifact["provenance"]["reference_ranges"]
    assert any(r["joint"] == "right_elbow" and r["min"] == 75 and r["max"] == 90 for r in refs)
    assert all(r["joint"] in artifact["events"][0]["angles"] for r in refs)


@pytest.mark.parametrize("failure", ["missing_calibration", "wrong_source", "same_camera", "one_view",
                                    "identity_switch", "forced_identity", "ambiguous_identity",
                                    "stale_pose_session", "stale_pose_source", "missing_sync",
                                    "wrong_reprojection", "nonfinite_keypoint", "stub_pose", "wrong_resolution"])
def test_inadequate_evidence_is_unavailable_without_fallback(pose_task, failure):
    if failure == "missing_calibration":
        pose_task["calib_dir"] = None
    elif failure in {"wrong_source", "same_camera", "one_view", "wrong_resolution"}:
        path = pose_task["calib_dir"] / "cameras.json"
        doc = json.loads(path.read_text())
        if failure == "wrong_source":
            doc["annotations"]["source_video_sha256"] = {cam: "0" * 64 for cam in pose_task["videos"]}
        elif failure == "one_view":
            doc["solved"]["cameras"] = {"cam_01": doc["solved"]["cameras"]["cam_01"]}
        elif failure == "same_camera":
            doc["solved"]["cameras"] = dict.fromkeys(pose_task["videos"], doc["solved"]["cameras"]["cam_01"])
        else:
            for cam in doc["solved"]["cameras"].values():
                cam["intrinsics"]["width"] = 640
        write_json(path, doc)
    elif failure == "missing_sync":
        pose_task["sync_path"].unlink()
    else:
        for path in pose_task["pose_paths"].values():
            doc = json.loads(path.read_text())
            det_path = path.with_name("detections.jsonl")
            dets = [json.loads(line) for line in det_path.read_text().splitlines()]
            if failure == "stale_pose_session":
                doc["session_id"] = "previous-session"
            if failure == "stale_pose_source":
                doc["source_video"] = "/old/test_data_v1/1-1.mkv"
            for index, fr in enumerate(doc["frames"]):
                target = fr["persons"][1]
                if failure == "identity_switch" and index == 1:
                    dets[index * 2 + 1]["student_id"] = "stu_B"
                if failure == "forced_identity":
                    dets[index * 2 + 1]["identity_confidence"] = "forced"
                if failure == "ambiguous_identity":
                    dets[index * 2]["student_id"] = "stu_A"
                if failure == "wrong_reprojection":
                    target["keypoints"][7][1] += {"cam_01": 180, "cam_02": -180, "cam_03": 60}[doc["camera_id"]]
                if failure == "nonfinite_keypoint":
                    target["keypoints"][7][0] = float("nan")
                if failure == "stub_pose":
                    target["pose_source"] = "stub"
            write_json(path, doc)
            det_path.write_text("\n".join(json.dumps(d) for d in dets))
    artifact, scene = run_pose(pose_task)
    assert artifact["available"] is False
    assert artifact["events"] == []
    assert artifact["reason"] and artifact["reason"] != "ok"
    assert not scene["frames"]
    assert (pose_task["group_dir"] / "motion.json").exists()
    assert artifact["provenance"]["reference_ranges"] == []
    assert artifact["provenance"]["verified"] is False


def test_no_implicit_testset_or_calibration_from_group_number(tmp_path):
    write_json(tmp_path / "group_01" / "motion.json", {"clips": []})
    scene = process_group_action_skeletons(tmp_path / "group_01")
    artifact = json.loads((tmp_path / "group_01" / "analyst_pose.json").read_text())
    assert artifact["available"] is False
    assert artifact["reason"] == "missing_task_context"
    assert scene["frames"] == []


def test_missing_joint_view_does_not_count_as_three_camera_evidence(pose_task):
    # One bad view of an elbow is excluded; the two good views still suffice.
    path = pose_task["pose_paths"]["cam_02"]
    doc = json.loads(path.read_text())
    for fr in doc["frames"]:
        fr["persons"][1]["keypoints"][7][2] = .01
    write_json(path, doc)
    artifact, _ = run_pose(pose_task)
    assert artifact["available"] is True
    assert all(e["camera_count"] == 2 for e in artifact["events"])


def test_large_offsets_do_not_expand_windows_or_reestimate_sync(pose_task):
    sync = json.loads(pose_task["sync_path"].read_text())
    sync["camera_time_offsets_ms"]["cam_01"] += 100_000
    sync["camera_time_offsets_ms"]["cam_02"] += 100_000
    write_json(pose_task["sync_path"], sync)
    artifact, _ = run_pose(pose_task)
    assert artifact["available"] is False
    assert artifact["camera_offsets_ms"]["cam_01"] == 99700


def test_perception_binds_export_to_actual_video_and_resolution(tmp_path, monkeypatch):
    import src.identity.perception as perception
    from types import SimpleNamespace

    class EmptyCapture:
        def get(self, key):
            return {cv2.CAP_PROP_FPS: 25., cv2.CAP_PROP_FRAME_WIDTH: 1280,
                    cv2.CAP_PROP_FRAME_HEIGHT: 720}.get(key, 0)

        def read(self):
            return False, None

        def release(self):
            pass

    source = tmp_path / "actual-upload.mp4"
    source.write_bytes(b"uploaded-video")
    monkeypatch.setattr(perception, "data_path", lambda *parts: tmp_path.joinpath(*parts))
    monkeypatch.setattr(perception, "EnrollmentGallery", lambda *a: SimpleNamespace(list_students=lambda: ["stu_A"]))
    for name in ("_create_tracker", "create_face_embedder", "create_body_embedder"):
        monkeypatch.setattr(perception, name, lambda *a: None)
    monkeypatch.setattr(perception.cv2, "VideoCapture", lambda *a: EmptyCapture())
    output = perception.run_perception_on_video("actual-session", "cam_03", source)
    doc = json.loads((output / "pose2d.json").read_text())
    assert doc["source_video"] == str(source.resolve())
    assert doc["image_size"] == [1280, 720]
    assert doc["fps"] == 25.


@pytest.mark.parametrize("calibration_error, expected_available", [(0.5, True), (30., False), (52., False)])
def test_product_real_runner_carries_task_context_and_retains_artifact(
    pose_task, tmp_path, monkeypatch, calibration_error, expected_available,
):
    """Stub GPU/DB/media stages; run actual product -> v2 -> 3D -> output copy."""
    import shutil
    import types
    from research_engine import product_runner

    # Original research results must not depend on GLM configuration or on
    # the old sample calibration passing the stricter analyst-only gate.
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    calibration_path = pose_task["calib_dir"] / "cameras.json"
    calibration = json.loads(calibration_path.read_text())
    for camera in calibration["solved"]["cameras"].values():
        camera["reproj_error_px"]["mean"] = calibration_error
    write_json(calibration_path, calibration)

    rtmlib = types.ModuleType("rtmlib")
    rtmlib.draw_skeleton = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "rtmlib", rtmlib)
    from scripts import run_v2_testset as runner
    from src.action import pipeline
    from scripts import build_group_dashboard, extract_action_skeletons_3d

    root = tmp_path / "real-product-task"
    data = root / "data"
    monkeypatch.setattr(runner, "data_path", lambda *parts: data.joinpath(*parts))
    # Config has module-level DATA; cover modules already imported in the test process.
    import src.config as config
    monkeypatch.setattr(config, "DATA", data)
    monkeypatch.setattr(runner, "create_session", lambda *a, **k: pose_task["session_id"])
    for name in ("init_db", "register_student", "grant_consent", "run_ball_tracking_on_video", "run_shot_outcome_session"):
        monkeypatch.setattr(runner, name, lambda *a, **kw: None)
    monkeypatch.setattr(runner, "_copy_gallery", lambda *a: ["stu_A"])
    monkeypatch.setattr(runner, "run_enroll_group", lambda *a, **kw: {"student_ids": ["stu_A"], "session_id": "enrollment"})
    monkeypatch.setattr(pipeline, "run_action_session_auto", lambda *a: 1)
    monkeypatch.setattr(runner, "remux_to_mp4", lambda src, dst: (shutil.copy2(src, dst), dst)[1])

    def existing_perception(session_id, cam, path, **kw):
        dst = data / "sessions" / session_id / "perception" / cam / "pose2d.json"
        doc = json.loads(pose_task["pose_paths"][cam].read_text())
        doc["source_video"] = str(path.resolve())
        write_json(dst, doc)
        shutil.copy2(pose_task["pose_paths"][cam].with_name("detections.jsonl"), dst.with_name("detections.jsonl"))

    monkeypatch.setattr(runner, "run_single_camera_perception", existing_perception)
    # A conflicting alignment result must not replace the explicitly supplied task sync.
    def alignment(session_id, *a, **kw):
        path = data / "sessions" / session_id / "sync" / "alignment.json"
        write_json(path, {"camera_time_offsets_ms": dict.fromkeys(pose_task["videos"], 0)})
        return path

    monkeypatch.setattr(runner, "run_temporal_alignment", alignment)
    motion = json.loads((pose_task["group_dir"] / "motion.json").read_text())
    monkeypatch.setattr(runner, "write_session_output", lambda sid, path, **kw: (write_json(path, motion), motion)[1])
    monkeypatch.setattr(runner, "build_group_report", lambda *a: {"clips": motion["clips"], "clip_count": 1,
                                                               "shot_stats": {}, "record_count": 3})
    monkeypatch.setattr(build_group_dashboard, "build_dashboard", lambda *a: None)
    monkeypatch.setattr(extract_action_skeletons_3d, "write_viewer", lambda *a: None)

    def render(group, *args, **kw):
        (group / "viz").mkdir(exist_ok=True)
        (group / "viz" / "phases.mp4").write_bytes(b"phases")
        return {}

    monkeypatch.setattr(runner, "render_group_visualizations", render)
    cam4 = tmp_path / "cam4.mp4"
    cam4.write_bytes(b"ball-only-video")
    manifest = {cam: str(path) for cam, path in pose_task["videos"].items()}
    manifest.update(cam_04=str(cam4), enrollment_video=str(cam4), sync=str(pose_task["sync_path"]),
                    calibration=str(pose_task["calib_dir"]))
    manifest_path = root / "input_manifest.json"
    write_json(manifest_path, manifest)
    product_runner.run_product_task(root, manifest_path, "full", tmp_path / "models")
    shutil.rmtree(root / "engine-output")
    shutil.rmtree(root / "data")
    artifact = json.loads((root / "output" / "analyst_pose.json").read_text())
    assert artifact["available"] is expected_available
    if expected_available:
        assert [e["time_ms"] for e in artifact["events"]] == [1000., 1100., 1200.]
    else:
        assert artifact["reason"] == "calibration_unverified"
        assert artifact["events"] == []
    final_report = json.loads((root / "output" / "report.json").read_text())
    assert final_report["clips"] == motion["clips"]
    assert final_report["clip_count"] == 1
    assert json.loads((root / "output" / "motion.json").read_text()) == motion
    assert json.loads((root / "output" / "summary.json").read_text())["session_id"] == pose_task["session_id"]
    assert set(json.loads((root / "output" / "media_manifest.json").read_text())) == {
        "cam_01", "cam_02", "cam_03", "cam_04", "phases",
    }


def test_explicit_task_sync_never_merges_shared_offsets(pose_task, tmp_path, monkeypatch):
    from src.cameras import temporal
    from src.identity import cross_cam_spatial, track_id_smooth
    from src.cameras import event_sync

    def forbidden(*a, **kw):
        pytest.fail("Task sync must not use event re-estimation or shared dataset offsets")

    monkeypatch.setattr(temporal, "_merge_offsets", forbidden)
    monkeypatch.setattr(event_sync, "estimate_camera_offsets", forbidden)
    monkeypatch.setattr(temporal, "build_per_camera_timelines", lambda *a: {})
    monkeypatch.setattr(temporal, "data_path", lambda *parts: tmp_path.joinpath(*parts))
    monkeypatch.setattr(cross_cam_spatial, "repair_cross_camera_identities", lambda *a: {})
    monkeypatch.setattr(track_id_smooth, "smooth_session_identities", lambda *a, **kw: {})
    path = temporal.run_temporal_alignment("current", ["cam_01", "cam_02", "cam_03"],
                                           task_offsets_ms={"cam_01": 123, "cam_03": 700})
    alignment = json.loads(path.read_text())
    assert alignment["camera_time_offsets_ms"] == {"cam_01": 123, "cam_03": 700}
    assert alignment["align_method"] == "task_sync"


def test_calibration_can_only_be_discovered_relative_to_matching_task_sources(pose_task, tmp_path):
    from src.pose import analyst_pose
    import shutil

    dataset = tmp_path / "bundle" / "data" / "uploaded-court"
    dataset.mkdir(parents=True)
    videos = {}
    for cam, source in pose_task["videos"].items():
        videos[cam] = dataset / source.name
        shutil.copy2(source, videos[cam])
    expected = dataset.parent / "calibration" / "existing" / "cameras.json"
    expected.parent.mkdir(parents=True)
    shutil.copy2(pose_task["calib_dir"] / "cameras.json", expected)
    assert analyst_pose.find_task_calibration(videos) == expected.resolve()
    for path in videos.values():
        path.write_bytes(b"another-upload-on-another-court")
    assert analyst_pose.find_task_calibration(videos) is None


def test_legacy_calibration_declaration_requires_exact_source_bytes(pose_task):
    path = pose_task["calib_dir"] / "cameras.json"
    doc = json.loads(path.read_text())
    doc["annotations"].pop("source_video_sha256")
    doc["annotations"]["source_videos"] = {cam: str(path) for cam, path in pose_task["videos"].items()}
    write_json(path, doc)
    assert run_pose(pose_task)[0]["available"] is True


def test_calibration_must_load_the_same_bundle_whose_source_is_verified(pose_task):
    # A caller must not verify one JSON while the loader reads sibling cameras.json.
    directory = pose_task["calib_dir"]
    decoy = directory / "other.json"
    decoy.write_text((directory / "cameras.json").read_text())
    wrong = json.loads((directory / "cameras.json").read_text())
    for cam in wrong["solved"]["cameras"].values():
        cam["tvec"][0] += 30
    write_json(directory / "cameras.json", wrong)
    pose_task["calib_dir"] = decoy
    assert run_pose(pose_task)[0]["provenance"]["calibration_verified"] is False


def test_identity_repair_cannot_assign_analyst_to_wrong_person(pose_task):
    for path in pose_task["pose_paths"].values():
        doc = json.loads(path.read_text())
        for fr in doc["frames"]:
            fr["persons"][1].update(student_id="stu_B", identity_confidence="sticky", identity_smooth="solo_consensus")
        write_json(path, doc)
    artifact, _ = run_pose(pose_task)
    assert artifact["available"] is True
    assert all(e["student_id"] == "stu_A" for e in artifact["events"])


def test_simultaneous_clips_keep_separate_players_and_angles(pose_task):
    motion_path = pose_task["group_dir"] / "motion.json"
    motion = json.loads(motion_path.read_text())
    motion["clips"].append({**motion["clips"][0], "clip_id": "clip_B", "student_id": "stu_B"})
    write_json(motion_path, motion)
    for path in pose_task["pose_paths"].values():
        doc = json.loads(path.read_text())
        for fr in doc["frames"]:
            k = np.array(fr["persons"][1]["keypoints"])
            k[9, :2] = 2 * k[7, :2] - k[5, :2]
            k[10, :2] = 2 * k[8, :2] - k[6, :2]
            fr["persons"][0]["keypoints"] = k.tolist()
        write_json(path, doc)
    artifact, _ = run_pose(pose_task)
    assert len(artifact["events"]) == 6
    for event in artifact["events"]:
        elbow = 90 if event["student_id"] == "stu_A" else 180
        assert event["angles"]["left_elbow"] == pytest.approx(elbow, abs=.001)


def test_missing_optional_camera_preserves_two_reliable_views(pose_task):
    pose_task["pose_paths"]["cam_02"].unlink()
    artifact, _ = run_pose(pose_task)
    assert artifact["available"] is True
    assert all(e["camera_count"] == 2 for e in artifact["events"])


def test_pose_timestamps_must_match_actual_frame_clock(pose_task):
    for path in pose_task["pose_paths"].values():
        doc = json.loads(path.read_text())
        for fr in doc["frames"]:
            fr["timestamp_ms"] += 1
        write_json(path, doc)
    assert run_pose(pose_task)[0]["available"] is False


def test_pairwise_camera_time_gap_is_bounded(pose_task):
    # Both views are near the anchor but 70ms apart from one another.
    sync = json.loads(pose_task["sync_path"].read_text())
    sync["camera_time_offsets_ms"]["cam_01"] += 35
    sync["camera_time_offsets_ms"]["cam_02"] -= 35
    write_json(pose_task["sync_path"], sync)
    artifact, _ = run_pose(pose_task)
    assert artifact["available"] is False


def test_phases_mosaic_maps_cam03_local_to_other_cameras(tmp_path, monkeypatch):
    import types
    rtmlib = types.ModuleType("rtmlib")
    rtmlib.draw_skeleton = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "rtmlib", rtmlib)
    from scripts import run_v1_testset as runner

    output = []

    class Capture:
        def __init__(self):
            self.index = -1

        def isOpened(self):
            return True

        def get(self, key):
            return {cv2.CAP_PROP_FPS: 10., cv2.CAP_PROP_FRAME_COUNT: 10}.get(key, 0)

        def read(self):
            self.index += 1
            return True, np.full((30, 30, 3), self.index + 1, dtype=np.uint8)

        def release(self):
            pass

    from types import SimpleNamespace
    monkeypatch.setattr(runner.cv2, "VideoCapture", lambda *a: Capture())
    monkeypatch.setattr(runner, "create_video_writer", lambda *a: (SimpleNamespace(write=lambda f: output.append(f.copy()),
                                                                                 release=lambda: None), "fake"))
    for name in ("putText", "line"):
        monkeypatch.setattr(runner.cv2, name, lambda *a, **kw: None)
    videos = {f"cam_0{i}": tmp_path / f"cam{i}.mp4" for i in range(1, 5)}
    for path in videos.values():
        path.touch()
    runner._compose_phases_quad(tmp_path / "phases.mp4", videos, stride=1, cell_size=(30, 30),
                                camera_offsets_ms={"cam_01": 0, "cam_02": 500, "cam_03": 200, "cam_04": 200})
    # cam03 local=200ms -> common=0; cam01=0, cam02=500, cam03/cam04=200.
    assert [int(output[2][y, x, 0]) for y, x in ((15, 15), (15, 45), (45, 15), (45, 45))] == [1, 6, 3, 3]
    # Negative local time has no source frame, and must not hold the first frame.
    assert output[0][15, 15, 0] == 0
    # cam02 runs out before anchor does; never hold the last frame as contemporaneous.
    assert output[-1][15, 45, 0] == 0
