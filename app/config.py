from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppSettings(BaseSettings):
    """Local deployment settings, loaded from environment or an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BASKETBALL_", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'runtime' / 'app.db'}"
    runtime_root: Path = PROJECT_ROOT / "runtime"
    sample_root: Path = PROJECT_ROOT / "local-assets" / "sample-bundle" / "data"
    model_root: Path = PROJECT_ROOT / "local-assets" / "runtime-models"
    sync_config: Path = PROJECT_ROOT / "local-assets" / "deployment" / "sync.json"
    frontend_dist: Path = PROJECT_ROOT / "app" / "frontend"
    admin_username: str = Field(default="admin", min_length=3, max_length=50)
    admin_password: str = Field(default="change-me-local-admin", min_length=8, max_length=128)
    jwt_secret_key: str = Field(
        default="change-this-local-jwt-secret-before-deployment-please",
        min_length=32,
    )
    access_token_minutes: int = 12 * 60
    cookie_secure: bool = False
    simulation_mode: bool = False
    worker_enabled: bool = True
    auto_create_schema: bool = False
    min_free_storage_gb: float = 20.0
    max_upload_size_gb: float = 30.0
    enrollment_retention_days: int = 7
    raw_retention_days: int = 30
    result_retention_days: int = 180


def get_settings() -> AppSettings:
    return AppSettings()
