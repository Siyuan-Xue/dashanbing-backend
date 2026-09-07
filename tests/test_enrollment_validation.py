import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

RESEARCH = Path(__file__).resolve().parents[1] / 'research_engine'
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))


@pytest.mark.parametrize('count', [0, 7, None, True, 1.5])
def test_person_count_must_be_explicit_integer_one_to_six(count):
    from src.identity.enrollment_validation import validate_registration_config, RegistrationError
    with pytest.raises(RegistrationError):
        validate_registration_config('sequential', count)


def test_no_auto_mode_guessing():
    from src.identity.enrollment_validation import validate_registration_config, RegistrationError
    with pytest.raises(RegistrationError):
        validate_registration_config('auto', 4)


def test_gallery_requires_actual_face_and_body_vectors(tmp_path):
    from src.identity.enrollment_validation import validate_gallery_samples, RegistrationError
    person = tmp_path / 'stu_00'
    person.mkdir()
    (person / 'meta.json').write_text('{"n_samples":8}')
    with pytest.raises(RegistrationError) as error:
        validate_gallery_samples(tmp_path, ['stu_00'], 1)
    assert error.value.code == 'registration_quality_failed'
    np.save(person / 'face_000.npy', np.ones(8))
    np.save(person / 'body_000.npy', np.full(8, np.nan))
    with pytest.raises(RegistrationError):
        validate_gallery_samples(tmp_path, ['stu_00'], 1)
    np.save(person / 'body_000.npy', np.ones(8))
    assert validate_gallery_samples(tmp_path, ['stu_00'], 1) == ['stu_00']
    with pytest.raises(RegistrationError):
        validate_gallery_samples(tmp_path, ['stu_00'], 2)


@pytest.mark.parametrize('detected', [1, 3, 7])
def test_sequential_never_trims_or_ignores_count_mismatch(monkeypatch, detected):
    from src.identity import sequential_enroll as sequential
    monkeypatch.setattr(sequential, 'get_perception_config', lambda: {})
    monkeypatch.setattr(sequential, 'scan_frontal_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sequential, 'cluster_sequential_enrollments', lambda *a, **k: [SimpleNamespace(t0=i) for i in range(detected)])
    written = []
    monkeypatch.setattr(sequential, 'write_enrollment_gallery', lambda *a, **k: written.append(a) or ['fake'])
    with pytest.raises(RuntimeError, match='registration_count_mismatch'):
        sequential.enroll_sequential_from_video('unused', Path('synthetic.mp4'), expected_persons=2)
    assert not written


def test_lineup_does_not_select_subset_of_extra_people(monkeypatch):
    from src.identity import lineup_enroll as lineup
    class Capture:
        def isOpened(self): return True
        def get(self, prop): return 25 if prop == lineup.cv2.CAP_PROP_FPS else 1
        def set(self, *_): pass
        def read(self): return True, np.zeros((100, 100, 3), dtype=np.uint8)
        def release(self): pass
    monkeypatch.setattr(lineup.cv2, 'VideoCapture', lambda *_: Capture())
    monkeypatch.setattr(lineup, '_load_yolo', lambda: (None, None))
    monkeypatch.setattr(lineup, '_detect_persons_pose', lambda *a: [])
    monkeypatch.setattr(lineup, '_frame_lineup_candidates', lambda *a, **k: [
        {'area_ratio': .1, 'frontal': .9, 'cx': .2 + i * .2} for i in range(3)])
    with pytest.raises(RuntimeError, match='registration_count_mismatch'):
        lineup.pick_best_lineup_frame(Path('synthetic.mp4'), expected_persons=2)


def test_runner_uses_manifest_registration_and_checks_gallery_before_processing(tmp_path, monkeypatch):
    from research_engine import product_runner as runner
    from src.identity import enrollment_validation as validation
    files = {}
    for field in ('enrollment_video', 'cam_01', 'cam_02', 'cam_03', 'cam_04', 'sync'):
        path = tmp_path / field
        path.write_text('{}')
        files[field] = str(path)
    manifest = tmp_path / 'input_manifest.json'
    manifest.write_text(json.dumps({**files, 'sync_schema_version': 1, 'enrollment_mode': 'lineup', 'expected_persons': 2}))
    calls = []
    fake = SimpleNamespace(
        run_enroll_group=lambda *a, **k: calls.append(k) or {'student_ids': ['stu_00', 'stu_01'], 'session_id': 'gallery'},
        process_action_group=lambda *a, **k: calls.append('processed'))
    monkeypatch.setitem(sys.modules, 'scripts.run_v2_testset', fake)
    monkeypatch.setattr(runner, 'configure_runtime', lambda *a: None)
    with pytest.raises(validation.RegistrationError, match='registration_quality_failed'):
        runner.run_product_task(tmp_path, manifest, 'quick', tmp_path / 'models')
    assert calls[0]['expected_persons'] == 2
    assert calls[0]['enroll_mode'] == 'lineup'
    assert 'processed' not in calls


def test_runner_never_overwrites_existing_completed_report(tmp_path, monkeypatch):
    from research_engine import product_runner as runner
    output = tmp_path / 'output'
    output.mkdir()
    report = output / 'report.json'
    report.write_text('{"original":true}')
    monkeypatch.setattr(runner, 'configure_runtime', lambda *a: None)
    with pytest.raises(RuntimeError, match='completed_report_exists'):
        runner.run_product_task(tmp_path, tmp_path / 'missing.json', 'quick', tmp_path)
    assert report.read_text() == '{"original":true}'


def test_action_group_rejects_unusable_gallery_before_perception(tmp_path, monkeypatch):
    # The v1 visualizer imports GPU-only RTMLib. This validation path must not call it.
    def forbidden(*args, **kwargs):
        raise AssertionError('Camera preparation or inference must not start')
    monkeypatch.setitem(sys.modules, 'scripts.run_v1_testset', SimpleNamespace(**{
        name: forbidden for name in ('discover_groups', 'remux_to_mp4', 'render_group_visualizations',
                                      'resolve_run_mode', '_ball_track_path')}))
    import src.config as config
    monkeypatch.setattr(config, 'DATA', tmp_path / 'research-data')
    from scripts import run_v2_testset as runner
    import src.privacy.db as privacy_db
    monkeypatch.setattr(privacy_db, 'DB_PATH', tmp_path / 'research.db')
    monkeypatch.setattr(runner, 'register_student', forbidden)
    monkeypatch.setattr(runner, 'grant_consent', forbidden)
    from src.identity.enrollment_validation import RegistrationError
    monkeypatch.setattr(runner, 'init_db', lambda: None)
    monkeypatch.setattr(runner, 'create_session', lambda *a, **k: 'new-session')
    monkeypatch.setattr(runner, 'get_perception_config', lambda: {})
    monkeypatch.setattr(runner, 'get_action_segment_camera', lambda: 'cam_03')
    monkeypatch.setattr(runner, 'data_path', lambda *parts: tmp_path.joinpath(*parts))
    called = []
    monkeypatch.setattr(runner, '_copy_gallery', lambda *a: called.append('copy') or ['stu_00'])
    with pytest.raises(RegistrationError, match='registration_quality_failed'):
        runner.process_action_group(1, {'cam_03': tmp_path / 'video.mp4'}, tmp_path / 'output',
                                    gallery_session_id='empty', student_ids=['stu_00'])
    assert not called
