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
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel
from app.schemas.transfer import ExtractedTransfer, ExtractionResult
from app.services import llm

SYSTEM_PROMPT = (
    "You are a precise civil-service news analyst specialising in Indian "
    "Administrative Service (IAS) officer transfers and postings. You read news "
    "articles and government orders and extract STRUCTURED data about officer "
    "transfers. Rules:\n"
    "1. Only extract real IAS/administrative transfer information actually stated "
    "in the text. NEVER invent or hallucinate.\n"
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
            t.confidence_score = round(0.6 * t.confidence_score + 0.4 * weight, 3)
            if not t.gov_order_link and article.gov_order_links:
                t.gov_order_link = article.gov_order_links[0]
            valid.append(t)

        article.status = ArticleStatus.PARSED
        self.audit("inform", f"Extracted {len(valid)} transfer(s) from article {article.id}",
                   article_id=article.id, count=len(valid),
                   model=model or llm.active_model(provider))
        return valid
