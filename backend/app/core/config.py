"""Application configuration.

Everything is environment driven so the same image runs locally (SQLite) and in
production (Postgres) without a code change - see SYSTEM_DESIGN.md section 9.
"""

import json
from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- app -----------------------------------------------------------------
    app_name: str = "Signal Clone API"
    api_prefix: str = "/api/v1"
    debug: bool = False

    # --- database ------------------------------------------------------------
    # SQLAlchemy is DB agnostic: swapping this URL for
    # postgresql+asyncpg://... is the entire Postgres migration.
    database_url: str = "sqlite+aiosqlite:///./signal.db"

    # --- auth ----------------------------------------------------------------
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- otp (mocked) --------------------------------------------------------
    mock_otp_code: str = "123456"
    otp_expire_seconds: int = 300

    # --- cors ----------------------------------------------------------------
    # Kept as a raw string on purpose: pydantic-settings JSON-decodes complex
    # types straight out of the environment, before any validator runs, so a
    # plain "a,b,c" value (what every PaaS dashboard produces) would blow up at
    # import time. Parsing lives in `cors_origin_list` instead.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- connection pool -----------------------------------------------------
    # Defaults are sized for the concurrency a chat workload actually produces.
    # SQLAlchemy ships pool_size=5/max_overflow=10, which caps the server at ~15
    # in-flight transactions - under a send burst that queue *is* the latency.
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_recycle_seconds: int = 1800
    # A per-checkout "SELECT 1". Worth it across a flaky network, pure overhead
    # against a local or same-VPC database, so it is opt-in.
    db_pool_pre_ping: bool = False

    # --- multi-node ----------------------------------------------------------
    # Set this and the app switches from in-process fan-out to Redis Pub/Sub,
    # which is the whole difference between one node and N. Unset = single node.
    redis_url: str | None = None
    node_id: str | None = None

    # --- behaviour -----------------------------------------------------------
    seed_on_startup: bool = True
    max_message_length: int = 8192

    # --- attachments ---------------------------------------------------------
    # Local disk for the demo. Swapping in S3/R2 means replacing the storage
    # helper in app/services/attachment_service.py - nothing else changes.
    media_root: str = "media"
    media_url_prefix: str = "/media"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    # How often the sweeper hard-deletes expired (disappearing) messages.
    disappear_sweep_seconds: int = 20
    rate_limit_messages: int = 20
    rate_limit_window_seconds: int = 10
    typing_relay_ttl_seconds: int = 5

    @cached_property
    def cors_origin_list(self) -> list[str]:
        """Accept either a comma separated list or a JSON array."""
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            return [str(origin) for origin in json.loads(raw)]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def multi_node(self) -> bool:
        return bool(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
