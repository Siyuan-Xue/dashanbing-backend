import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

CAMERAS = ('cam_01', 'cam_02', 'cam_03', 'cam_04')


def inputs(tmp_path):
    result = []
    for camera in (*CAMERAS, 'enrollment_video'):
        path = tmp_path / f'{camera}.mkv'
        path.write_bytes(b'video')
        result.append(SimpleNamespace(slot=camera, path=str(path), validation_state='valid',
                                      upload_operation_id='version-one', byte_size=5,
                                      updated_at=datetime.now(timezone.utc)))
    return result


def test_selected_times_normalize_to_cam03_and_snapshot_overlap():
    from app.services.task_sync import validate_sync
    config = validate_sync({'selected_timestamps_ms': dict(zip(CAMERAS, [1000, 1100, 900, 950])),
                            'input_versions': dict.fromkeys(CAMERAS, 'v1')},
                           dict.fromkeys(CAMERAS, 'v1'), dict.fromkeys(CAMERAS, 2000))
    assert config['camera_time_offsets_ms'] == dict(zip(CAMERAS, [100, 200, 0, 50]))
    assert (config['overlap_start_ms'], config['overlap_end_ms']) == (0, 1800)


@pytest.mark.parametrize('payload,code', [
    ({}, 'sync_invalid'),
    ({'offsets_ms': dict.fromkeys(CAMERAS, 0), 'selected_timestamps_ms': dict.fromkeys(CAMERAS, 1)}, 'sync_invalid'),
    ({'offsets_ms': dict.fromkeys(CAMERAS, float('nan'))}, 'sync_invalid'),
    ({'offsets_ms': dict.fromkeys(CAMERAS, 1)}, 'sync_invalid'),
    ({'offsets_ms': dict(zip(CAMERAS, [2000, 0, 0, 0]))}, 'sync_no_overlap'),
    ({'selected_timestamps_ms': dict.fromkeys(CAMERAS, 2000)}, 'sync_invalid'),
    ({'offsets_ms': {'cam_01': 0}}, 'sync_invalid'),
])
def test_invalid_sync_rejected(payload, code):
    from app.services.task_sync import validate_sync
    payload['input_versions'] = dict.fromkeys(CAMERAS, 'v1')
    with pytest.raises(HTTPException) as error:
        validate_sync(payload, dict.fromkeys(CAMERAS, 'v1'), dict.fromkeys(CAMERAS, 2000))
    assert error.value.status_code == 422
    assert error.value.detail['code'] == code


def test_stale_camera_versions_are_conflict():
    from app.services.task_sync import validate_sync
    with pytest.raises(HTTPException) as error:
        validate_sync({'offsets_ms': dict.fromkeys(CAMERAS, 0), 'input_versions': dict.fromkeys(CAMERAS, 'old')},
                      dict.fromkeys(CAMERAS, 'new'), dict.fromkeys(CAMERAS, 2000))
    assert error.value.status_code == 409
    assert error.value.detail['code'] == 'sync_stale'


def test_only_camera_replacement_invalidates_confirmation(tmp_path):
    from app.services.task_sync import source_versions, sync_status
    items = inputs(tmp_path)
    task = SimpleNamespace(sync_config_json=json.dumps({'schema_version': 1, 'input_versions': source_versions(items)}),
                           submitted_at=None, status='draft')
    assert sync_status(task, items) == 'confirmed'
    items[-1].upload_operation_id = 'new'
    assert sync_status(task, items) == 'confirmed'
    items[0].upload_operation_id = 'new'
    assert sync_status(task, items) == 'stale'
    task.status = 'completed'
    task.submitted_at = datetime.now(timezone.utc)
    assert sync_status(task, []) == 'confirmed'
    task.sync_config_json = None
    assert sync_status(task, []) == 'legacy'


