"""Application configuration.

Every tunable value is read from the environment (see `.env.example`).
Nothing trading-related, and no credential, is ever hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "Prajwal Trading Platform"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    TIMEZONE: str = "Asia/Kolkata"

    # --- Security ---
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_MIN_LENGTH: int = 10

    # --- Database ---
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "trading"
    POSTGRES_PASSWORD: str = "trading"
    POSTGRES_DB: str = "prajwal_trading"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # --- SAFETY SWITCHES ---------------------------------------------------
    # Live execution is OFF by default. Flipping these is not sufficient to
    # place a real order: `app.brokers` has no live execution adapter in
    # Phase 1, and `assert_live_execution_allowed()` raises regardless.
    LIVE_TRADING_ENABLED: bool = False
    EXECUTION_MODE: Literal["paper", "live"] = "paper"
    ALLOW_LIVE_ORDER_PLACEMENT: bool = False

    # --- Trading defaults ---
    DEFAULT_CAPITAL: float = 1_000_000.0
    MAX_RISK_PER_TRADE_PCT: float = 1.0
    MAX_DAILY_LOSS_PCT: float = 3.0
    MAX_OPEN_POSITIONS: int = 5
    MAX_TRADES_PER_DAY: int = 20
    MAX_CAPITAL_UTILISATION_PCT: float = 80.0

    # --- Broker ---
    BROKER_NAME: str = "zerodha"
    KITE_API_KEY: str = ""
    KITE_API_SECRET: str = ""
    KITE_ACCESS_TOKEN: str = ""
    KITE_REQUEST_TOKEN: str = ""

    # --- AI ---
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5-5"
    AI_MONTHLY_BUDGET_USD: float = 20.0
    AI_ENABLED: bool = False

    # --- Notifications ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # --- Data import ---
    SQLITE_SOURCE_PATH: str = "./data/sqlite_source/equity_1min.sqlite"
    IMPORT_BATCH_SIZE: int = 50_000

    # ------------------------------------------------------------------ #

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def ai_configured(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY) and self.AI_ENABLED

    @property
    def broker_configured(self) -> bool:
        return bool(self.KITE_API_KEY and self.KITE_API_SECRET)

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
