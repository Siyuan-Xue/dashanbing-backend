"""Shared draft/upload validation. Execution consumes a task-local immutable snapshot."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from app.sync_schemas import CAMERAS, SyncInput


def sync_error(code: str, message: str, status: int = 422, **fields) -> HTTPException:
    return HTTPException(status_code=status, detail={'code': code, 'message': message, **fields})


def source_versions(items) -> dict[str, str]:
    versions = {}
    for item in items:
        if item.slot not in CAMERAS or item.validation_state != 'valid':
            continue
        try:
            stat = Path(item.path).stat()
        except OSError:
            continue
        # Upload operation catches byte-identical replacements; stat detects changes outside API.
        identity = [item.upload_operation_id, str(item.updated_at), stat.st_size, stat.st_mtime_ns, stat.st_ino]
        versions[item.slot] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32]
    return versions


def read_sync_config(task) -> dict | None:
    try:
        value = json.loads(task.sync_config_json or 'null')
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get('schema_version') == 1 else None


def sync_status(task, items) -> str:
    config = read_sync_config(task)
    # Submitted snapshots keep their meaning after input retention/deletion.
    if task.submitted_at is not None and task.status not in {'draft', 'uploading'}:
        return 'confirmed' if config else 'legacy'
    if config is None:
        return 'unconfirmed'
    current = source_versions(items)
    return 'confirmed' if len(current) == 4 and config.get('input_versions') == current else 'stale'


def camera_paths(items) -> dict[str, Path]:
    paths = {item.slot: Path(item.path) for item in items
             if item.slot in CAMERAS and item.validation_state == 'valid' and Path(item.path).is_file()}
    missing = sorted(set(CAMERAS) - set(paths))
    if missing:
        raise sync_error('input_missing', 'Upload all four camera videos first.', cameras=missing)
    return paths


def validate_sync(payload, versions: dict, durations: dict, *, bind_uploaded_versions=False) -> dict:
    try:
        value = payload if isinstance(payload, SyncInput) else SyncInput.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        raise sync_error('sync_invalid', 'Supply exactly four finite timestamps or offsets, not both.') from None
    if set(versions) != set(CAMERAS):
        raise sync_error('input_missing', 'All four camera versions are required.')
    if value.input_versions is None and not bind_uploaded_versions:
        raise sync_error('sync_invalid', 'Current input versions are required.')
    if value.input_versions is not None and value.input_versions != versions:
        raise sync_error('sync_stale', 'Camera inputs changed. Refresh previews and confirm synchronization again.', 409)
    if set(durations) != set(CAMERAS) or any(not math.isfinite(x) or x <= 0 for x in durations.values()):
        raise sync_error('sync_invalid', 'Camera durations must be finite and positive.')
    selected = value.selected_timestamps_ms
    if selected is not None:
        if any(t < 0 or t >= durations[camera] for camera, t in selected.items()):
            raise sync_error('sync_invalid', 'Selected timestamps must be within each camera video.')
        offsets = {camera: t - selected['cam_03'] for camera, t in selected.items()}
    else:
        offsets = value.offsets_ms
        if offsets['cam_03'] != 0:
            raise sync_error('sync_invalid', 'cam_03 must have zero offset.')
    start = max(-offsets[camera] for camera in CAMERAS)
    end = min(durations[camera] - offsets[camera] for camera in CAMERAS)
    if not math.isfinite(start) or not math.isfinite(end) or start >= end:
        raise sync_error('sync_no_overlap', 'Camera offsets must leave a positive common time interval.')
    return {'schema_version': 1, 'anchor_camera': 'cam_03', 'camera_time_offsets_ms': offsets,
            'selected_timestamps_ms': selected, 'input_versions': dict(versions), 'durations_ms': durations,
            'overlap_start_ms': start, 'overlap_end_ms': end,
            'confirmed_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}


def confirm_sync(task, items, payload, *, bind_uploaded_versions=False) -> dict:
    from app.services.input_preview import inspect_video
    paths = camera_paths(items)
    before = source_versions(items)
    durations = {camera: inspect_video(path)['duration_ms'] for camera, path in paths.items()}
    if before != source_versions(items):
        raise sync_error('sync_stale', 'Camera inputs changed while checking synchronization.', 409)
    config = validate_sync(payload, before, durations, bind_uploaded_versions=bind_uploaded_versions)
    task.sync_config_json = json.dumps(config, allow_nan=False)
    return config


def require_submission_config(task, items) -> dict:
    if task.enrollment_mode not in {'sequential', 'lineup'} or type(task.expected_persons) is not int or not 1 <= task.expected_persons <= 6:
        raise sync_error('registration_config_required', 'Select an enrollment method and an expected person count from 1 to 6.')
    config = read_sync_config(task)
    if config is None or config.get('input_versions') != source_versions(items):
        from app.services.prepared_demo_sync import prepared_demo_config
        automatic = prepared_demo_config(items)
        if automatic is not None:
            config = automatic
            task.sync_config_json = json.dumps(config, allow_nan=False)
    if config is None:
        raise sync_error('sync_config_required', 'Confirm camera synchronization before submission.')
    # Always compare live versions for new submission, even after a correction of a failed task.
    if config.get('input_versions') != source_versions(items) or len(config.get('input_versions', {})) != 4:
        raise sync_error('sync_stale', 'Camera inputs changed. Confirm synchronization again.', 409)
    return validate_sync({'input_versions': config['input_versions'], 'offsets_ms': config['camera_time_offsets_ms']},
                         source_versions(items), config['durations_ms']) | {'confirmed_at': config['confirmed_at'],
                                                                         'selected_timestamps_ms': config.get('selected_timestamps_ms')}


def registration_manifest(task) -> dict:
    return {'enrollment_mode': task.enrollment_mode, 'expected_persons': task.expected_persons}


def preserve_execution_config(task, manifest: dict) -> dict:
    """valid_manifest checks files; preserve the original non-file execution settings too."""
    original = json.loads(task.input_manifest_json)
    for key in ('enrollment_mode', 'expected_persons', 'sync_schema_version', 'calibration'):
        if key in original:
            manifest[key] = original[key]
    return manifest


def prepare_preset_config(task, items, manifest, storage) -> dict:
    """Normalize this preset group's verified offsets through the upload validator."""
    try:
        source = json.loads(Path(manifest['sync']).read_text(encoding='utf-8'))
        if source.get('anchor_camera') != 'cam_03':
            raise ValueError('Invalid anchor')
        payload = {'offsets_ms': source['camera_time_offsets_ms']}
    except (OSError, ValueError, KeyError, TypeError):
        raise sync_error('sync_invalid', 'Preset synchronization is unavailable or invalid.') from None
    confirm_sync(task, items, payload, bind_uploaded_versions=True)
    config = require_submission_config(task, items)
    completed = storage.prepare_preset(task.id, manifest | registration_manifest(task), sync_config=config)
    task.input_manifest_json = json.dumps(completed, ensure_ascii=False)
    return completed
