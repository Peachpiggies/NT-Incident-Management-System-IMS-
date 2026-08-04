from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NT Incident Management System"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    jwt_secret: str
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    aws_s3_bucket: str = ""
    aws_region: str = "ap-southeast-1"
    aws_s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    s3_signed_url_expire_seconds: int = 900
    upload_dir: str = "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
