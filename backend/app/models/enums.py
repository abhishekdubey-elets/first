"""Shared enums for the domain models."""
from __future__ import annotations

import enum


class ArticleStatus(str, enum.Enum):
    """Lifecycle of a discovered article as it moves through the pipeline."""

    DISCOVERED = "discovered"      # found by discovery agent, not yet fetched
    EXTRACTED = "extracted"        # full text/media pulled
    PARSED = "parsed"              # LLM information extraction done
    IRRELEVANT = "irrelevant"      # not an IAS transfer after inspection
    FAILED = "failed"


class TransferStatus(str, enum.Enum):
    """Lifecycle of a structured transfer record."""

    PENDING = "pending"            # extracted, awaiting validation
    VERIFIED = "verified"          # confirmed (single or multi-source)
    CONFLICTED = "conflicted"      # sources disagree — needs review
    EXPORTED = "exported"          # written to Google Sheets
    EXPORT_FAILED = "export_failed"


class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class SyncStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"