def test_submission_requires_registration_and_current_sync(tmp_path):
    from app.services.task_sync import require_submission_config
    task = SimpleNamespace(enrollment_mode='sequential', expected_persons=None, sync_config_json=None,
                           submitted_at=None, status='draft')
    with pytest.raises(HTTPException) as error:
        require_submission_config(task, inputs(tmp_path))
    assert error.value.status_code == 422
    assert error.value.detail['code'] == 'registration_config_required'
    task.expected_persons = 2
    with pytest.raises(HTTPException) as error:
        require_submission_config(task, inputs(tmp_path))
    assert error.value.status_code == 422
    assert error.value.detail['code'] == 'sync_config_required'


def test_storage_snapshot_uses_supplied_sync_and_registration(tmp_path):
    from app.config import AppSettings
    from app.services.storage import AnalysisStorage
    storage = AnalysisStorage(AppSettings(runtime_root=tmp_path, min_free_storage_gb=0))
    config = {'schema_version': 1, 'camera_time_offsets_ms': dict.fromkeys(CAMERAS, 0)}
    manifest = storage.prepare_task_submission('task-one', {'enrollment_mode': 'lineup', 'expected_persons': 4}, sync_config=config)
    assert json.loads(Path(manifest['sync']).read_text()) == config
    assert manifest['enrollment_mode'] == 'lineup'
    assert manifest['expected_persons'] == 4
    assert manifest['sync_schema_version'] == 1
    assert json.loads((storage.analysis_root('task-one') / 'input_manifest.json').read_text()) == manifest


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session, create_engine
    from app.api.deps import get_current_user
    from app.database import get_session
    from app.api.routes import tasks, analyses, task_sync
    from app.config import AppSettings
    from app.models import User
    import app.admin_models  # Register concurrently added quota tables in this isolated database.
    from app.services.storage import AnalysisStorage
    app = FastAPI()
    for router in (tasks.router, analyses.router, task_sync.router):
        app.include_router(router, prefix='/api/v1')
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}', connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    user = User(id=1, username='test-owner', hashed_password='unused', role='user')
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    def sessions():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_current_user] = lambda: user
    app.state.engine = engine
    app.state.storage = AnalysisStorage(AppSettings(runtime_root=tmp_path / 'runtime', min_free_storage_gb=0))
    app.state.storage.video_probe = lambda *_: None
    app.state.readiness = SimpleNamespace(require_ready=lambda: None)
    monkeypatch.setattr('app.services.input_preview.inspect_video', lambda _: {'duration_ms': 2000})
    with TestClient(app) as client:
        yield client
    engine.dispose()


def create_full_draft(api, **config):
    created = api.post('/api/v1/tasks', json={'title': 'Training', 'mode': 'quick', **config})
    assert created.status_code == 201, created.text
    task_id = created.json()['id']
    for slot in ('enrollment_video', *CAMERAS):
        response = api.put(f'/api/v1/tasks/{task_id}/inputs/{slot}', files={'file': (slot+'.mkv', b'\x1aE\xdf\xa3video')})
        assert response.status_code == 200, response.text
    return task_id


