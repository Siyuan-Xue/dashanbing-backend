import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException


def make_video(path: Path, fps=25, seconds=1):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg/FFprobe unavailable')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size=96x64:rate={fps}',
                    '-t', str(seconds), '-c:v', 'libx264', '-threads', '1', '-y', str(path)], check=True)
    return path


def test_measured_frame_timestamps_support_non30fps_and_nearest_frame(tmp_path):
    from app.services.input_preview import inspect_video, nearest_frame
    metadata = inspect_video(make_video(tmp_path / 'source.mp4', fps=25))
    assert metadata['fps'] == pytest.approx(25)
    assert metadata['frame_count'] == 25
    assert metadata['duration_ms'] == pytest.approx(1000, abs=1)
    assert nearest_frame(metadata, 55) == (1, 40.0)
    assert nearest_frame(metadata, 60) == (1, 40.0)
    with pytest.raises(HTTPException):
        nearest_frame(metadata, 1000)


def test_discontinuous_pts_rejected():
    from app.services.input_preview import timeline_metadata
    with pytest.raises(HTTPException) as error:
        timeline_metadata([0, 40, 80, 300, 340], 25)
    assert error.value.detail['code'] == 'unsupported_timeline'


def test_background_preview_actual_frame_and_restart(tmp_path):
    from app.services.input_preview import InputPreviewService
    paths = {camera: make_video(tmp_path / f'{camera}.mp4', fps=20 + i * 5)
             for i, camera in enumerate(('cam_01', 'cam_02', 'cam_03', 'cam_04'))}
    versions = dict.fromkeys(paths, 'v1')
    service = InputPreviewService(tmp_path / 'cache')
    assert service.prepare('task', paths, versions)['status'] == 'preparing'
    service.wait_for_idle(timeout=30)
    ready = service.status('task', versions)
    assert ready['status'] == 'ready', ready
    frame = service.frame('task', 'cam_01', versions, 64)
    assert frame['actual_time_ms'] == 50
    assert frame['image_data_url'].startswith('data:image/jpeg;base64,')
    restarted = InputPreviewService(tmp_path / 'cache')
    assert restarted.status('task', versions)['status'] == 'ready'
    assert restarted.status('task', {**versions, 'cam_01': 'v2'})['status'] == 'unprepared'


def test_restart_marks_orphan_preparation_failed_and_can_retry(tmp_path):
    import json
    from app.services.input_preview import InputPreviewService
    service = InputPreviewService(tmp_path / 'cache')
    paths = {camera: make_video(tmp_path / f'{camera}.mp4') for camera in ('cam_01', 'cam_02', 'cam_03', 'cam_04')}
    versions = dict.fromkeys(paths, 'v1')
    directory = service._directory('task', versions)
    directory.mkdir(parents=True)
    (directory / 'status.json').write_text(json.dumps({'status': 'preparing', 'source_versions': versions,
                                                      'cameras': {}, 'error': None, '_pid': 99999999, '_process': 'old'}))
    assert service.status('task', versions)['error']['code'] == 'preview_interrupted'
    assert service.prepare('task', paths, versions)['status'] == 'preparing'
    service.wait_for_idle(timeout=30)
    assert service.status('task', versions)['status'] == 'ready'


def test_failed_source_version_is_retryable_and_error_never_leaks_paths(tmp_path):
    from app.services.input_preview import InputPreviewService
    service = InputPreviewService(tmp_path / 'cache')
    invalid = tmp_path / 'sensitive-source-name.mp4'
    invalid.write_text('not a video')
    paths = {camera: invalid for camera in ('cam_01', 'cam_02', 'cam_03', 'cam_04')}
    versions = dict.fromkeys(paths, 'bad-version')
    service.prepare('task', paths, versions)
    service.wait_for_idle(timeout=30)
    failure = service.status('task', versions)
    assert failure['status'] == 'failed'
    assert str(tmp_path) not in str(failure)
    assert invalid.name not in str(failure)
    service.prepare('task', paths, versions)
    service.wait_for_idle(timeout=30)
    assert service.status('task', versions)['status'] == 'failed'


