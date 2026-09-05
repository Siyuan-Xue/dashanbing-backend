# Analyst pose artifact, version 1

The approved analyst pipeline runs in the existing product task. It consumes that
task's source videos, remuxed videos, per-camera `pose2d.json`, original
`detections.jsonl`, motion clips, and explicit task sync. It does not run additional
pose inference, sample new video frames, solve calibration, or train models.

`process_action_group` calls `process_group_action_skeletons` with explicit session,
videos, source videos, pose paths, sync path, and calibration. The latter always
writes `group_XX/analyst_pose.json`. `_copy_product_outputs` copies it to
`<task_root>/output/analyst_pose.json` before temporary task data is retained/deleted.
A failed/missing pose export produces an unavailable artifact; report, summary,
motion, original camera review videos, and phases continue to work.

## Contract

```json
{
  "schema_version": 1,
  "available": true,
  "reason": "ok",
  "events": [
    {
      "clip_id": "stu_A:0",
      "student_id": "stu_A",
      "time_ms": 1000.0,
      "angles": {
        "left_elbow": 90.0,
        "right_elbow": 90.0,
        "left_knee": 180.0,
        "right_knee": 180.0
      },
      "camera_count": 2,
      "reprojection_error_px": 0.5
    }
  ],
  "camera_offsets_ms": {"cam_01": -300.0, "cam_02": 200.0, "cam_03": 700.0},
  "time_basis": "common",
  "provenance": {}
}
```

The example is illustrative, not measured task data. All event values are finite;
angles are degrees in `[0,180]`. Each event is one existing anchor pose frame for
one exact `(clip_id, student_id)`. `camera_count` counts complete views supporting
all twelve measured joints of the four angles; each such view passes the same
quality gates. Reprojection error is the mean observed pixel residual over those
joints/views, before any smoothing or grounding. Every residual also passes the
maximum threshold. No pseudo-3D, virtual wrist angles, inferred joint values,
cross-person smoothing, or 2D fallback enters this artifact.

`available` is true only if at least one reliable event exists. Partial coverage
omits rejected events and records counts under `provenance.rejected`.
Unavailable exports contain `available:false`, a nonempty `reason`, `events:[]`,
and empty reference ranges. Reasons include `missing_task_context`,
`session_mismatch`, `calibration_unverified`, `insufficient_matching_pose_views`,
`no_reliable_pose_events`, `invalid_pose_evidence`, and `pose_export_missing`.

`provenance` has these fields:

| Field | Meaning |
| --- | --- |
| `verified` | Boolean; true only with validated events. |
| `calibration_verified` | Boolean; at least two valid cameras match actual source bytes. |
| `identity_verified` | Boolean; true only with exported identity-validated events. |
| `session_id` | Current research session, never inferred from a group number. |
| `pose_source` | `calibrated_multiview_triangulation`. |
| `identity_method` | `raw_detection_track_and_high_confidence_student_id`. |
| `sampling` / `smoothing` | `existing_anchor_pose_frames_only` / `none`. |
| `offset_convention` | `common_ms = local_ms - offset_ms`. |
| `videos` | Camera → original source `path` and `sha256`. |
| `pose_files` | Camera → pose `path`, `sha256`, prepared `video_path`, `fps`, and `detections_sha256`. |
| `sync` | Exact supplied sync `path`, `sha256`, `source`. |
| `calibration` | Bundle `path`, `sha256`, `verified`, `source_match:"sha256"`, and per-camera verification details. |
| `samples` | Event keys/time plus `anchor_camera`, per-camera `track_ids`, `frames`, `local_times_ms`. |
| `quality_thresholds` | Gates listed below. |
| `reference_ranges` | Applicable action YAML elbow/knee ranges for clips with accepted evidence; each records clip/action/phase/joint/min/max/unit/source. No score is inferred. |
| `rejected` | Reason → rejected candidate count. |
| `error_type` | Present on malformed/missing evidence; exception class only. |

Local provenance paths are for auditing; consumers should whitelist measurements
and identifiers when constructing model requests.

## Clock and identity

