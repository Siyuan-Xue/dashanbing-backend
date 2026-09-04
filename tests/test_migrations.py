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
        identities = connection.execute(
            text("SELECT value, user_id FROM user_identity ORDER BY value")
        ).all()
        submissions = connection.execute(
            text("SELECT task_id, owner_id, kind FROM submission_event ORDER BY id")
        ).all()
        user_columns = {column["name"]: column for column in inspect(connection).get_columns("user")}
        analysis_columns = {
            column["name"]: column for column in inspect(connection).get_columns("analysis")
        }

    assert analysis == (7, "legacy", 0)
    assert identities == [("bootstrap", 7)]
    assert submissions == [("legacy-analysis", 7, "initial")]
    assert user_columns["email"]["nullable"] is True
    assert user_columns["is_active"]["nullable"] is False
    assert "created_at" in user_columns
    assert analysis_columns["owner_id"]["nullable"] is False
    assert "submitted_at" in analysis_columns


def test_user_identity_migration_deduplicates_a_single_users_matching_values(
    tmp_path: Path,
    monkeypatch,
):
    """Catches a legacy account inserting its same normalized identity key twice."""
    database_url = f"sqlite:///{tmp_path / 'identity-migration.db'}"
    monkeypatch.setenv("BASKETBALL_DATABASE_URL", database_url)
    monkeypatch.setenv("BASKETBALL_ADMIN_USERNAME", "bootstrap")
    config = _alembic_config()
    command.upgrade(config, "20260903_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO user (id, username, hashed_password) VALUES (9, 'bootstrap', 'hash')")
        )

    command.upgrade(config, "20260904_0002")
    with engine.begin() as connection:
        connection.execute(text("UPDATE user SET email = 'bootstrap' WHERE id = 9"))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        identities = connection.execute(
            text("SELECT value, user_id FROM user_identity ORDER BY value")
        ).all()
    assert identities == [("bootstrap", 9)]


def test_task_input_migration_records_staged_upload_metadata(tmp_path: Path, monkeypatch):
    """Catches shipping the staged task API without its durable input metadata."""
    database_url = f"sqlite:///{tmp_path / 'task-input-migration.db'}"
    monkeypatch.setenv("BASKETBALL_DATABASE_URL", database_url)
    monkeypatch.setenv("BASKETBALL_ADMIN_USERNAME", "bootstrap")
    config = _alembic_config()
    command.upgrade(config, "20260903_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO user (id, username, hashed_password) VALUES (11, 'bootstrap', 'hash')")
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        columns = {column["name"]: column for column in inspect(connection).get_columns("task_input")}
        primary_key = inspect(connection).get_pk_constraint("task_input")["constrained_columns"]
        foreign_keys = inspect(connection).get_foreign_keys("task_input")

    assert set(columns) == {
        "task_id",
        "slot",
        "original_filename",
        "byte_size",
        "validation_state",
        "upload_operation_id",
        "path",
        "created_at",
        "updated_at",
    }
    assert set(primary_key) == {"task_id", "slot"}
    assert foreign_keys[0]["referred_table"] == "analysis"


def test_api_key_migration_creates_owner_scoped_non_plaintext_credentials(
    tmp_path: Path,
    monkeypatch,
):
    """Catches deployments missing the API-key verifier and lifecycle metadata."""
    database_url = f"sqlite:///{tmp_path / 'api-key-migration.db'}"
    monkeypatch.setenv("BASKETBALL_DATABASE_URL", database_url)
    monkeypatch.setenv("BASKETBALL_ADMIN_USERNAME", "bootstrap")
    config = _alembic_config()
    command.upgrade(config, "20260903_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO user (id, username, hashed_password) VALUES (13, 'bootstrap', 'hash')")
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        columns = {column["name"]: column for column in inspect(connection).get_columns("api_key")}
        foreign_keys = inspect(connection).get_foreign_keys("api_key")
        indexes = inspect(connection).get_indexes("api_key")

    assert set(columns) == {
        "id",
        "owner_id",
        "name",
        "digest",
        "prefix",
        "last_four",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
    }
    assert columns["owner_id"]["nullable"] is False
    assert columns["digest"]["nullable"] is False
    assert foreign_keys[0]["referred_table"] == "user"
    assert any(index["column_names"] == ["digest"] and index["unique"] for index in indexes)
