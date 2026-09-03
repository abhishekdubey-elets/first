"""Information Extraction Agent.

Reads the full article text and returns zero or more structured transfer records
using the configured LLM. The prompt enforces a strict JSON schema and a hard
"return null, never hallucinate" rule. Output is validated with Pydantic before
it ever reaches the database.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.sources import source_weight
from app.core.config import settings
from app.core.india import canonical_state
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel
from app.schemas.transfer import ExtractedTransfer, ExtractionResult
from app.services import llm

# Values models sometimes wrongly drop into district/posting fields — these are
# the order's nature or generic labels, not real places/titles. Nulled out so
# the dashboard's From/To columns never show them.
_PLACEHOLDERS = {
    "new posting", "previous posting", "current posting", "present posting",
    "posting", "new district", "previous district", "new role", "same posting",
    "extension of service", "extension of service period", "service extension",
    "extension", "promotion", "promoted", "transfer", "transferred",
    "transfer order", "reshuffle", "repatriation", "repatriated", "deputation",
    "awaiting posting", "posting awaited", "await posting", "not specified",
    "not mentioned", "not available", "na", "n/a", "tba", "to be decided",
    "to be determined", "unknown", "none", "nil", "new", "district", "officer",
    "ias officer", "same", "no change", "vacant",
}


def _clean_field(v: str | None) -> str | None:
    """Null out generic-label / order-nature junk in a place/title field."""
    if not v:
        return None
    s = v.strip()
    norm = s.lower().rstrip(" .,:;-–—")
    if not norm or norm in _PLACEHOLDERS:
        return None
    return s


def _sanitize(t: ExtractedTransfer) -> ExtractedTransfer:
    t.previous_posting = _clean_field(t.previous_posting)
    t.new_posting = _clean_field(t.new_posting)
    # If a district is actually a state name, promote it to state (if empty) and
    # null the district so state names never count as districts.
    for fld in ("previous_district", "new_district"):
        raw = _clean_field(getattr(t, fld))
        if raw and canonical_state(raw):
            if not t.state:
                t.state = canonical_state(raw)
            raw = None
        setattr(t, fld, raw)
    # A "from == to" is a no-op move (hallucinated) — drop the previous side.
    if t.previous_district and t.new_district and \
            t.previous_district.strip().lower() == t.new_district.strip().lower():
        t.previous_district = None
    if t.previous_posting and t.new_posting and \
            t.previous_posting.strip().lower() == t.new_posting.strip().lower():
        t.previous_posting = None
    return t


SYSTEM_PROMPT = (
    "You are a precise civil-service news analyst specialising in Indian "
    "Administrative Service (IAS) officer transfers and postings. You read news "
    "articles and government orders and extract STRUCTURED data about officer "
    "transfers. Rules:\n"
    "1. SCOPE — extract transfers / postings / appointments of Indian **IAS "
    "(Indian Administrative Service)** officers and senior state civil-service "
    "administrators in IAS-type posts (District Magistrate / Collector, "
    "Commissioner, Secretary, SDM, ADM, CEO of a district body). Set "
    "is_transfer_news=false when the article is NOT that: a foreign country or "
    "official (e.g. Bangladesh, Sylhet, Nepal), other services or staff (IPS/"
    "police, engineers, doctors, teachers, accountants, clerks, bank or corporate "
    "employees, university/college appointments), or a non-posting event "
    "(vigilance raid, arrest, probe, award, death). If it plausibly concerns an "
    "IAS-level officer's posting, INCLUDE it even when details are sparse — leave "
    "unknown fields null rather than dropping the record. In a mixed reshuffle "
    "(IAS + others) return only the IAS-level officers. Only extract information "
    "actually stated; NEVER hallucinate.\n"
    "1a. Any state/cadre you DO report must be an Indian state/UT; if the only "
    "location mentioned is clearly foreign (e.g. Sylhet), treat the article as "
    "out of scope. A missing/unknown state is fine — keep the record, state=null.\n"
    "2. Capture the officer's PREVIOUS posting and district whenever the text "
    "implies them — e.g. 'transferred from <place>', 'currently <role>', "
    "'<District> Collector/DM', 'replacing / in place of / vice <officer>', "
    "'shifted from X to Y'. Put the prior office/role in previous_posting and the "
    "prior district in previous_district; do the same for new_posting/new_district "
    "for the destination.\n"
    "3. If a field is genuinely not stated, return null. Do NOT output placeholder "
    "strings such as 'TBA', 'NA', 'N/A', 'Not specified', 'Unknown', 'to be "
    "decided', 'with immediate effect', or their Hindi equivalents (e.g. "
    "'निर्धारित नहीं') — use null instead.\n"
    "3a. *_district fields must be an actual PLACE (district/city/state) and "
    "*_posting fields an actual office/role TITLE. NEVER put the order's nature or "
    "a generic label in them — e.g. 'New posting', 'Extension of service', "
    "'Promotion', 'Transfer', 'Repatriation', 'Reshuffle', 'Awaiting posting' are "
    "NOT places or titles → use null. Never copy the destination into the "
    "previous_* fields; if the prior place/role isn't stated, previous_* = null. "
    "previous and new must differ — never output the same value for both.\n"
    "4. Dates: copy a date only if an actual calendar date is given (any format is "
    "fine, copy it verbatim). If no concrete date is stated, return null for that "
    "date field — never a placeholder.\n"
    "5. One article may describe multiple officer transfers (a reshuffle) — return "
    "one object per officer.\n"
    "6. confidence_score (0.0-1.0) reflects how clearly the article states the "
    "transfer for THAT officer.\n"
    "Respond with strict JSON only."
)

SCHEMA_HINT = {
    "is_transfer_news": "boolean — true only if the article reports IAS/officer transfer(s)",
    "transfers": [
        {
            "officer_name": "string|null",
            "ias_batch": "string|null — e.g. '2009' or '2009 batch'",
            "cadre": "string|null — state cadre, e.g. 'UP', 'Maharashtra'",
            "state": "string|null",
            "current_designation": "string|null",
            "previous_district": "string|null",
            "previous_posting": "string|null — role/office held before transfer",
            "new_district": "string|null",
            "new_posting": "string|null — role/office after transfer",
            "transfer_date": "string|null — as written",
            "effective_date": "string|null — as written",
            "reason": "string|null",
            "notification_number": "string|null — government order number",
            "gov_order_link": "string|null",
            "confidence_score": "number 0.0-1.0",
        }
    ],
}


class InformationAgent(BaseAgent):
    name = "information"

    def run(self, article: Article, *, provider=None, model=None) -> list[ExtractedTransfer]:
        text = (article.full_text or "").strip()
        if not text:
            article.status = ArticleStatus.IRRELEVANT
            return []

        user_prompt = (
            f"SOURCE: {article.source_name or 'unknown'}\n"
            f"URL: {article.url}\n"
            f"HEADLINE: {article.title or ''}\n\n"
            "Extract all IAS transfers from the article below. Return JSON with "
            f"keys exactly: {json.dumps(list(SCHEMA_HINT.keys()))}.\n"
            f"Schema: {json.dumps(SCHEMA_HINT)}\n\n"
            "ARTICLE:\n"
            f"{text[: settings.LLM_MAX_INPUT_CHARS]}"
        )

        try:
            raw = llm.complete_json(SYSTEM_PROMPT, user_prompt,
                                    provider=provider, model=model)
            result = ExtractionResult.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            # An LLM call error / unparseable reply is usually TRANSIENT — the
            # local model was momentarily overloaded or timed out. Do not mark
            # the article permanently FAILED on a single blip; record the error
            # and re-raise so the Celery task retries it (and a later discovery
            # cycle can pick it up again) instead of dropping relevant news.
            article.error = f"LLM extraction error (will retry): {exc}"
            self.audit("inform", f"LLM extraction error for article {article.id} — will retry",
                       level=LogLevel.ERROR, article_id=article.id, error=str(exc))
            raise

        if not result.is_transfer_news or not result.transfers:
            article.status = ArticleStatus.IRRELEVANT
            self.audit("inform", f"No transfers found in article {article.id}",
                       article_id=article.id)
            return []

        # Keep only objects with at least an officer name; blend the model's
        # self-reported confidence with our source-trust weight.
        weight = source_weight(article.source_name, article.url)
        valid: list[ExtractedTransfer] = []
        for t in result.transfers:
            if not (t.officer_name and t.officer_name.strip()):
                continue
            _sanitize(t)  # strip label/order-nature junk from place/title fields
            # Normalise the cadre state to a canonical Indian state/UT; a value
            # that isn't one (e.g. "Sylhet") is dropped as non-Indian.
            t.state = canonical_state(t.state)
            t.confidence_score = round(0.6 * t.confidence_score + 0.4 * weight, 3)
            if not t.gov_order_link and article.gov_order_links:
                t.gov_order_link = article.gov_order_links[0]
            valid.append(t)

        article.status = ArticleStatus.PARSED
        self.audit("inform", f"Extracted {len(valid)} transfer(s) from article {article.id}",
                   article_id=article.id, count=len(valid),
                   model=model or llm.active_model(provider))
        return valid
