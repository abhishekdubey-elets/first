"""Retrieval-Augmented assistant over the IAS transfer records.

Retrieval is hybrid: local semantic embeddings (Ollama) + keyword overlap, so
both fuzzy questions ("recent reshuffles in the south") and exact-entity ones
("who is the new Patna DM") work. Generation is grounded strictly in the
retrieved records with citations, and refuses to answer beyond the data.

The embedding index is built in-memory and lazily refreshed whenever the set of
records changes (cheap for this dataset size), so there is no extra DB schema.
"""
from __future__ import annotations

import math
import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services import llm

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the assistant for an IAS (Indian Administrative Service) officer "
    "transfer-intelligence dashboard.\n"
    "You are given CANDIDATE REFERENCE records retrieved by a similarity search. "
    "They are ONLY candidates — some or all may be IRRELEVANT to the question. "
    "Treat them as references to verify, NOT as a guaranteed answer.\n"
    "Method (follow in order):\n"
    "1. VERIFY: decide which candidate records, if any, genuinely pertain to the "
    "question (matching officer / district / state / posting / topic asked). "
    "Silently discard the rest — never mention or list irrelevant candidates.\n"
    "2. If NO candidate genuinely answers the question, reply with EXACTLY the "
    "single token NO_LOCAL_ANSWER and nothing else.\n"
    "3. GENERATE: answer using ONLY the records you verified as relevant. Never "
    "use outside knowledge and never invent officer names, places, or dates.\n"
    "4. Be concise and factual. List multiple officers as bullets "
    "'Officer — From → To (source, date)' and mention the source outlet/date.\n"
)

# Sentinel the model emits when the retrieved records don't cover the question;
# triggers the live web-search fallback.
_NO_LOCAL = "NO_LOCAL_ANSWER"

_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "who", "what", "which", "where", "when", "how", "show", "me",
    "list", "all", "any", "from", "by", "as", "officer", "officers", "ias",
    "transfer", "transfers", "transferred", "posting", "postings", "latest",
    "recent", "new", "give", "tell", "about", "do", "does", "did", "has", "have",
}

# In-memory embedding index: parallel lists kept in sync.
_IDS: list[int] = []
_TEXTS: list[str] = []
_VECS: list[list[float]] = []
_META: list[dict[str, Any]] = []
_SIG: tuple | None = None


def record_card(t: dict[str, Any]) -> str:
    """One compact, embeddable text 'card' per transfer record."""
    frm = t.get("previous_posting") or t.get("previous_district") or "unknown"
    to = t.get("new_posting") or t.get("new_district") or "unknown"
    parts = [f"Officer {t.get('officer_name') or 'unknown'}"]
    if t.get("ias_batch"):
        parts.append(f"batch {t['ias_batch']}")
    if t.get("cadre") or t.get("state"):
        parts.append(f"cadre/state {t.get('cadre') or t.get('state')}")
    parts.append(f"transferred from {frm} to {to}")
    if t.get("transfer_date"):
        parts.append(f"on {t['transfer_date']}")
    if t.get("notification_number"):
        parts.append(f"order {t['notification_number']}")
    if t.get("source_name"):
        parts.append(f"reported by {t['source_name']}")
    if t.get("status"):
        parts.append(f"status {t['status']}")
    return ", ".join(parts) + "."


def _signature(records: list[dict[str, Any]]) -> tuple:
    return (len(records), tuple(sorted((r["id"], str(r.get("updated_at"))) for r in records)))


def _ensure_index(records: list[dict[str, Any]]) -> None:
    """(Re)build the embedding index if the record set changed."""
    global _IDS, _TEXTS, _VECS, _META, _SIG
    sig = _signature(records)
    if sig == _SIG and _VECS:
        return
    texts = [record_card(r) for r in records]
    vecs = llm.embed_texts(texts) if texts else []
    _IDS = [r["id"] for r in records]
    _TEXTS = texts
    _VECS = vecs
    _META = records
    _SIG = sig
    log.info("rag_index_built", records=len(records))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_score(question: str, meta: dict[str, Any]) -> float:
    toks = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP and len(w) > 2}
    if not toks:
        return 0.0
    hay = " ".join(str(meta.get(f) or "") for f in (
        "officer_name", "state", "cadre", "previous_district", "previous_posting",
        "new_district", "new_posting", "source_name", "notification_number",
    )).lower()
    hits = sum(1 for tok in toks if tok in hay)
    return hits / len(toks)


def retrieve(
    question: str, records: list[dict[str, Any]], k: int | None = None
) -> tuple[list[dict[str, Any]], float]:
    """Hybrid semantic + keyword retrieval.

    Returns (top-k record dicts, best semantic similarity among them). The score
    lets the caller decide whether the local data actually covers the question.
    """
    k = k or settings.CHAT_TOP_K
    if not records:
        return [], 0.0
    _ensure_index(records)
    qvec = llm.embed_texts([question])[0]
    scored = []
    for i, meta in enumerate(_META):
        sem = _cosine(qvec, _VECS[i]) if i < len(_VECS) else 0.0
        kw = _keyword_score(question, meta)
        # Blend: semantic carries meaning, keyword guarantees exact-entity hits.
        scored.append((0.7 * sem + 0.3 * kw, sem, kw, meta))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:k]
    best_sem = max((s for _, s, _, _ in top), default=0.0)
    return [m for _, _, _, m in top], best_sem


