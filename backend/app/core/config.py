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
    max_attachment_bytes: int = 10_000_000
    max_attachments_per_ticket: int = 10

    # --- Database connection pool ---
    # SQLAlchemy's own defaults (pool_size=5, max_overflow=10, no recycle)
    # are fine for local dev but too small/unmonitored for production
    # concurrency. pool_recycle avoids handing out connections postgres or
    # an intermediary has silently dropped after sitting idle too long.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    sla_scheduler_enabled: bool = True

    clamav_host: str = "127.0.0.1"
    clamav_port: int = 3310
    clamav_timeout: float = 10.0

    # --- Notification Engine: Email (SMTP) ---
    # Left empty by default. When smtp_host is unset, the email sender logs
    # instead of connecting to a real server -- fine for local dev/tests, but
    # deployments that want email delivery must set these.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = True

    # --- Notification Engine: SMS (Twilio) ---
    # Same story: unset twilio_account_sid means SMS delivery is logged
    # rather than actually sent.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()