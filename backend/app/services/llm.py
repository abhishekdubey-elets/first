"""Unified LLM client (cloud).

Two providers share one small interface (``complete_json`` / ``complete_text``):

* ``openai``    — GPT via the OpenAI API (default).
* ``anthropic`` — Claude via the official Anthropic SDK (Messages API).

Embeddings (for RAG retrieval) always use OpenAI's embedding model — Anthropic
has no embeddings endpoint. The active provider/model is chosen from
``settings`` but can be overridden per call (e.g. from the Settings page) by
passing ``provider``/``model``.
"""
from __future__ import annotations

import json
from typing import Any

from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.config import LLMProvider, settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMError(Exception):
    """Raised when an LLM completion fails."""


class LLMConfigError(LLMError):
    """Missing/invalid provider configuration: retrying cannot help."""


_RETRY = dict(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20),
              retry=retry_if_not_exception_type(LLMConfigError), reraise=True)


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


# --- OpenAI -----------------------------------------------------------------
def _openai_client():
    from openai import OpenAI

    key = _openai_key()
    if not key:
        raise LLMConfigError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=key)


def _openai_chat(system_prompt: str, user_prompt: str, *, model: str, temperature: float,
                 max_tokens: int, timeout: float | None, json_mode: bool) -> str:
    client = _openai_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM completion failed (openai/{model}): {exc}") from exc
    return (resp.choices[0].message.content or "").strip()


# --- Anthropic ---------------------------------------------------------------
def _anthropic_client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise LLMConfigError("The 'anthropic' package is not installed.") from exc

    if not settings.ANTHROPIC_API_KEY:
        raise LLMConfigError("ANTHROPIC_API_KEY is not configured.")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _anthropic_chat(system_prompt: str, user_prompt: str, *, model: str,
                    max_tokens: int, timeout: float | None, json_mode: bool) -> str:
    """One Claude Messages API call, returning the concatenated text blocks.

    ``temperature`` is deliberately not sent (rejected by current models);
    ``effort`` steers cost. Server-side refusal fallbacks are enabled so a
    policy decline on the primary model is re-run on a fallback model inside
    the same request instead of dropping the article.
    """
    import anthropic

    client = _anthropic_client()
    if timeout is not None:
        client = client.with_options(timeout=timeout)
    system = system_prompt
    if json_mode:
        system = system_prompt + "\n\nRespond with a single JSON object and nothing else."
    try:
        resp = client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"effort": settings.ANTHROPIC_EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
            anthropic.NotFoundError) as exc:
        raise LLMConfigError(f"Anthropic configuration error ({model}): {exc}") from exc
    except anthropic.BadRequestError as exc:
        raise LLMError(f"Anthropic rejected the request ({model}): {exc}") from exc
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise LLMError(f"LLM completion failed (anthropic/{model}): {exc}") from exc

    if resp.stop_reason == "refusal":
        raise LLMError(f"Anthropic declined the request ({model}): "
                       f"{getattr(resp.stop_details, 'category', None)}")
    if resp.stop_reason == "max_tokens":
        # Not fatal: the JSON parser recovers every complete object. Logged so a
        # too-small cap shows up in the Space logs instead of as lost records.
        log.warning("llm_output_truncated", model=model, max_tokens=max_tokens)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# --- Public API ----------------------------------------------------------------
@retry(**_RETRY)
def complete_json(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: LLMProvider | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run a JSON completion and return the parsed object.

    Robust to models that wrap JSON in markdown fences or surrounding prose.
    """
    provider = provider or active_provider()
    model = model or active_model(provider)
    if provider == "openai":
        content = _openai_chat(system_prompt, user_prompt, model=model,
                               temperature=settings.LLM_TEMPERATURE,
                               max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                               timeout=None, json_mode=True)
    elif provider == "anthropic":
        content = _anthropic_chat(system_prompt, user_prompt, model=model,
                                  max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                                  timeout=None, json_mode=True)
    else:
        raise LLMConfigError(f"Unknown LLM provider: {provider}")
    return _parse_json(content or "{}")


@retry(**_RETRY)
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
    max_tokens = max_tokens or settings.LLM_MAX_OUTPUT_TOKENS
    if provider == "openai":
        return _openai_chat(system_prompt, user_prompt, model=model, temperature=temperature,
                            max_tokens=max_tokens, timeout=timeout, json_mode=False)
    if provider == "anthropic":
        return _anthropic_chat(system_prompt, user_prompt, model=model,
                               max_tokens=max_tokens, timeout=timeout, json_mode=False)
    raise LLMConfigError(f"Unknown LLM provider: {provider}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
       retry=retry_if_not_exception_type(LLMConfigError), reraise=True)
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with the OpenAI embedding model (used for RAG retrieval)."""
    if not texts:
        return []
    key = _openai_key()
    if not key:
        raise LLMConfigError("OPENAI_API_KEY is not configured (needed for embeddings).")
    from openai import OpenAI

    client = OpenAI(api_key=key)
    out: list[list[float]] = []
    # The embeddings endpoint caps one request at 2048 inputs.
    for i in range(0, len(texts), 1000):
        chunk = texts[i : i + 1000]
        try:
            resp = client.embeddings.create(model=settings.EMBED_MODEL, input=chunk)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Embedding failed ({settings.EMBED_MODEL}): {exc}") from exc
        out.extend(d.embedding for d in resp.data)
    return out


TRUNCATED_KEY = "_truncated"


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
    salvaged = _salvage_truncated(content[start:] if start != -1 else content)
    if salvaged is not None:
        return salvaged
    raise LLMError(f"Model did not return valid JSON: {content[:300]}")


def _salvage_truncated(content: str, max_attempts: int = 60) -> dict[str, Any] | None:
    """Recover the complete objects from a reply cut off by the token limit.

    A reshuffle reply looks like ``{"is_transfer_news": true, "transfers": [
    {...}, {...}, {"officer_name": "Sh`` — everything before the last complete
    object is valid. Walk back through the closing braces and try to close the
    array and the envelope at each one. The result is flagged with
    ``_truncated`` so the caller can log how much it kept.
    """
    cut = content.rfind("}")
    attempts = 0
    while cut > 0 and attempts < max_attempts:
        attempts += 1
        head = content[: cut + 1]
        for tail in ("]}", "}", "]}}", "}}"):
            try:
                obj = json.loads(head + tail)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                obj[TRUNCATED_KEY] = True
                return obj
        cut = content.rfind("}", 0, cut)
    return None