WEB_SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions about IAS officer transfers "
    "using LIVE WEB SEARCH results (recent news headlines). Answer concisely from "
    "the results provided. Make clear this is from a live web search, not the "
    "dashboard's tracked database, and don't invent details beyond the results."
)


def _chat_model() -> str | None:
    """Use the small fast local model for chat; let a cloud provider use its own."""
    return settings.CHAT_MODEL if llm.active_provider() == "ollama" else None


def _generate(system: str, user: str) -> str:
    return llm.complete_text(
        system, user,
        model=_chat_model(),
        max_tokens=settings.CHAT_MAX_TOKENS,
        timeout=settings.CHAT_TIMEOUT_SECONDS,
    )


def web_search(question: str, limit: int = 6) -> list[dict[str, Any]]:
    """Live web search via Google News RSS (no API key)."""
    import re
    import urllib.parse

    import feedparser

    q = urllib.parse.quote(question)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    items: list[dict[str, Any]] = []
    for e in feed.entries[:limit]:
        summary = re.sub(r"<[^>]+>", "", e.get("summary", "") or "").strip()
        src = ""
        s = e.get("source")
        if s is not None:
            src = (getattr(s, "title", "") or (s.get("title", "") if hasattr(s, "get") else "")) or ""
        items.append({
            "title": e.get("title", ""),
            "summary": summary[:300],
            "link": e.get("link", ""),
            "source": src,
            "published": e.get("published", ""),
        })
    return items


def _answer_from_web(question: str, local_hits: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        items = web_search(question)
    except Exception as exc:  # noqa: BLE001
        log.warning("web_search_failed", error=str(exc))
        items = []

    if not items:
        return {"answer": "I don't have this in the tracked transfer data, and a "
                          "live web search didn't return anything usable right now.",
                "sources": [], "web_sources": [], "from_web": True}

    ctx = "\n".join(
        f"- {it['title']} — {it['summary']} ({it['source']}, {it['published']})"
        for it in items
    )
    user_prompt = (
        f"WEB SEARCH RESULTS (live news):\n{ctx}\n\n"
        f"QUESTION: {question}\n\nAnswer concisely from these results."
    )
    try:
        text = _generate(WEB_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("web_generate_failed", error=str(exc))
        text = "From a live web search:\n" + "\n".join(
            f"• {it['title']} ({it['source']})" for it in items
        )
    web_sources = [
        {"title": it["title"], "url": it["link"], "source": it["source"],
         "published": it["published"]}
        for it in items
    ]
    return {"answer": text, "sources": [], "web_sources": web_sources, "from_web": True}


def answer(question: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Retrieve relevant records and generate a grounded, cited answer.

    Local-first: if the tracked data doesn't cover the question (or there are no
    records), fall back to a live web search. Generation always degrades
    gracefully to a records list so the user never gets a hard error.
    """
    try:
        hits, best_sem = retrieve(question, records)
    except Exception as exc:  # noqa: BLE001 — embedding/index failure shouldn't 500
        log.warning("retrieve_failed", error=str(exc))
        hits, best_sem = [], 0.0

    insufficient = (not hits) or (best_sem < settings.CHAT_MIN_SIM)
    if insufficient and settings.ENABLE_WEB_FALLBACK:
        return _answer_from_web(question, hits)

    if not hits:
        return {"answer": "There are no transfer records in the system yet.",
                "sources": [], "web_sources": [], "from_web": False}

    ctx_lines, used, total = [], [], 0
    for r in hits:
        line = f"[{r['id']}] {record_card(r)}"
        if total + len(line) > settings.CHAT_MAX_CONTEXT_CHARS:
            break
        ctx_lines.append(line)
        used.append(r)
        total += len(line)
    user_prompt = (
        "CANDIDATE REFERENCE records (may include irrelevant ones — verify "
        "before use):\n" + "\n".join(ctx_lines) + "\n\n"
        f"QUESTION: {question}\n\n"
        "Verify which candidates are relevant, then answer using only those."
    )
    try:
        text = _generate(SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # noqa: BLE001 — never dump raw records; ask to retry
        log.warning("chat_generate_failed", error=str(exc))
        return {
            "answer": "I couldn't generate a verified answer just now — the local "
                      "model is busy. Please try again in a moment.",
            "sources": [], "web_sources": [], "from_web": False,
        }

    # The model judged the candidates don't actually answer this → go to web.
    if settings.ENABLE_WEB_FALLBACK and _NO_LOCAL in text.upper():
        return _answer_from_web(question, used)

    # Show as references only the candidates the verified answer actually used
    # (matched by officer name); fall back to all candidates if none are named.
    low = text.lower()
    cited = [r for r in used if (r.get("officer_name") or "").lower() in low and r.get("officer_name")]
    return {"answer": text, "sources": cited or used, "web_sources": [], "from_web": False}