def confirm(api, task_id):
    current = api.get(f'/api/v1/tasks/{task_id}/sync')
    assert current.status_code == 200, current.text
    payload = {'input_versions': current.json()['source_versions'], 'offsets_ms': dict.fromkeys(CAMERAS, 0)}
    response = api.put(f'/api/v1/tasks/{task_id}/sync', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_draft_submit_registration_sync_and_retry_snapshot(api):
    from sqlmodel import Session
    from app.models import Analysis
    task_id = create_full_draft(api, enrollment_mode='lineup', expected_persons=4)
    missing = api.post(f'/api/v1/tasks/{task_id}/submit')
    assert missing.status_code == 422, missing.text
    assert missing.json()['detail']['code'] == 'sync_config_required'
    confirmed = confirm(api, task_id)
    assert confirmed['status'] == 'confirmed'
    queued = api.post(f'/api/v1/tasks/{task_id}/submit')
    assert queued.status_code == 200, queued.text
    with Session(api.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        original = json.loads(task.input_manifest_json)
        assert original['enrollment_mode'] == 'lineup'
        assert original['expected_persons'] == 4
        assert json.loads(Path(original['sync']).read_text()) == confirmed['config']
        task.status = 'failed'
        session.add(task)
        session.commit()
    retried = api.post(f'/api/v1/tasks/{task_id}/retry')
    assert retried.status_code == 200, retried.text
    with Session(api.app.state.engine) as session:
        assert json.loads(session.get(Analysis, task_id).input_manifest_json) == original


def test_camera_change_409_enrollment_change_keeps_sync(api):
    task_id = create_full_draft(api, expected_persons=2)
    confirm(api, task_id)
    for slot, expected in [('enrollment_video', 'confirmed'), ('cam_01', 'stale')]:
        response = api.put(f'/api/v1/tasks/{task_id}/inputs/{slot}', files={'file': ('new.mkv', b'\x1aE\xdf\xa3video')})
        assert response.status_code == 200
        assert api.get(f'/api/v1/tasks/{task_id}/sync').json()['status'] == expected
    response = api.post(f'/api/v1/tasks/{task_id}/submit')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'sync_stale'


def test_owner_only_sync_routes(api):
    from app.api.deps import get_current_user
    from app.models import User
    task_id = create_full_draft(api)
    api.app.dependency_overrides[get_current_user] = lambda: User(id=2, username='another-owner', hashed_password='unused', role='user')
    for method, suffix in [('get', '/sync'), ('post', '/sync/preview'), ('get', '/sync/frames/cam_01?time_ms=0')]:
        assert getattr(api, method)(f'/api/v1/tasks/{task_id}{suffix}').status_code == 404


def test_single_upload_requires_config_and_uses_shared_snapshot(api):
    from sqlmodel import Session
    from app.models import Analysis
    files = {slot: (slot+'.mkv', b'\x1aE\xdf\xa3video') for slot in ('enrollment_video', *CAMERAS)}
    fields = {'title': 'Single upload', 'mode': 'quick', 'enrollment_mode': 'lineup',
              'expected_persons': '3', 'analyst_locale': 'en', 'sync': json.dumps({'offsets_ms': dict.fromkeys(CAMERAS, 0)})}
    missing = api.post('/api/v1/analyses/upload', data={'title': 'Missing', 'mode': 'quick'}, files=files)
    assert missing.status_code == 422
    response = api.post('/api/v1/analyses/upload', data=fields, files=files)
    assert response.status_code == 201, response.text
    with Session(api.app.state.engine) as session:
        task = session.get(Analysis, response.json()['id'])
        manifest = json.loads(task.input_manifest_json)
        assert (task.enrollment_mode, task.expected_persons, task.analyst_locale) == ('lineup', 3, 'en')
        assert json.loads(Path(manifest['sync']).read_text())['input_versions']
        assert manifest['expected_persons'] == 3


def test_return_to_input_retains_files_and_rejects_completed_report(api):
    from sqlmodel import Session
    from app.models import Analysis
    task_id = create_full_draft(api, expected_persons=2)
    confirm(api, task_id)
    api.post(f'/api/v1/tasks/{task_id}/submit')
    with Session(api.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        paths = json.loads(task.input_manifest_json)
        task.status = 'failed'
        task.error_code = 'registration_count_mismatch'
        session.add(task)
        session.commit()
    response = api.post(f'/api/v1/tasks/{task_id}/return-to-input')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'draft'
    assert all(Path(paths[c]).is_file() for c in CAMERAS)
    report = api.app.state.storage.analysis_root(task_id) / 'output' / 'report.json'
    report.write_text('{"completed":true}')
    with Session(api.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        task.status = 'failed'
        session.add(task)
        session.commit()
    assert api.post(f'/api/v1/tasks/{task_id}/return-to-input').status_code == 409
    assert report.read_text() == '{"completed":true}'


def test_preset_explicit_v3_configuration_and_group_snapshot(api, tmp_path):
    from app.services.presets import PresetCatalog
    from sqlmodel import Session
    from app.models import Analysis
    root = tmp_path / 'samples'
    inputs = root / 'test_data_v3'
    inputs.mkdir(parents=True)
    for filename in ['0-2.mkv', *[f'4-{i}.mkv' for i in range(1, 5)]]:
        (inputs / filename).write_bytes(b'\x1aE\xdf\xa3video')
    source_sync = inputs / 'sync' / 'group_04.json'
    source_sync.parent.mkdir()
    source_sync.write_text(json.dumps({'anchor_camera': 'cam_03', 'camera_time_offsets_ms': dict(zip(CAMERAS, [100, 200, 0, 50]))}))
    api.app.state.presets = PresetCatalog(root)
    for endpoint in ('/api/v1/tasks/from-preset', '/api/v1/analyses/preset'):
        response = api.post(endpoint, json={'preset_id': 'quick-demo', 'mode': 'quick', 'analyst_locale': 'en'})
        assert response.status_code == 201, response.text
        assert response.json()['enrollment_mode'] == 'lineup'
        assert response.json()['expected_persons'] == 4
        assert response.json()['analyst_locale'] == 'en'
        with Session(api.app.state.engine) as session:
            task = session.get(Analysis, response.json()['id'])
            manifest = json.loads(task.input_manifest_json)
            assert Path(manifest['sync']) != source_sync
            snapshot = json.loads(Path(manifest['sync']).read_text())
            assert snapshot['camera_time_offsets_ms']['cam_02'] == 200
            assert snapshot['input_versions']


def test_readiness_no_longer_depends_on_shared_upload_sync(tmp_path, monkeypatch):
    import sys
    from app.config import AppSettings
    from app.services.readiness import ReadinessService
    monkeypatch.setitem(sys.modules, 'torch', None)
    settings = AppSettings(runtime_root=tmp_path, model_root=tmp_path / 'models', sample_root=tmp_path / 'samples', sync_config=tmp_path / 'missing.json')
    report = ReadinessService(settings).report()
    assert 'sync_config' not in {check['name'] for check in report['checks']}


def test_null_mode_patch_is_rejected_without_clearing_sync(api):
    task_id = create_full_draft(api, expected_persons=2)
    before = confirm(api, task_id)
    response = api.patch(f'/api/v1/tasks/{task_id}', json={'title': 'Training', 'mode': 'quick', 'enrollment_mode': None})
    assert response.status_code == 422
    assert api.get(f'/api/v1/tasks/{task_id}/sync').json() == before


def test_preview_range_and_stale_video_source(api):
    from app.services.input_preview import InputPreviewService
    task_id = create_full_draft(api)
    versions = api.get(f'/api/v1/tasks/{task_id}/sync').json()['source_versions']
    service = InputPreviewService(api.app.state.storage.root)
    api.app.state.storage.input_preview = service
    directory = service._directory(task_id, versions)
    directory.mkdir(parents=True)
    for camera in CAMERAS:
        (directory / f'{camera}.mp4').write_bytes(b'0123456789')
    (directory / 'status.json').write_text(json.dumps({'status': 'ready', 'source_versions': versions,
                                                      'cameras': {}, 'error': None}))
    response = api.get(f'/api/v1/tasks/{task_id}/sync/preview/cam_01', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.content == b'2345'
    assert response.headers['content-range'] == 'bytes 2-5/10'
    response = api.get(f'/api/v1/tasks/{task_id}/sync/preview/cam_01?source_version=obsolete')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'sync_stale'


def test_historical_submitted_task_retries_without_new_config(api):
    from app.models import Analysis
    from sqlmodel import Session
    task_id = create_full_draft(api)
    root = api.app.state.storage.analysis_root(task_id)
    sync = root / 'input' / 'sync.json'
    sync.write_text('{"old_sync":true}')
    with Session(api.app.state.engine) as session:
        task = session.get(Analysis, task_id)
        manifest = {c: str(root / 'input' / f'{c}.mkv') for c in CAMERAS}
        manifest.update(enrollment_video=str(root / 'input' / 'enrollment.mkv'), sync=str(sync))
        task.input_manifest_json = json.dumps(manifest)
        task.status = 'failed'
        task.submitted_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()
    response = api.post(f'/api/v1/tasks/{task_id}/retry')
    assert response.status_code == 200
    assert response.json()['sync_status'] == 'legacy'
    assert sync.read_text() == '{"old_sync":true}'


def test_prepared_demo_auto_sync_is_exact_and_grouped(tmp_path, monkeypatch):
    import hashlib
    from app.services import prepared_demo_sync as demo
    items = inputs(tmp_path)
    cameras = {}
    for index, item in enumerate(items[:4]):
        Path(item.path).write_bytes(f'video-{index}'.encode())
        cameras[item.slot] = {'size': 7, 'sha256': hashlib.sha256(Path(item.path).read_bytes()).hexdigest(), 'duration_ms': 22000}
    monkeypatch.setattr(demo, 'DEMOS', [{'name': 'test-demo', 'cameras': cameras}])
    config = demo.prepared_demo_config(items)
    assert config['camera_time_offsets_ms'] == dict.fromkeys(CAMERAS, 0)
    assert config['input_versions']
    assert config['overlap_end_ms'] == 22000
    # A byte change of the same length and a camera swap must both be rejected.
    original = Path(items[0].path).read_bytes()
    Path(items[0].path).write_bytes(b'altered')
    assert demo.prepared_demo_config(items) is None
    Path(items[0].path).write_bytes(original)
    items[0].path, items[1].path = items[1].path, items[0].path
    assert demo.prepared_demo_config(items) is None


def test_demo_sync_route_confirms_and_preserves_manual_sync(api, monkeypatch):
    from app.api.routes import task_sync
    from app.services.task_sync import source_versions, validate_sync
    task_id = create_full_draft(api, expected_persons=4)
    def recognized(items):
        return validate_sync({'offsets_ms': dict.fromkeys(CAMERAS, 0)}, source_versions(items),
                             dict.fromkeys(CAMERAS, 2000), bind_uploaded_versions=True)
    monkeypatch.setattr(task_sync, 'prepared_demo_config', recognized)
    response = api.post(f'/api/v1/tasks/{task_id}/sync/demo')
    assert response.status_code == 200
    assert response.json()['status'] == 'confirmed'
    monkeypatch.setattr(task_sync, 'prepared_demo_config', lambda _: pytest.fail('Do not overwrite manual confirmation'))
    assert api.post(f'/api/v1/tasks/{task_id}/sync/demo').json()['status'] == 'confirmed'
    assert api.post(f'/api/v1/tasks/{task_id}/submit').status_code == 200


def test_unknown_inputs_are_not_automatically_confirmed(api):
    task_id = create_full_draft(api, expected_persons=4)
    response = api.post(f'/api/v1/tasks/{task_id}/sync/demo')
    assert response.status_code == 200
    assert response.json()['status'] == 'unconfirmed'
    assert api.post(f'/api/v1/tasks/{task_id}/submit').status_code == 422


def test_single_upload_can_omit_sync_only_for_recognized_demo(api, monkeypatch):
    from app.services import prepared_demo_sync as demo
    from app.services.task_sync import source_versions, validate_sync
    files = {slot: (slot+'.mkv', b'\x1aE\xdf\xa3video') for slot in ('enrollment_video', *CAMERAS)}
    fields = {'title': 'Demo without sync UI', 'mode': 'quick', 'enrollment_mode': 'sequential',
              'expected_persons': '4', 'analyst_locale': 'zh'}
    rejected = api.post('/api/v1/analyses/upload', data=fields, files=files)
    assert rejected.status_code == 422
    assert rejected.json()['detail']['code'] == 'sync_config_required'
    def recognized(items):
        return validate_sync({'offsets_ms': dict.fromkeys(CAMERAS, 0)}, source_versions(items),
                             dict.fromkeys(CAMERAS, 22000), bind_uploaded_versions=True)
    monkeypatch.setattr(demo, 'prepared_demo_config', recognized)
    created = api.post('/api/v1/analyses/upload', data=fields, files=files)
    assert created.status_code == 201, created.text
    task_id = created.json()['id']
    assert created.json()['status'] == 'queued'
    assert api.get(f'/api/v1/tasks/{task_id}/sync').json()['config']['camera_time_offsets_ms'] == dict.fromkeys(CAMERAS, 0)
