"""Unified LLM client (cloud).

A single OpenAI-compatible code path serves two providers:

* ``openai``    — GPT via the OpenAI API (default).
* ``anthropic`` — Claude via Anthropic's OpenAI-compatible endpoint (optional).

Embeddings (for RAG retrieval) use OpenAI's embedding model. The active
provider/model is chosen from ``settings`` but can be overridden per call
(e.g. from the Settings page) by passing ``provider``/``model``.
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
    """The effective provider: runtime-selected (Settings page) else env default."""
    from app.services.app_settings import get_export_config

    return get_export_config().get("llm_provider") or settings.LLM_PROVIDER


def is_available(provider: LLMProvider | None = None) -> bool:
    provider = provider or active_provider()
    if provider == "openai":
        return bool(_openai_key())
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    return False


def active_model(provider: LLMProvider | None = None) -> str:
    provider = provider or active_provider()
    return {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
    }[provider]


def _client(provider: LLMProvider):
    from openai import OpenAI

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
    # response_format JSON mode is supported by OpenAI; Anthropic's compat layer
    # ignores unknown fields gracefully.
    kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM completion failed ({provider}/{model}): {exc}") from exc

    content = (resp.choices[0].message.content or "{}").strip()
    return _parse_json(content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def complete_text(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: LLMProvider | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    """Plain free-text chat completion (used by the RAG assistant)."""
    provider = provider or active_provider()
    model = model or active_model(provider)
    client = _client(provider)
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Chat completion failed ({provider}/{model}): {exc}") from exc
    return (resp.choices[0].message.content or "").strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with the OpenAI embedding model (used for RAG retrieval)."""
    from openai import OpenAI

    if not texts:
        return []
    key = _openai_key()
    if not key:
        raise LLMError("OPENAI_API_KEY is not configured (needed for embeddings).")
    client = OpenAI(api_key=key)
    try:
        resp = client.embeddings.create(model=settings.EMBED_MODEL, input=texts)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Embedding failed ({settings.EMBED_MODEL}): {exc}") from exc
    return [d.embedding for d in resp.data]


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
