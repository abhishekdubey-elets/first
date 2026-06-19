"""Multimodal extraction helpers: PDF text + image OCR for government orders.

These power the multimodal requirement — when a transfer order arrives as a PDF
or a scanned image, we pull its text so the Information Extraction Agent can read
it like any article. All functions fail soft and return "" if the optional
dependency or system binary is missing, so the core pipeline never hard-fails.
"""
from __future__ import annotations

import io

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _download(url: str) -> bytes | None:
    try:
        resp = httpx.get(
            url,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as exc:  # noqa: BLE001
        log.warning("ocr_download_failed", url=url, error=str(exc))
        return None


def extract_pdf_text(url: str) -> str:
    """Pull selectable text from a PDF; OCR scanned pages when enabled."""
    data = _download(url)
    if not data:
        return ""
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("pdf_parse_failed", url=url, error=str(exc))

    if text.strip():
        return text

    # Scanned PDF with no text layer → OCR each page image if enabled.
    if settings.ENABLE_OCR:
        return _ocr_pdf(data, url)
    return ""


def _ocr_pdf(data: bytes, url: str) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(data)
        return "\n".join(
            pytesseract.image_to_string(p, lang=settings.OCR_LANGUAGES) for p in pages
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("pdf_ocr_failed", url=url, error=str(exc))
        return ""


def extract_image_text(url: str) -> str:
    """OCR a (possibly scanned notification) image."""
    if not settings.ENABLE_OCR:
        return ""
    data = _download(url)
    if not data:
        return ""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img, lang=settings.OCR_LANGUAGES)
    except Exception as exc:  # noqa: BLE001
        log.warning("image_ocr_failed", url=url, error=str(exc))
        return ""