Task sync uses `{camera_time_offsets_ms:{camera_id:number}, ...}` with finite signed
millisecond offsets. `common = local - offset`; `local = common + offset`.
Report clips and phases remain on `clip.anchor_camera`'s local clock (normally
cam03). Analyst events and triangulated scene frames are on common time. To join
a clip, subtract its anchor offset from the clip interval/release; to seek a
camera, add that camera's offset to the common event time. The phases mosaic
retains its anchor-local playback clock and maps other tiles through common time.
Unavailable pose does not invalidate separately supplied task sync for seeking.

Per-camera exports record the actual prepared `source_video` and `image_size`.
The analyst checks source path, session ID, camera ID, resolution, positive FPS,
and frame/timestamp agreement within 0.5ms. It joins poses to original detections
by exact frame and track ID; spatial/solo/majority rewritten IDs are not evidence.
Only high-confidence original identity matches qualify, with at least two track
observations, no competing student IDs on a track, no duplicate assignment in a
frame, and one continuous track per camera/clip. It never picks by bounding-box
size/order, assumes an unlabeled person is the student, or transfers a broken track.

## Calibration and quality

An optional product manifest `calibration` points to an existing `cameras.json`
bundle or its directory. Otherwise the runner searches only `calibration/*/cameras.json`
beside the actual source-video dataset. Discovery must yield one unambiguous
matching bundle. There are no global test-data or reference defaults.

The existing solved bundle format is retained. Source verification uses
`annotations.source_video_sha256:{camera_id:sha256}` when already recorded, or
hashes files explicitly declared by `annotations.source_videos`. The latter can
be a camera/path map or the existing brace-list form such as
`data/test_data_v3/1-{1,2,3}.mkv`. Exact source bytes must match. A dataset name,
matching camera names, `shared_across_groups:true`, or the temporary `group_01`
name provides no verification. No new binding/annotation is manufactured.

Gates require at least two views, keypoint confidence ≥0.5 for every required
joint, finite proper calibration matrices and matching dimensions, calibration
mean residual ≤8px, each pose residual ≤8px, positive depth, triangulation ray
angle ≥2°, broad limb-length checks, and anchor/pairwise time deltas ≤40ms.
The 8px limits are conservative engineering gates, not an accuracy certification.
Missing/poor old calibration or identity yields unavailable results; existing
sample courts are not automatically endorsed as reliable 3D.

These are two distinct measurements. `max_calibration_error_px=8` limits each
camera's mean error projecting its annotated **court landmarks**, taken from
`solved.cameras[cam].reproj_error_px.mean`. `max_reprojection_error_px=8` limits
**every required skeleton joint/view residual** after triangulation. The event's
`reprojection_error_px` then reports the mean of those accepted pose residuals;
it does not report calibration error.

The previous `triangulate_clip_sequence(max_reproj_px=90)` rejected frames using
the **mean skeleton reprojection error** across available joints/views. It did
not apply an 8px gate to calibration landmark error, and an average could hide
individual poor joints. This change is a deliberate conservative policy for
analyst measurements, not a like-for-like replacement of a 90px calibration
threshold. Neither cutoff has been established as an angle-accuracy guarantee.

The bundled v3 calibration currently reports court-landmark means of 52.31px
(cam01), 29.95px (cam02), and 51.99px (cam03). All three fail the new calibration
gate, so that bundle cannot produce available analyst pose even if source and
identity checks otherwise pass. This is an accepted quality limit; source video,
action/shot results, and review media continue to work without analyst pose or
a GLM API key. Changing either threshold requires separate measurement evidence;
passing the old 90px pose-average check does not validate those calibration means.

## Verification

Run from the shared worktree:

```sh
.venv/bin/python -m pytest tests/test_analyst_pose.py tests/test_product_runner.py -q
```

Tests cover the actual product → v2 runner → pose exporter → product copy chain,
retention, known-angle multiview projections, identity ambiguity/switches/repairs,
simultaneous players, source/calibration mismatches, missing views, invalid poses,
signed/nonzero-anchor sync, pairwise timing, and mosaic clock/coverage. GPU, DB,
and video rendering boundaries use test doubles; geometric reconstruction and
artifact handling execute production code.
