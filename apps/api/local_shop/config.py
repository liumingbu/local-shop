import re
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, model_validator
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
    wechat_login_enabled: bool = False
    wechat_appid: str = ""
    wechat_app_secret: SecretStr = SecretStr("")
    auth_trusted_proxy_ips: str = ""
    auth_session_seconds: int = Field(default=900, ge=300, le=3600)
    media_root: Path = Path("var/media")
    media_receive_timeout_seconds: float = Field(default=15, ge=0.05, le=120)
    db_statement_timeout_ms: int = Field(default=10000, ge=100, le=60000)
    db_lock_timeout_ms: int = Field(default=3000, ge=100, le=60000)
    db_pool_timeout_seconds: float = Field(default=5, ge=0.05, le=60)

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
        if self.app_env == "production" and not self.wechat_login_enabled:
            raise ValueError(
                "Production requires configured verified identity; development fallback forbidden"
            )
        if self.auth_trusted_proxy_ips:
            try:
                peers = self.auth_trusted_proxy_ips.split(",")
                if len(peers) > 8 or "%" in self.auth_trusted_proxy_ips:
                    raise ValueError
                self.auth_trusted_proxy_ips = ",".join(str(ip_address(x.strip())) for x in peers)
            except ValueError:
                raise ValueError(
                    "AUTH_TRUSTED_PROXY_IPS requires at most eight exact IPs, no CIDR/wildcard"
                ) from None
            if self.dev_auth_enabled:
                raise ValueError("Trusted formal proxy cannot coexist with development identity")
        if self.wechat_login_enabled:
            if (
                not re.fullmatch(r"wx[a-fA-F0-9]{16}", self.wechat_appid)
                or len(self.wechat_app_secret.get_secret_value()) < 16
            ):
                raise ValueError(
                    "WeChat login requires protected project AppID and secret configuration"
                )
        return self
