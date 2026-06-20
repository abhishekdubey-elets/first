"""Auth, settings, article, log, and stats schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


# --- Auth ------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str | None
    role: str


# --- Articles / news feed --------------------------------------------------
class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    title: str | None
    source_name: str | None
    language: str | None
    published_at: datetime | None
    status: str
    relevance_score: float | None
    created_at: datetime


# --- Logs ------------------------------------------------------------------
class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: str
    agent: str | None
    action: str | None
    message: str
    context: dict | None
    created_at: datetime


class SyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    rows_written: int
    rows_failed: int
    message: str | None
    created_at: datetime


# --- Settings --------------------------------------------------------------
class ExportConfig(BaseModel):
    spreadsheet_id: str | None = None
    worksheet_name: str | None = None
    auto_export: bool | None = None


class OpenAiKeyConfig(BaseModel):
    # None/empty clears the key and reverts the pipeline to the local Ollama LLM.
    openai_api_key: str | None = None


class RuntimeSettingsOut(BaseModel):
    spreadsheet_id: str | None
    worksheet_name: str | None
    auto_export: bool
    credentials_uploaded: bool
    llm_provider: str
    llm_model: str
    discovery_interval_seconds: int
    openai_configured: bool = False


# --- Stats / analytics -----------------------------------------------------
class StatsOut(BaseModel):
    total_transfers: int
    today: int
    this_week: int
    this_month: int
    pending: int
    verified: int
    exported: int
    by_state: list[dict]
