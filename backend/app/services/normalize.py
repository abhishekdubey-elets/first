"""Field normalisers shared by extraction, enrichment and the public feed.

Everything here is pure and cheap: no I/O, no database. Keeping the rules in
one place means the LLM's output, the web-enrichment output and the feed all
agree on what a batch year, a district or a government-order link looks like.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from dateutil import parser as dateparser

from app.core.india import canonical_state

_YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
_NON_ALNUM = re.compile(r"[^a-z0-9ऀ-ॿ]+")


def clean(value: str | None) -> str:
    return (value or "").strip()


def norm_name(value: str | None) -> str:
    """Officer-name key: case/punctuation/spacing-insensitive, keeps Devanagari."""
    return _NON_ALNUM.sub("", clean(value).lower())


def norm_batch(value: str | None) -> str | None:
    """'2009 batch', '2023 बैच', 'IAS 2009' -> '2009'. Anything else -> None.

    Batch is only ever a four-digit year; everything the model wraps around it
    is noise that breaks grouping and filtering.
    """
    m = _YEAR.search(clean(value))
    return m.group(0) if m else None


def strip_state_suffix(value: str | None) -> str | None:
    """'Imphal, Manipur' -> 'Imphal'. Leaves 'Imphal' and 'Manipur' alone.

    Models like to write a district as "district, state"; the state has its
    own column and the suffix breaks district grouping.
    """
    text = clean(value)
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    while len(parts) > 1 and canonical_state(parts[-1]):
        parts.pop()
    return ", ".join(parts) or None


def parse_loose_date(raw: str | None) -> datetime | None:
    """Parse a free-text date, rejecting anything with a missing component.

    ``transfer_date`` is copied verbatim from the article, so it can be
    "15 August 2026", "2026-08-15", "with immediate effect" or "Monday".
    Parsing twice with different defaults and keeping the result only when both
    agree rejects strings that never specified a day or a month, which would
    otherwise silently inherit today's.
    """
    text = clean(raw)
    if not text or not any(ch.isdigit() for ch in text):
        return None
    try:
        a = dateparser.parse(text, dayfirst=True, default=datetime(2000, 1, 1))
        b = dateparser.parse(text, dayfirst=True, default=datetime(2001, 6, 15))
    except (ValueError, OverflowError, TypeError):
        return None
    if a is None or b is None or a.date() != b.date():
        return None
    return a


# Role grouping. Order matters: "Chief Secretary" must beat "Secretary", and
# "Deputy Commissioner" (a Collector by another name) must beat "Commissioner".
ROLE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Chief Secretary", ("chief secretary", "मुख्य सचिव")),
    ("District Magistrate / Collector", (
        "district magistrate", "collector", "deputy commissioner", " dm ",
        "जिलाधिकारी", "कलेक्टर", "जिला मजिस्ट्रेट", "उपायुक्त",
    )),
    ("Sub-Divisional Magistrate", (
        "sub-divisional", "sub divisional", " sdm", "sdm ", "sdm,", "(sdm",
        "एसडीएम", "उपखंड अधिकारी", "अनुविभागीय",
    )),
    ("Commissioner", ("commissioner", "आयुक्त")),
    ("Secretary", ("secretary", "सचिव")),
    ("Managing Director / CEO", (
        "managing director", "chief executive", " ceo", "ceo,", "vice chairman",
        "प्रबंध निदेशक", "मुख्य कार्यपालन",
    )),
    ("Director", ("director", "निदेशक")),
    ("Chairman", ("chairman", "chairperson", "अध्यक्ष")),
)


def role_text(new_posting, current_designation, new_district) -> str:
    """The post a record describes, with sensible fallbacks."""
    return (
        clean(new_posting)
        or clean(current_designation)
        or (f"Collector, {clean(new_district)}" if clean(new_district) else "")
        or "IAS Officer"
    )


def role_group_of(role: str | None) -> str:
    padded = f" {clean(role).lower()} "
    for label, needles in ROLE_GROUPS:
        if any(n in padded for n in needles):
            return label
    return "Other"


# --- government-order links --------------------------------------------------
_GOV_DOMAINS = ("gov.in", "nic.in", "india.gov.in")
# Whole-word only: "border" must not match "order", "adoption" must not match "dopt".
_ORDER_WORDS = re.compile(
    r"(?<![a-z])(orders?|notifications?|gazette|dopt|circulars?|transfer[-_]?(list|order))(?![a-z])"
)


def looks_like_gov_order(href: str | None, article_host: str | None = None) -> bool:
    """Is this link plausibly a government order, not just any page?

    Rules, in order: PDFs qualify; a government domain qualifies unless it is
    the bare homepage; the publisher's own pages never qualify (an outlet's
    "related" links are not orders); otherwise the path must contain a whole
    word such as "order" or "notification".
    """
    text = clean(href)
    if not text:
        return False
    try:
        parts = urlparse(text)
    except ValueError:
        return False
    host, path = parts.netloc.lower(), parts.path.lower()
    if not path or path == "/":
        return False
    if path.endswith(".pdf"):
        return True
    if any(host == d or host.endswith("." + d) for d in _GOV_DOMAINS):
        return True
    if article_host and host == article_host.lower():
        return False
    return bool(_ORDER_WORDS.search(path))
