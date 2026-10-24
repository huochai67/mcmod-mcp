"""Configuration for the mcmod API, MCP server and CLI."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "mcmod-mcp/0.1 (SSR reader; +https://www.mcmod.cn/robots.txt; "
    "respects rate limits)"
)


class Settings(BaseSettings):
    """Runtime settings, read from environment variables and ``.env``.

    All variables use the ``MCMOD_`` prefix, e.g. ``MCMOD_DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="MCMOD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Upstream
    base_url: str = "https://www.mcmod.cn"
    search_url: str = "https://search.mcmod.cn"
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = Field(default=20.0, gt=0)
    min_interval: float = Field(
        default=1.0,
        ge=0,
        description="Minimum seconds between two upstream HTTP requests.",
    )
    max_retries: int = Field(default=2, ge=0, le=5)

    # Database (SQLite by default; MariaDB/MySQL via SQLAlchemy URL)
    database_url: str = "sqlite:///./mcmod.db"
    database_echo: bool = False
    sqlite_timeout: float = Field(default=30.0, gt=0)

    # Result cache
    cache_enabled: bool = True
    cache_ttl_search: int = Field(default=900, ge=0)
    cache_ttl_list: int = Field(default=1800, ge=0)
    cache_ttl_detail: int = Field(default=21600, ge=0)
    cache_ttl_meta: int = Field(default=86400, ge=0)

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_base: str = "http://127.0.0.1:8000"
    admin_token: str = ""
    cors_origins: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("database_url must not be empty")
        # SQLAlchemy does not ship a "mariadb" dialect under that name.
        for prefix in ("mariadb+pymysql://", "mariadb://"):
            if value.startswith(prefix):
                return "mysql+pymysql://" + value[len(prefix) :]
        if value.startswith("mysql://"):
            return "mysql+pymysql://" + value[len("mysql://") :]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> Path | None:
        if not self.is_sqlite:
            return None
        raw = self.database_url.removeprefix("sqlite:///")
        if raw in ("", ":memory:"):
            return None
        return Path(raw)

    @property
    def backend_name(self) -> str:
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        if "pymysql" in self.database_url or self.database_url.startswith("mysql"):
            return "mariadb"
        return "database"

