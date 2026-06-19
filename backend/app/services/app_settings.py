"""Runtime-mutable settings persisted to a JSON file next to the secrets volume.

Values the admin changes from the UI at runtime (spreadsheet id, worksheet,
auto-export toggle, active LLM provider/model) that don't belong in the
immutable env-based ``Settings``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings

_STORE_PATH = Path(settings.GOOGLE_CREDENTIALS_FILE).parent / "app_settings.json"

_DEFAULTS: dict[str, Any] = {
    "spreadsheet_id": settings.GOOGLE_SHEET_ID,
    "worksheet_name": settings.GOOGLE_WORKSHEET_NAME,
    "auto_export": settings.GOOGLE_SHEETS_AUTO_EXPORT,
    "llm_provider": settings.LLM_PROVIDER,
    "llm_model": "",
    "discovery_interval_seconds": settings.DISCOVERY_INTERVAL_SECONDS,
}


def _read() -> dict[str, Any]:
    if _STORE_PATH.exists():
        try:
            return {**_DEFAULTS, **json.loads(_STORE_PATH.read_text())}
        except (json.JSONDecodeError, OSError):
            return dict(_DEFAULTS)
    return dict(_DEFAULTS)


def _write(data: dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2))


def get_export_config() -> dict[str, Any]:
    data = _read()
    data["credentials_uploaded"] = Path(settings.GOOGLE_CREDENTIALS_FILE).exists()
    return data


def update_export_config(**changes: Any) -> dict[str, Any]:
    data = _read()
    for key, value in changes.items():
        if value is not None and key in _DEFAULTS:
            data[key] = value
    _write(data)
    return get_export_config()
