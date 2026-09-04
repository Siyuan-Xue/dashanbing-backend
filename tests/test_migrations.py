from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def test_identity_migration_backfills_existing_analyses_before_making_owner_required(
    tmp_path: Path,
    monkeypatch,
):
    """Catches upgrading old local data with analyses that have no tenant owner."""
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("BASKETBALL_DATABASE_URL", database_url)
    monkeypatch.setenv("BASKETBALL_ADMIN_USERNAME", "bootstrap")
    config = _alembic_config()
    command.upgrade(config, "20260903_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO user (id, username, hashed_password) VALUES (7, 'bootstrap', 'hash')")
        )
        connection.execute(
            text(
                """
                INSERT INTO analysis (
                    id, title, mode, source_type, status, progress, stage_message,
                    input_manifest_json, created_at, updated_at
                ) VALUES (
                    'legacy-analysis', 'Legacy', 'full', 'upload', 'queued', 0, 'waiting',
                    '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        analysis = connection.execute(
            text(
                "SELECT owner_id, created_via, retry_count FROM analysis WHERE id = 'legacy-analysis'"
            )
        ).one()
        user_columns = {column["name"]: column for column in inspect(connection).get_columns("user")}
        analysis_columns = {
            column["name"]: column for column in inspect(connection).get_columns("analysis")
        }

    assert analysis == (7, "legacy", 0)
    assert user_columns["email"]["nullable"] is True
    assert user_columns["is_active"]["nullable"] is False
    assert "created_at" in user_columns
    assert analysis_columns["owner_id"]["nullable"] is False
    assert "submitted_at" in analysis_columns
