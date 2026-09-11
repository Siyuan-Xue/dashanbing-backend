"""Bounded CPU previews with measured source PTS and restart-safe disk metadata."""
import base64
import bisect
import fcntl
import hashlib
import json
import math
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

from app.services.task_sync import sync_error

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='input-preview')
_CAPACITY = threading.BoundedSemaphore(8)
_PROCESS = uuid4().hex
_CPU_LOCK = threading.Lock()
MAX_FRAMES = 216_000
MAX_CACHE_BYTES = 2 * 1024**3


def _run(args, *, timeout=120):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        # FFmpeg 4.4 lacks -fps_mode; newer FFmpeg releases have removed -vsync.
        # Retry only this unsupported option, keeping passthrough frame timing.
        if (result.returncode and args[0] == 'ffmpeg' and '-fps_mode' in args
                and b"Unrecognized option 'fps_mode'" in (result.stderr or b'')):
            legacy = list(args)
            index = legacy.index('-fps_mode')
            legacy[index:index + 2] = ['-vsync', '0']
            result = subprocess.run(legacy, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise sync_error('preview_failed', 'Video processing is unavailable or timed out.', 503) from None
    if result.returncode:
        raise sync_error('preview_failed', 'The video could not be processed.', 422)
    return result.stdout


def timeline_metadata(pts_ms: list[float], fps: float) -> dict:
    if not pts_ms or len(pts_ms) > MAX_FRAMES or not math.isfinite(fps) or not 0 < fps <= 240:
        raise sync_error('unsupported_timeline', 'Use a constant-rate video of at most 216000 frames and 240 fps.')
    step = 1000 / fps
    if any(not math.isfinite(t) for t in pts_ms) or any(
        b <= a or abs((b - a) - step) > max(1.1, step * .025)
        for a, b in zip(pts_ms, pts_ms[1:])
    ):
        raise sync_error('unsupported_timeline', 'Variable frame rates, timestamp gaps and timeline edits are unsupported.')
    times = [round(t - pts_ms[0], 6) for t in pts_ms]
    return {'duration_ms': round(times[-1] + step, 6), 'fps': fps, 'frame_count': len(times),
            'source_start_pts_ms': pts_ms[0], 'frame_timestamps_ms': times}


def inspect_video(path: Path) -> dict:
    """Decode frame timing, never assume a nominal 30 fps timeline."""
    try:
        payload = json.loads(_run(['ffprobe', '-v', 'error', '-threads', '1', '-select_streams', 'v:0',
                                  '-read_intervals', f'%+#{MAX_FRAMES + 16}',
                                  '-show_entries', 'stream=avg_frame_rate,r_frame_rate:frame=best_effort_timestamp_time',
                                  '-of', 'json', str(path)]))
        stream = payload['streams'][0]
        fps = float(Fraction(stream['r_frame_rate']))
        pts = [float(frame['best_effort_timestamp_time']) * 1000 for frame in payload['frames']]
    except (KeyError, IndexError, ValueError, TypeError, ZeroDivisionError):
        raise sync_error('unsupported_timeline', 'A valid video frame timeline is required.') from None
    return timeline_metadata(pts, fps)


def nearest_frame(metadata: dict, time_ms: float) -> tuple[int, float]:
    if not math.isfinite(time_ms) or not 0 <= time_ms < metadata['duration_ms']:
        raise sync_error('sync_invalid', 'Frame time must be inside the video duration.')
    times = metadata['frame_timestamps_ms']
    index = bisect.bisect_left(times, time_ms)
    choices = [i for i in (index - 1, index) if 0 <= i < len(times)]
    index = min(choices, key=lambda i: (abs(times[i] - time_ms), i))
    return index, times[index]


def _write_json(path: Path, payload):
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    temporary.write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


class InputPreviewService:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._jobs = {}

    def _directory(self, task_id, versions):
        if not task_id or Path(task_id).name != task_id or task_id in {'.', '..'}:
            raise sync_error('input_missing', 'Task input is unavailable.', 404)
        digest = hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:32]
        return self.root / task_id / 'input' / 'preview' / digest

    def status(self, task_id: str, versions: dict) -> dict:
        directory = self._directory(task_id, versions)
        empty = {'status': 'unprepared', 'source_versions': versions, 'cameras': {}, 'error': None}
        try:
            data = json.loads((directory / 'status.json').read_text())
        except (OSError, ValueError):
            return empty
        if data.get('source_versions') != versions:
            return empty
        if data['status'] == 'preparing':
            pid = data.get('_pid')
            try:
                os.kill(pid, 0)
                alive = pid != os.getpid() or data.get('_process') == _PROCESS
            except (OSError, TypeError):
                alive = False
            if not alive:
                return {**empty, 'status': 'failed', 'error': {'code': 'preview_interrupted', 'message': 'Preview preparation was interrupted. Prepare again.'}}
        if data['status'] == 'ready' and any(not (directory / f'{c}.mp4').is_file() for c in versions):
            return empty
        return {key: value for key, value in data.items() if not key.startswith('_')}

    def prepare(self, task_id: str, paths: dict, versions: dict) -> dict:
        directory = self._directory(task_id, versions)
        with self._lock:
            self._jobs = {key: job for key, job in self._jobs.items() if not job.done()}
            current = self.status(task_id, versions)
            if current['status'] in {'ready', 'preparing'}:
                return current
            if not _CAPACITY.acquire(blocking=False):
                raise sync_error('preview_busy', 'Preview queue is full. Try again shortly.', 503)
            try:
                directory.mkdir(parents=True, exist_ok=True)
                state = {'status': 'preparing', 'source_versions': versions, 'cameras': {}, 'error': None,
                         '_pid': os.getpid(), '_process': _PROCESS}
                _write_json(directory / 'status.json', state)
                fingerprints = {c: (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ino) for c, p in paths.items()}
                self._jobs[str(directory)] = _EXECUTOR.submit(self._convert, task_id, paths, versions, fingerprints, directory)
            except Exception:
                _CAPACITY.release()
                raise
        return {key: value for key, value in state.items() if not key.startswith('_')}

    def _convert(self, task_id, paths, versions, fingerprints, directory):
        try:
            # Shared file lock additionally bounds conversion across server processes.
            self.root.mkdir(parents=True, exist_ok=True)
            with _CPU_LOCK, (self.root / '.preview-cpu.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                cameras = {}
                for camera, path in paths.items():
                    metadata = inspect_video(path)
                    target = directory / f'{camera}.mp4'
                    _run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '1', '-i', str(path),
                          '-map', '0:v:0', '-an', '-vf', "setpts=PTS-STARTPTS,scale='min(960,iw)':-2",
                          '-filter_threads', '1', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast',
                          '-crf', '28', '-pix_fmt', 'yuv420p', '-fps_mode', 'passthrough', '-movflags', '+faststart',
                          '-fs', str(MAX_CACHE_BYTES // 4), '-y', str(target)], timeout=600)
                    if sum(p.stat().st_size for p in directory.iterdir() if p.is_file()) >= MAX_CACHE_BYTES:
                        raise sync_error('preview_cache_limit', 'Preview exceeds the cache budget. Use shorter input videos.', 422)
                    converted = inspect_video(target)
                    if converted['frame_count'] != metadata['frame_count'] or any(
                        abs(a - b) > 1.1 for a, b in zip(converted['frame_timestamps_ms'], metadata['frame_timestamps_ms'])
                    ):
                        raise sync_error('unsupported_timeline', 'Preview cannot preserve this source timeline.')
                    cameras[camera] = {**metadata, 'source_version': versions[camera],
                                       'video_url': f'/api/v1/tasks/{task_id}/sync/preview/{camera}?source_version={versions[camera]}'}
                if any((p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ino) != fingerprints[c] for c, p in paths.items()):
                    raise sync_error('sync_stale', 'Camera input changed during preview preparation.', 409)
                _write_json(directory / 'status.json', {'status': 'ready', 'source_versions': versions, 'cameras': cameras, 'error': None})
                self._prune(directory)
        except Exception as error:
            detail = getattr(error, 'detail', None)
            safe = detail if isinstance(detail, dict) else {'code': 'preview_failed', 'message': 'Preview preparation failed. Prepare again.'}
            if directory.exists():
                for path in directory.glob('*.mp4'):
                    path.unlink(missing_ok=True)
                _write_json(directory / 'status.json', {'status': 'failed', 'source_versions': versions, 'cameras': {}, 'error': safe})
                self._prune(directory)
        finally:
            _CAPACITY.release()

    def _prune(self, current):
        # Keep two versions per task and at most 64 versions / 2 GiB globally.
        entries = []
        for status in self.root.glob('*/input/preview/*/status.json'):
            directory = status.parent
            try:
                data = json.loads(status.read_text())
                if data['status'] == 'preparing':
                    continue
                size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
                entries.append((status.stat().st_mtime_ns, directory, size))
            except (OSError, ValueError, KeyError):
                continue
        entries.sort(reverse=True)
        total = 0
        per_task = {}
        for i, (_, directory, size) in enumerate(entries):
            task = directory.parent
            per_task[task] = per_task.get(task, 0) + 1
            total += size
            if directory != current and (i >= 64 or total > MAX_CACHE_BYTES or per_task[task] > 2):
                shutil.rmtree(directory, ignore_errors=True)

    def video_path(self, task_id, camera, versions):
        state = self.status(task_id, versions)
        if camera not in versions or state['status'] != 'ready':
            raise sync_error('preview_not_ready', 'Prepare current camera previews first.', 409)
        return self._directory(task_id, versions) / f'{camera}.mp4'

    def frame(self, task_id, camera, versions, time_ms):
        video = self.video_path(task_id, camera, versions)
        metadata = self.status(task_id, versions)['cameras'][camera]
        index, actual = nearest_frame(metadata, time_ms)
        # Decode from beginning and select by index: seek approximation cannot shift the returned frame.
        with _CPU_LOCK, (self.root / '.preview-cpu.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            jpeg = _run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '1', '-i', str(video),
                         '-vf', f'select=eq(n\\,{index})', '-filter_threads', '1', '-frames:v', '1',
                         '-threads', '1', '-f', 'image2pipe', '-c:v', 'mjpeg', '-'])
        if not jpeg:
            raise sync_error('preview_failed', 'The requested video frame is unavailable.', 422)
        return {'camera': camera, 'source_version': versions[camera], 'requested_time_ms': time_ms,
                'actual_time_ms': actual, 'source_pts_ms': metadata['source_start_pts_ms'] + actual,
                'frame_index': index, 'image_data_url': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')}

    def wait_for_idle(self, timeout=30):
        """Drain known jobs for graceful callers and deterministic isolated verification."""
        with self._lock:
            jobs = list(self._jobs.values())
        _, pending = wait(jobs, timeout=timeout)
        if pending:
            raise TimeoutError('Preview processing is still active')
