from pathlib import Path

from pydantic import Field, SecretStr
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
    glm_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="GLM_API_KEY", repr=False)
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-5.3"
    glm_reasoning_effort: str = "max"
    glm_temperature: float = Field(default=1.0, ge=0, le=1, multiple_of=0.01)
    glm_max_tokens: int = Field(default=65536, ge=1024, le=131072)
    glm_timeout_seconds: float = Field(default=600, ge=1, le=1800)
    analyst_worker_enabled: bool = True
    analyst_concurrency: int = Field(default=8, ge=1, le=8)
    analyst_daily_limit: int = Field(default=100, ge=1)


def get_settings() -> AppSettings:
    return AppSettings()
