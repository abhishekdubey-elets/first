"""Enrichment Agent.

For a transfer record with missing fields (from / to / state / date), this agent
runs a live web search for the officer, asks the LLM to fill ONLY the missing
fields from what it finds, and writes the results back. Fields that remain empty
after a search are genuinely "no info" — surfaced as such in the dashboard.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.information import _clean_field
from app.core.india import canonical_state
from app.services.normalize import norm_batch
from app.models.enums import LogLevel
from app.models.transfer import IasTransfer
from app.services import llm, rag

# Fields we try to enrich (and pass as known context).
_FIELDS = (
    "state", "cadre", "ias_batch", "previous_district", "previous_posting",
    "new_district", "new_posting", "transfer_date",
)

_SYSTEM = (
    "You enrich Indian IAS officer transfer records from live web-search "
    "snippets. Given the KNOWN fields and the SEARCH RESULTS, output JSON that "
    "fills ONLY the requested MISSING fields using facts actually present in the "
    "results. Rules: *_district = a real place (district/city/state); *_posting "
    "= a real office/role title; transfer_date = a real date as written; ias_batch "
    "= the officer's IAS batch as a four-digit year; cadre = the officer's state "
    "cadre. Use null "
    "for anything the results don't clearly state. NEVER use generic labels like "
    "'New posting', 'Extension of service', 'Promotion', 'Transfer'. Only return "
    "info that is clearly about THIS officer. Write values in English (Latin "
    "script), transliterating names and translating titles. Respond with strict "
    "JSON only."
)


class EnrichmentAgent(BaseAgent):
    name = "enrichment"

    def enrich(self, t: IasTransfer) -> bool:
        """Fill missing fields on a transfer via web search. Returns True if any filled."""
        missing = [f for f in ("state", "cadre", "ias_batch", "new_district",
                               "previous_district", "new_posting", "transfer_date")
                   if not getattr(t, f, None)]
        if not missing or not (t.officer_name and t.officer_name.strip()):
            return False

        query = " ".join(x for x in [
            t.officer_name, "IAS officer transfer posting", (t.cadre or t.state or "")
        ] if x).strip()
        try:
            items = rag.web_search(query, limit=6)
        except Exception as exc:  # noqa: BLE001
            self.audit("enrich", f"web search failed for {t.officer_name}: {exc}",
                       level=LogLevel.WARNING)
            return False
        if not items:
            return False

        ctx = "\n".join(f"- {i['title']} — {i['summary']} ({i.get('source','')})"
                        for i in items)
        known = {f: getattr(t, f, None) for f in _FIELDS}
        user = (
            f"KNOWN fields: {json.dumps(known, ensure_ascii=False)}\n"
            f"MISSING fields to fill if found: {missing}\n\n"
            f"SEARCH RESULTS:\n{ctx}\n\n"
            "Return JSON containing only the missing keys you can fill."
        )
        try:
            raw = llm.complete_json(_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001
            self.audit("enrich", f"LLM enrich failed for {t.officer_name}: {exc}",
                       level=LogLevel.WARNING)
            return False

        filled = []
        for f in missing:
            val = raw.get(f) if isinstance(raw, dict) else None
            cleaned = _clean_field(val) if isinstance(val, str) else None
            if f == "state":
                cleaned = canonical_state(cleaned)  # only accept real Indian states
            if f == "cadre":
                cleaned = canonical_state(cleaned) or cleaned
            if f == "ias_batch":
                cleaned = norm_batch(cleaned)      # a year or nothing
            if f in ("previous_district", "new_district") and cleaned and canonical_state(cleaned):
                cleaned = None  # a state name is not a district
            if cleaned:
                # don't let enrichment set from == to
                if f == "previous_district" and (t.new_district or "").strip().lower() == cleaned.strip().lower():
                    continue
                setattr(t, f, cleaned)
                filled.append(f)
        if filled:
            self.audit("enrich", f"Enriched {t.officer_name}: {', '.join(filled)}",
                       officer=t.officer_name, fields=filled)
        return bool(filled)
