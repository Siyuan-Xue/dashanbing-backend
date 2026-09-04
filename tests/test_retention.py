import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session

from app.config import AppSettings
from app.database import create_database_engine, create_tables
from app.models import Analysis, User
from app.services.retention import RetentionService
from app.services.storage import AnalysisStorage


def test_retention_cleans_runtime_tiers_but_never_read_only_presets(tmp_path: Path):
    settings = AppSettings(
        database_url=f"sqlite:///{tmp_path / 'retention.db'}",
        runtime_root=tmp_path / "runtime",
        sample_root=tmp_path / "samples",
        admin_password="correct-password",
        jwt_secret_key="test-secret-with-at-least-thirty-two-characters",
    )
    engine = create_database_engine(settings.database_url)
    create_tables(engine)
    storage = AnalysisStorage(settings)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        owner = User(username="retention-owner", hashed_password="hash")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        owner_id = owner.id
    old = Analysis(
        title="old",
        input_manifest_json=json.dumps({}),
        status="completed",
        owner_id=owner_id,
        created_at=now - timedelta(days=200),
        completed_at=now - timedelta(days=190),
    )
    recent = Analysis(
        title="recent",
        input_manifest_json=json.dumps({}),
        status="completed",
        owner_id=owner_id,
        created_at=now - timedelta(days=40),
        completed_at=now - timedelta(days=20),
    )
    raw_expired = Analysis(
        title="raw-expired",
        input_manifest_json=json.dumps({}),
        status="completed",
        owner_id=owner_id,
        created_at=now - timedelta(days=50),
        completed_at=now - timedelta(days=40),
    )
    queued = Analysis(
        title="queued",
        input_manifest_json=json.dumps({}),
        status="queued",
        owner_id=owner_id,
        created_at=now - timedelta(days=200),
    )
    with Session(engine) as session:
        session.add(old)
        session.add(recent)
        session.add(raw_expired)
        session.add(queued)
        session.commit()
        old_id, recent_id, raw_expired_id, queued_id = old.id, recent.id, raw_expired.id, queued.id
    for analysis_id in (old_id, recent_id, raw_expired_id, queued_id):
        root = storage.prepare(analysis_id)
        (root / "input" / "video.mkv").write_bytes(b"raw")
        (root / "data" / "enrollment").mkdir()
        (root / "data" / "enrollment" / "face.npy").write_bytes(b"gallery")
        (root / "data" / "sessions").mkdir()
        (root / "data" / "sessions" / "raw.mp4").write_bytes(b"raw")
        (root / "engine-output").mkdir()
        (root / "engine-output" / "intermediate.json").write_text("{}", encoding="utf-8")
        (root / "output" / "report.json").write_text("{}", encoding="utf-8")
    preset = settings.sample_root / "outputs" / "v3" / "group_04" / "report.json"
    preset.parent.mkdir(parents=True)
    preset.write_text("{}", encoding="utf-8")

    RetentionService(settings, engine, storage).run_once(now=now)

    old_root = storage.analysis_root(old_id)
    recent_root = storage.analysis_root(recent_id)
    raw_expired_root = storage.analysis_root(raw_expired_id)
    queued_root = storage.analysis_root(queued_id)
    assert not (old_root / "input").exists()
    with Session(engine) as session:
        assert session.get(Analysis, old_id) is None
    assert (recent_root / "input" / "video.mkv").is_file()
    assert not (recent_root / "data" / "enrollment").exists()
    assert (recent_root / "data" / "sessions" / "raw.mp4").is_file()
    assert (recent_root / "output" / "report.json").is_file()
    assert not (raw_expired_root / "input").exists()
    assert not (raw_expired_root / "data").exists()
    assert not (raw_expired_root / "engine-output").exists()
    assert (raw_expired_root / "output" / "report.json").is_file()
    assert (queued_root / "input" / "video.mkv").is_file()
    assert preset.is_file()
