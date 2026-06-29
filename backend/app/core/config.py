"""Application configuration for the IAS Transfer Intelligence Dashboard.

All values are typed and validated via pydantic-settings. Import the singleton
``settings`` everywhere instead of reading ``os.environ`` directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# "openai"    -> GPT via the OpenAI API (default — cloud, deployment friendly)
# "anthropic" -> Claude via Anthropic's OpenAI-compatible endpoint (optional)
LLMProvider = Literal["openai", "anthropic"]

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_BACKEND_DIR / ".env"), str(_ROOT_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "IAS Transfer Intelligence Dashboard"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    # --- Security ----------------------------------------------------------
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    JWT_ALGORITHM: str = "HS256"
    FIRST_ADMIN_EMAIL: str = "admin@digitallearning.in"
    FIRST_ADMIN_PASSWORD: str = "ChangeMe123!"
    # Fernet key for at-rest encryption of API keys stored in the DB. Generate
    # with: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""

    # --- Database ----------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+asyncpg://ias:ias_password@localhost:5432/ias_transfers"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://ias:ias_password@localhost:5432/ias_transfers"
    )
    # Require TLS to the database. Set true for managed Postgres (Supabase/Neon).
    DB_SSL: bool = False

    # --- Scheduling --------------------------------------------------------
    # Shared secret for the cron-triggered discovery endpoint
    # (POST /api/v1/agents/run-cycle with an `x-cron-token` header). Set this in
    # the deployment and in the Supabase pg_cron job. No Redis/Celery needed.
    CRON_TOKEN: str = ""

    # --- Discovery ---------------------------------------------------------
    # Suggested cron cadence (seconds) for the discovery cycle. 600 = 10 minutes.
    DISCOVERY_INTERVAL_SECONDS: int = 600
    DISCOVERY_LOOKBACK_HOURS: int = 24
    DISCOVERY_MAX_ARTICLES_PER_RUN: int = 80
    # Comma-separated languages for Google News (e.g. "en,hi,ta").
    DISCOVERY_LANGUAGES: str = "en,hi"
    HTTP_USER_AGENT: str = (
        "IASTransferIntelligenceBot/1.0 (+https://digitallearning.in; research)"
    )
    HTTP_TIMEOUT_SECONDS: int = 20
    RESPECT_ROBOTS_TXT: bool = True

    # --- LLM / extraction --------------------------------------------------
    LLM_PROVIDER: LLMProvider = "openai"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_OUTPUT_TOKENS: int = 4000
    LLM_MAX_INPUT_CHARS: int = 16000

    # OpenAI (default). Set OPENAI_API_KEY via env or the dashboard Settings page.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"

    # Anthropic / Claude (optional) — uses the OpenAI-compatible endpoint.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1/"
    ANTHROPIC_MODEL: str = "claude-opus-4-8"

    # --- RAG chatbot -------------------------------------------------------
    # OpenAI embedding model used to semantically retrieve relevant transfer
    # records for the assistant.
    EMBED_MODEL: str = "text-embedding-3-small"
    CHAT_TOP_K: int = 8           # how many records to ground each answer on
    CHAT_MAX_CONTEXT_CHARS: int = 6000
    # The assistant uses the configured chat model (OPENAI_MODEL by default).
    # Falls back gracefully if it can't generate.
    CHAT_MAX_TOKENS: int = 800
    CHAT_TIMEOUT_SECONDS: int = 60
    # Below this best-semantic-similarity, the local data is considered to not
    # cover the question and a live web search is used instead.
    CHAT_MIN_SIM: float = 0.5
    ENABLE_WEB_FALLBACK: bool = True

    # --- Multimodal / OCR --------------------------------------------------
    # OCR needs the Tesseract + Poppler system binaries, which aren't available
    # on serverless/Vercel — off by default. Enable only on a self-hosted backend
    # that has those binaries (and set the paths below). Fails soft when missing.
    ENABLE_OCR: bool = False
    OCR_LANGUAGES: str = "eng+hin"
    TESSERACT_CMD: str = ""
    POPPLER_PATH: str = ""

    # --- Google Sheets -----------------------------------------------------
    GOOGLE_CREDENTIALS_FILE: str = "/data/secrets/google-credentials.json"
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_WORKSHEET_NAME: str = "Transfers"
    GOOGLE_SHEETS_AUTO_EXPORT: bool = True

    # --- Notifications -----------------------------------------------------
    SLACK_WEBHOOK_URL: str = ""
    GENERIC_WEBHOOK_URL: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = ""
    HIGH_CONFIDENCE_THRESHOLD: float = 0.85

    # --- Storage / processing ---------------------------------------------
    STORAGE_DIR: str = "/data/storage"
    MAX_RETRIES: int = 3
    TASK_TIMEOUT_SECONDS: int = 1800

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def languages(self) -> list[str]:
        return [s.strip() for s in self.DISCOVERY_LANGUAGES.split(",") if s.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
