"""Shared pytest fixtures and configuration.

These tests are intentionally dependency-light and DB-free where possible so
they run reliably in CI without a live Postgres/Redis/Ollama. We set safe
placeholder env vars *before* the app config is imported so that importing
``app.core.config`` never fails for want of a secret.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the backend package importable when pytest is invoked from backend/.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Provide harmless defaults so config import is never blocked.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
# A real (throwaway) Fernet key: anything else makes encrypt_secret() raise.
os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("ENABLE_INPROCESS_SCHEDULER", "0")

import pytest  # noqa: E402


class _FakeArticle:
    """Minimal stand-in for an Article ORM row used by extracted transfers."""

    def __init__(self, url="https://example.com/a", source_name="Example", id=1):
        self.url = url
        self.source_name = source_name
        self.id = id


@pytest.fixture
def fake_article():
    return _FakeArticle()
