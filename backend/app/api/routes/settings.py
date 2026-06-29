"""Settings page: runtime config, Google credentials upload, model selection."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_current_user, require_admin
from app.core.config import settings as env_settings
from app.services import llm
from app.services.app_settings import (
    get_export_config,
    set_openai_key,
    update_export_config,
)
from app.schemas.common import ExportConfig, OpenAiKeyConfig, RuntimeSettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=RuntimeSettingsOut)
async def read_settings(_: object = Depends(get_current_user)):
    cfg = get_export_config()
    return RuntimeSettingsOut(
        spreadsheet_id=cfg.get("spreadsheet_id"),
        worksheet_name=cfg.get("worksheet_name"),
        auto_export=cfg.get("auto_export", False),
        credentials_uploaded=cfg.get("credentials_uploaded", False),
        llm_provider=cfg.get("llm_provider", env_settings.LLM_PROVIDER),
        llm_model=cfg.get("llm_model") or llm.active_model(),
        discovery_interval_seconds=cfg.get(
            "discovery_interval_seconds", env_settings.DISCOVERY_INTERVAL_SECONDS
        ),
        openai_configured=cfg.get("openai_configured", False),
    )


@router.put("/export")
async def update_export(payload: ExportConfig, _: object = Depends(require_admin)):
    return update_export_config(
        spreadsheet_id=payload.spreadsheet_id,
        worksheet_name=payload.worksheet_name,
        auto_export=payload.auto_export,
    )


@router.put("/openai")
async def update_openai_key(
    payload: OpenAiKeyConfig, _: object = Depends(require_admin)
):
    """Set or clear the optional OpenAI API key.

    Supplying a key switches extraction to OpenAI; clearing it reverts to the
    local Ollama model (the original, key-free behaviour).
    """
    return set_openai_key(payload.openai_api_key)


@router.post("/credentials")
async def upload_credentials(
    file: UploadFile = File(...), _: object = Depends(require_admin)
):
    """Upload the Google service-account JSON to the secrets volume."""
    dest = Path(env_settings.GOOGLE_CREDENTIALS_FILE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    return {"uploaded": True, "path": str(dest)}


@router.get("/models")
async def available_models(_: object = Depends(get_current_user)):
    """Which providers are usable given the current env (for the model picker)."""
    return {
        "providers": [
            {"id": "openai", "label": "OpenAI GPT",
             "available": llm.is_available("openai"), "model": env_settings.OPENAI_MODEL},
            {"id": "anthropic", "label": "Anthropic Claude",
             "available": llm.is_available("anthropic"), "model": env_settings.ANTHROPIC_MODEL},
        ],
        "active": llm.active_provider(),
    }
