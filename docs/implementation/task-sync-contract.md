# Task synchronization and registration contract

All URLs below have `/api/v1` prefix. Existing authenticated business-user ownership applies; another owner's task returns 404. Register `app.api.routes.task_sync.router` in `app/api/router.py` with `api_router.include_router(task_sync.router)`. No startup hook is required: preview work is lazy and disk state is recoverable after restart.

## Task configuration

TaskCreate: `enrollment_mode: "sequential" | "lineup"` defaults to sequential; `expected_persons: integer | null` (1–6) may be absent in a draft. TaskUpdate accepts these same fields. Registration changes do not invalidate camera synchronization. Public serialization should call `app.services.task_sync.sync_status(task, task_inputs(task.id, session))`, returning `unconfirmed | confirmed | stale | legacy`. Legacy means already submitted without a versioned sync configuration, not a draft.

New submission requires all five valid files, an explicit person count, and confirmed current synchronization. 422 = missing/invalid configuration; 409 = stale versions or state conflict. Retries execute the original snapshot; previously submitted historical tasks are not retroactively required to confirm sync. `POST /tasks/{id}/return-to-input` allows failed/interrupted registration correction, preserves input files, clears submission/error state, and rejects completed tasks or tasks with a completed report.

## Preview preparation

`POST /tasks/{id}/sync/preview` has no body; returns 202 and a PreviewStatus object. `GET /tasks/{id}/sync/preview` returns the same object (200). POST is idempotent for an in-progress or ready source version; explicitly retries failed or interrupted versions. Poll GET while preparing. One CPU conversion job runs at a time; overload returns 503 `preview_busy`.

PreviewStatus:
```json
{"status":"unprepared","source_versions":{"cam_01":"opaque","cam_02":"opaque","cam_03":"opaque","cam_04":"opaque"},"cameras":{},"error":null}
```
Status is `unprepared | preparing | ready | failed`. Ready `cameras` maps each camera to `{source_version, duration_ms, fps, frame_count, source_start_pts_ms, frame_timestamps_ms, video_url}`. Frame timestamps are measured presentation times relative to the first source video frame, not inferred from 30 fps. Preview seconds map directly to these local milliseconds (no time stretching, trimming, or frame-rate conversion). Different constant frame rates across cameras are supported. Variable frame rates, timestamp gaps, and midstream timeline edits are rejected in v1. A physically edited constant-frame-rate source cannot be detected automatically and is outside the supported capture contract.

`GET /tasks/{id}/sync/preview/{camera}?source_version=...` serves browser MP4 with HTTP Range support. `source_version` is optional; if supplied it must match. `GET /tasks/{id}/sync/frames/{camera}?time_ms=1234&source_version=...` returns `{camera, source_version, requested_time_ms, actual_time_ms, source_pts_ms, frame_index, image_data_url}`. The image is JPEG at the nearest measured frame (ties choose the earlier frame). Use actual_time_ms when confirming a selected frame. Seeking outside `[0,duration_ms)` is 422. Not-ready media is 409; missing camera inputs are 422. All FFmpeg/FFprobe work executes outside the event loop, with one conversion process/thread at a time and bounded jobs/cache.

## Synchronization

`GET /tasks/{id}/sync` returns `{status, source_versions, config}`. Config is null before confirmation. `PUT /tasks/{id}/sync` is draft-only and accepts:
```json
{"input_versions":{"cam_01":"opaque","cam_02":"opaque","cam_03":"opaque","cam_04":"opaque"},"selected_timestamps_ms":{"cam_01":1000,"cam_02":1100,"cam_03":900,"cam_04":950}}
```
Alternatively replace `selected_timestamps_ms` with `offsets_ms` containing all four cameras. Exactly one representation is required; all numbers must be finite. `cam_03` is the anchor: selected times produce offsets `{cam_01:100,cam_02:200,cam_03:0,cam_04:50}`. Offsets use `common_ms = local_ms - offset_ms`; supplied cam_03 offset must be zero. Validate selected timestamps against actual durations; offsets must leave a positive common overlap across all cameras. GET/PUT config contains `schema_version:1`, `anchor_camera:"cam_03"`, `camera_time_offsets_ms`, `selected_timestamps_ms` (or null), `input_versions`, `durations_ms`, `overlap_start_ms`, `overlap_end_ms`, and `confirmed_at`.

Camera upload replacement makes sync stale, including same-byte reuploads; registration-video replacement does not. Fetch new preview versions and confirm again. Execution snapshots live at task-local `input/sync.json`; manifests include `enrollment_mode`, `expected_persons`, `sync_schema_version:1`, and `sync` pointing at that snapshot. Global server sync settings are never copied into new uploads.

`POST /analyses/upload` is one multipart request: existing title/mode/five videos plus required `enrollment_mode`, `expected_persons`, `analyst_locale` (`zh|en`), and `sync` (JSON string in the same PUT shape). For this single-request upload omit `input_versions`: the server binds confirmation to the just-uploaded files. If versions are supplied they are checked. It uses the same validation and snapshot functions as draft submission.

Errors use `detail: {code, message, ...}` with safe identifiers, never server paths. Codes include `registration_config_required`, `sync_config_required`, `sync_invalid`, `sync_stale`, `sync_no_overlap`, `input_missing`, `preview_not_ready`, `preview_busy`, `preview_failed`, `unsupported_timeline`, `task_state_conflict`, and `registration_correction_unavailable`.

