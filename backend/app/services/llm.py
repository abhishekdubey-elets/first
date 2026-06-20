"""Unified LLM client.

A single OpenAI-compatible code path serves three providers:

* ``ollama``    — a local open-source model (default; no API key, fully offline).
                  This mirrors the local-model setup used by the sibling
                  transcript dashboard.
* ``openai``    — GPT via the OpenAI API.
* ``anthropic`` — Claude via Anthropic's OpenAI-compatible endpoint (optional).

The active provider/model is chosen from ``settings`` but can be overridden per
call (e.g. from the Settings page) by passing ``provider``/``model``.
"""
from __future__ import annotations

import json
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import LLMProvider, settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMError(Exception):
    """Raised when an LLM completion fails."""


def _openai_key() -> str:
    """OpenAI key from runtime settings (Settings page) or, failing that, env."""
    from app.services.app_settings import get_openai_key

    return get_openai_key() or settings.OPENAI_API_KEY


def active_provider() -> LLMProvider:
    """The effective provider: runtime-selected (Settings page) else env default.

    With no OpenAI key supplied this stays ``ollama`` — the original behaviour.
    """
    from app.services.app_settings import get_export_config

    return get_export_config().get("llm_provider") or settings.LLM_PROVIDER


def is_available(provider: LLMProvider | None = None) -> bool:
    provider = provider or active_provider()
    if provider == "ollama":
        return True  # assumed reachable; call fails loudly if not
    if provider == "openai":
        return bool(_openai_key())
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    return False


def active_model(provider: LLMProvider | None = None) -> str:
    provider = provider or active_provider()
    return {
        "ollama": settings.OLLAMA_MODEL,
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
    }[provider]


def _client(provider: LLMProvider):
    from openai import OpenAI

    if provider == "ollama":
        return OpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")
    if provider == "openai":
        key = _openai_key()
        if not key:
            raise LLMError("OPENAI_API_KEY is not configured.")
        return OpenAI(api_key=key)
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise LLMError("ANTHROPIC_API_KEY is not configured.")
        return OpenAI(
            base_url=settings.ANTHROPIC_BASE_URL, api_key=settings.ANTHROPIC_API_KEY
        )
    raise LLMError(f"Unknown LLM provider: {provider}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def complete_json(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: LLMProvider | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run a JSON-mode completion and return the parsed object.

    Robust to models that wrap JSON in markdown fences (common with small
    local models that don't honour response_format).
    """
    provider = provider or active_provider()
    model = model or active_model(provider)
    client = _client(provider)

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # response_format JSON mode is supported by OpenAI and Ollama; Anthropic's
    # compat layer ignores unknown fields gracefully.
    kwargs["response_format"] = {"type": "json_object"}
    if provider == "ollama":
        kwargs["extra_body"] = {
            "options": {"num_ctx": settings.OLLAMA_NUM_CTX},
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM completion failed ({provider}/{model}): {exc}") from exc

    content = (resp.choices[0].message.content or "{}").strip()
    return _parse_json(content)


def _parse_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences / surrounding prose and retry on the first {...}.
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError(f"Model did not return valid JSON: {content[:300]}")
