"""Application settings.

Values come from environment variables, with a `.env` file at the repository
root for development. Secrets never live in the repository; `.env.example`
lists every variable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Cornelius"
    app_env: str = Field(default="development", pattern="^(development|test|staging|production)$")
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    sentry_dsn: str | None = None

    # Supabase
    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # legacy HS256 secret; when empty, JWKS (asymmetric) is used
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54329/cornelius"

    # Object storage (S3 API). Backblaze B2 now; Cloudflare R2 later by config only.
    storage_endpoint_url: str = "https://s3.eu-central-003.backblazeb2.com"
    storage_region: str = "eu-central-003"
    storage_bucket: str = "cornelius-videos"
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_presign_ttl_seconds: int = 7200
    storage_multipart_part_mb: int = 64

    # Jobs
    jobs_poll_interval_s: int = 5

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.app_base_url}
        if self.app_env == "development":
            origins |= {"http://localhost:3000", "http://127.0.0.1:3000"}
        return sorted(origins)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
