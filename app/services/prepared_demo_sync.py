"""Recognize the four pre-aligned upload packs by exact per-camera content."""
import hashlib
import json
from pathlib import Path

from app.services.task_sync import source_versions, sync_error, validate_sync
from app.sync_schemas import CAMERAS

DEMOS = json.loads(Path(__file__).with_name('prepared_demos.json').read_text())


def prepared_demo_config(items):
    paths = {item.slot: Path(item.path) for item in items
             if item.slot in CAMERAS and item.validation_state == 'valid'}
    if set(paths) != set(CAMERAS):
        return None
    versions = source_versions(items)
    try:
        sizes = {camera: path.stat().st_size for camera, path in paths.items()}
        candidates = [demo for demo in DEMOS if all(
            demo['cameras'][camera]['size'] == sizes[camera] for camera in CAMERAS)]
        if not candidates:
            return None
        digests = {}
        for camera, path in paths.items():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            digests[camera] = digest.hexdigest()
    except OSError:
        return None
    if versions != source_versions(items):
        raise sync_error('sync_stale', 'Camera inputs changed during demo recognition.', 409)
    for demo in candidates:
        if all(demo['cameras'][camera]['sha256'] == digests[camera] for camera in CAMERAS):
            # These exact files were cropped with the original offsets, then rebased to zero.
            return validate_sync({'offsets_ms': dict.fromkeys(CAMERAS, 0)}, versions,
                                 {camera: demo['cameras'][camera]['duration_ms'] for camera in CAMERAS},
                                 bind_uploaded_versions=True)
    return None