## Implementation sequence and scoped verification

1. Test sync validation, version invalidation, draft submit/upload parity and immutable snapshot behavior; implement shared schemas/service/persistence and routes.
2. Test synthetic-media frame PTS, Range serving, source-version/restart/cache behavior; implement bounded background preview service.
3. Test count overflow/mismatch and actual gallery sample quality; implement explicit enrollment dispatch and runner manifest use, verify preset source metadata.
4. Run the scoped tests and record exact commands/results. No deployment, commits, real input/model processing, production data, or final acceptance/optimization loops.

## Scoped implementation handoff — 2026-09-07

Implementation is complete in `codex/ai-analyst`. Parent router registration and TaskPublic serialization are present. Analysis upload/preset responses return persisted `enrollment_mode`, `expected_persons`, and `analyst_locale` through AnalysisPublic. No stored sync-status column is introduced.

Research registration rejects excess/insufficient counts, invalid count/mode, empty or invalid persisted face/body samples, and mismatched gallery identities before processing cameras. New manifests carry explicit registration settings; already-submitted legacy manifests retain the old sequential/unknown-count entry path and still require a usable 1–6-person gallery. Both the product runner and the standalone action-group helper check persisted gallery samples. The small companion `run_v3_testset.py` change passes `--enroll-mode lineup` explicitly. Its tracked four-person lineup defaults are the source for preset registration configuration.

Registration failures emit `PRODUCT_ERROR` with `{code,message,...}` and write `logs/registration_error.json`. The existing worker currently presents its generic safe `ENGINE_FAILED` response; mapping this diagnostic to a specialized public error code would belong to the worker owner. Return-to-input works for failed/interrupted tasks without a report or pending cleanup, so the generic worker code does not prevent correction.

Preview limits: one background CPU conversion job, up to eight pending/running jobs, at most two cached versions per task and 64 versions / 2 GiB globally; each camera conversion has a byte limit and a 600-second timeout. FFprobe reads a bounded number of frames (maximum supported source timeline 216000 frames, 240 fps). Failed/interrupted versions can be explicitly prepared again. Conversion checks actual output frame PTS against source PTS; JPEG lookup selects the measured source frame index. The browser sees normalized local time; source PTS origin is retained in metadata. V1 supports constant-rate, unedited capture timelines only.

Owned files changed:

- `app/sync_schemas.py`
- `app/services/task_sync.py`
- `app/services/input_preview.py`
- `app/api/routes/task_sync.py`
- `app/api/routes/tasks.py`
- `app/api/routes/analyses.py`
- `app/services/storage.py`
- `app/services/presets.py`
- `app/services/readiness.py`
- `research_engine/product_runner.py`
- `research_engine/src/identity/enrollment_validation.py`
- `research_engine/src/identity/sequential_enroll.py`
- `research_engine/src/identity/lineup_enroll.py`
- `research_engine/scripts/run_v2_testset.py`
- `research_engine/scripts/run_v3_testset.py` (required explicit-lineup companion default)
- `migrations/versions/20260907_0013_task_sync.py`
- `tests/test_task_sync.py`
- `tests/test_input_preview.py`
- `tests/test_enrollment_validation.py`
- `docs/implementation/task-sync-contract.md`

Commands run from `/Users/milesxue/Documents/ChatGPT/dashanbing-backend/.worktrees/ai-analyst`:

```sh
.venv/bin/python -m pytest tests/test_task_sync.py tests/test_input_preview.py tests/test_enrollment_validation.py tests/test_storage.py tests/test_product_runner.py -q --tb=short
```

Result: **51 passed in 2.59s**, exit 0, no skips. Real synthetic-media preview tests used `/opt/homebrew/bin/ffmpeg` and `/opt/homebrew/bin/ffprobe` (installed during this work). Earlier tests had two environment skips before those tools became available; the final scoped run includes their execution. Tests exercise 20/25/30/35-fps clips, source PTS metadata, frame lookup, actual conversion, restart recovery, failed versions, queue/cache limits, Range responses, ownership, registration failures, immutable retry configuration, per-preset sync snapshots, and legacy retry compatibility. Research GPU inference is not claimed: detectors/embedders are isolated where needed to test rejection before inference.

An inline Python migration check disabled `.env` loading, cleared inherited service settings, selected a new temporary SQLite database, then executed these Alembic commands:

```python
command.upgrade(Config('alembic.ini'), '20260907_0012')
# Insert one synthetic business user and one historical completed analysis.
command.upgrade(Config('alembic.ini'), '20260907_0013')
# Assert (enrollment_mode, expected_persons, sync_config_json, status,
#         input_manifest_json) == ('sequential', None, None, 'completed', '{}').
command.downgrade(Config('alembic.ini'), '20260907_0012')
# Assert the historical status and manifest remain ('completed', '{}').
```

Result: `PASS: isolated 0012 -> 0013 -> 0012; historical completed row preserved`, exit 0. The temporary database was disposed and deleted.

`git diff --check -- <owned paths>` passed with no whitespace errors. No commits, pushes, deployments, production input processing, or final acceptance/optimization loops were performed. Existing older task/preset/readiness tests that expect global sync injection or a manifest containing only file paths need adaptation by their owners to the intentionally changed contract; they were not included in this scoped verification.
