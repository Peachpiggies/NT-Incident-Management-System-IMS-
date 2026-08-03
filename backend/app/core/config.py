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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