def test_preview_queue_is_bounded_and_idempotent(tmp_path, monkeypatch):
    import threading
    from app.services import input_preview as preview
    # Hold the CPU job so queue capacity can be asserted without artificial slow media.
    started = threading.Event()
    release = threading.Event()
    def blocked_probe(_):
        started.set()
        release.wait(10)
        raise RuntimeError('synthetic probe failure')
    monkeypatch.setattr(preview, 'inspect_video', blocked_probe)
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'video')
    service = preview.InputPreviewService(tmp_path / 'cache')
    paths = {camera: source for camera in ('cam_01', 'cam_02', 'cam_03', 'cam_04')}
    versions = dict.fromkeys(paths, 'v1')
    try:
        assert service.prepare('task-0', paths, versions)['status'] == 'preparing'
        assert started.wait(2)
        assert service.prepare('task-0', paths, versions)['status'] == 'preparing'
        for i in range(1, 8):
            service.prepare(f'task-{i}', paths, versions)
        with pytest.raises(HTTPException) as error:
            service.prepare('task-overload', paths, versions)
        assert error.value.status_code == 503
        assert error.value.detail['code'] == 'preview_busy'
    finally:
        release.set()
        service.wait_for_idle(timeout=20)


def test_measured_source_start_pts_preserved():
    from app.services.input_preview import timeline_metadata, nearest_frame
    metadata = timeline_metadata([1200, 1240, 1280], 25)
    assert metadata['source_start_pts_ms'] == 1200
    assert nearest_frame(metadata, 42) == (1, 40)


def test_single_preview_cannot_exceed_cache_budget(tmp_path, monkeypatch):
    from app.services import input_preview as preview
    monkeypatch.setattr(preview, 'MAX_CACHE_BYTES', 64)
    path = make_video(tmp_path / 'source.mp4')
    service = preview.InputPreviewService(tmp_path / 'cache')
    paths = {camera: path for camera in ('cam_01', 'cam_02', 'cam_03', 'cam_04')}
    versions = dict.fromkeys(paths, 'v1')
    service.prepare('task', paths, versions)
    service.wait_for_idle(timeout=30)
    state = service.status('task', versions)
    assert state['status'] == 'failed'
    assert state['error']['code'] == 'preview_cache_limit'
    assert not list(service._directory('task', versions).glob('*.mp4'))


def test_preview_keeps_frames_with_ffmpeg_44_command_options(tmp_path, monkeypatch):
    from app.services import input_preview as preview
    # Production uses FFmpeg 4.4: preserve its CLI constraint while doing real encoding.
    real_run = subprocess.run
    def ffmpeg_44(args, **kwargs):
        if args[0] == 'ffmpeg' and '-fps_mode' in args:
            return subprocess.CompletedProcess(args, 1, stdout=b'', stderr=b"Unrecognized option 'fps_mode'.")
        if args[0] == 'ffmpeg' and '-vsync' in args:
            # The test host uses modern FFmpeg, so translate the legacy CLI for real encoding.
            args = list(args)
            index = args.index('-vsync')
            args[index:index + 2] = ['-fps_mode', 'passthrough']
        return real_run(args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', ffmpeg_44)
    source = make_video(tmp_path / 'source.mp4', fps=60)
    paths = dict.fromkeys(('cam_01', 'cam_02', 'cam_03', 'cam_04'), source)
    versions = dict.fromkeys(paths, 'v1')
    service = preview.InputPreviewService(tmp_path / 'cache')
    service.prepare('task', paths, versions)
    service.wait_for_idle(timeout=30)
    state = service.status('task', versions)
    assert state['status'] == 'ready', state
    for camera in paths:
        assert state['cameras'][camera]['frame_count'] == 60
        assert state['cameras'][camera]['duration_ms'] == pytest.approx(1000, abs=1)
        assert service.frame('task', camera, versions, 500)['actual_time_ms'] == 500
