"""Helper to persist agent actions to the SystemLog table (audit trail).

Agents call ``log_event(...)`` so every action is searchable in the dashboard's
System Logs page, in addition to structured stdout logging.
"""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.enums import LogLevel
from app.models.log import SystemLog

_stdout = get_logger("agent")


def log_event(
    db,
    *,
    level: LogLevel = LogLevel.INFO,
    agent: str,
    action: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Write one audit row. ``db`` is a sync Session (worker/agent context)."""
    db.add(
        SystemLog(
            level=level,
            agent=agent,
            action=action,
            message=message,
            context=context or {},
        )
    )
    db.flush()
    _stdout.info(
        "agent_event",
        audit_level=level.value,
        agent=agent,
        action=action,
        message=message,
        context=context or {},
    )
