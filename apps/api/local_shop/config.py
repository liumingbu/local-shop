from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    app_timezone: str = "Asia/Shanghai"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: SecretStr
    app_secret_key: SecretStr
    dev_auth_enabled: bool = False

    @model_validator(mode="after")
    def validate_runtime(self):
        if not 1 <= self.api_port <= 65535:
            raise ValueError("API_PORT must be between 1 and 65535")
        try:
            ZoneInfo(self.app_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from None
        try:
            url = make_url(self.database_url.get_secret_value())
        except Exception:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg" or not url.database or not url.username:
            raise ValueError("DATABASE_URL requires postgresql+psycopg, user, and database")
        key = self.app_secret_key.get_secret_value()
        if len(key) < 32 or len(set(key)) < 10:
            raise ValueError("APP_SECRET_KEY must contain at least 32 varied characters")
        if self.dev_auth_enabled and (
            self.app_env == "production" or self.api_host not in {"127.0.0.1", "::1", "localhost"}
        ):
            raise ValueError("Development identity requires non-production loopback binding")
        if self.app_env == "production" and (not url.host or not url.password):
            raise ValueError("Production PostgreSQL configuration requires host and password")
        return self
