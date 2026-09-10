"""Runtime settings, all driven by environment variables (loaded from .env)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    feeds_dir: Path = Field(default=Path("./feeds"), alias="FEEDS_DIR")

    # publish step — stays off until phase 2
    publish_mode: str = Field(default="off", alias="PUBLISH_MODE")
    wp_mysql_host: str | None = Field(default=None, alias="WP_MYSQL_HOST")
    wp_mysql_port: int = Field(default=3306, alias="WP_MYSQL_PORT")
    wp_mysql_user: str | None = Field(default=None, alias="WP_MYSQL_USER")
    wp_mysql_password: str | None = Field(default=None, alias="WP_MYSQL_PASSWORD")
    wp_mysql_db: str | None = Field(default=None, alias="WP_MYSQL_DB")

    # how long an offer may go unseen in a feed before it's considered gone
    freshness_missed_runs: int = 3


def load() -> Settings:
    return Settings()  # type: ignore[call-arg]
