"""Outbound notifications: Slack, generic webhook, and email (SMTP).

All channels are best-effort and fail soft — a notification failure must never
break the pipeline. Configure via env; unconfigured channels are skipped.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _post_json(url: str, payload: dict) -> None:
    try:
        httpx.post(url, json=payload, timeout=10)
    except Exception as exc:  # noqa: BLE001
        log.warning("notification_failed", url=url, error=str(exc))


def notify(title: str, message: str, *, level: str = "info") -> None:
    """Fan a notification out to every configured channel."""
    if settings.SLACK_WEBHOOK_URL:
        emoji = {"info": ":information_source:", "success": ":white_check_mark:",
                 "warning": ":warning:", "error": ":rotating_light:"}.get(level, "")
        _post_json(settings.SLACK_WEBHOOK_URL, {"text": f"{emoji} *{title}*\n{message}"})

    if settings.GENERIC_WEBHOOK_URL:
        _post_json(
            settings.GENERIC_WEBHOOK_URL,
            {"title": title, "message": message, "level": level},
        )

    if settings.SMTP_HOST and settings.ALERT_EMAIL_TO:
        _send_email(title, message)


def _send_email(subject: str, body: str) -> None:
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[IAS Transfer] {subject}"
        msg["From"] = settings.SMTP_USER or "noreply@digitallearning.in"
        msg["To"] = settings.ALERT_EMAIL_TO
        msg.set_content(body)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        log.warning("email_failed", error=str(exc))


def notify_new_transfer(t) -> None:
    move = f"{t.previous_district or t.previous_posting or '?'} → {t.new_district or t.new_posting or '?'}"
    level = "success" if t.confidence_score >= settings.HIGH_CONFIDENCE_THRESHOLD else "info"
    notify(
        f"New IAS transfer detected: {t.officer_name}",
        f"{move}  |  State: {t.state or '?'}  |  Confidence: {t.confidence_score:.0%}\n{t.source_url or ''}",
        level=level,
    )
