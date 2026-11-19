"""Officer Research Agent: press coverage and photos for an officer's profile.

For one officer (as grouped by ``app.services.officers``) it:

1. searches Google News for the name as the press writes it ("Katherine
   Saranya IAS", and with the cadre), keeping results whose headline names the
   officer or one of their places;
2. reads up to ``OFFICER_RESEARCH_MAX_PAGES`` of them: most officers are named
   only in the body of a reshuffle story, so a result whose headline doesn't
   name them stays only if the page does. It keeps an excerpt around the name
   and any photo whose caption or alt text names the officer;
3. decides which results are about THIS officer, not a namesake: the LLM
   compares headline and excerpt with the officer's postings, places and
   cadre. With no LLM configured, they must mention one of those places, and
   for a common name ("Rajesh Kumar") a district or post, not just the state.
   Photos are kept only from articles that pass;
4. looks up Wikipedia, accepting a page only when it describes a civil servant
   and mentions their cadre, state or a district they served in.

Identity always rests on text (captions, headlines, the Wikipedia article),
never on faces. Images are kept as links with the page they came from; nothing
is downloaded. Only Wikipedia images are treated as confirmed; the rest are
shown as unverified, and an admin can hide any of them.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.agents.base import BaseAgent
from app.core.config import settings
from app.models.enums import LogLevel
from app.services import gnews, llm, rag
from app.services.normalize import clean, names_match, norm_name, text_mentions
from app.services.officers import Officer

WIKI_API = "https://en.wikipedia.org/w/api.php"
MAX_PRESS = 15
MAX_IMAGES = 6

# Words too generic to tie a result to one officer.
_GENERIC = {
    "additional", "administration", "board", "chief", "collector", "commissioner",
    "corporation", "department", "deputy", "development", "director", "district",
    "government", "joint", "magistrate", "managing", "member", "municipal", "office",
    "officer", "principal", "secretary", "special", "state", "the", "and", "of",
}
_SKIP_IMAGE = re.compile(
    r"(logo|icon|sprite|placeholder|blank|pixel|spacer|avatar|default|banner|ads?[/_-])",
    re.I,
)

_SYSTEM = (
    "You check news search results against ONE Indian IAS officer. Many officers "
    "share a name, so a result is about this officer only when its details fit "
    "the OFFICER facts: the posts held, the districts or states, the cadre. "
    "Answer for every result: 'yes' (clearly this officer), 'no' (another person, "
    "or not about the officer) or 'unsure'. Respond with strict JSON only: "
    '{"results": [{"i": <number>, "about_officer": "yes" | "no" | "unsure"}]}'
)


# --- pure helpers (unit-tested) ----------------------------------------------
def officer_names(o: Officer) -> list[str]:
    return [o.name, *o.aliases]


# Name words shared by so many officers that a state match proves nothing.
_COMMON_NAME_WORDS = {
    "kumar", "kumari", "singh", "sharma", "verma", "gupta", "yadav", "devi", "prasad",
    "rao", "reddy", "patel", "mishra", "das", "khan", "ali", "ahmed", "ahmad", "jain",
    "pandey", "tiwari", "shukla", "chaudhary", "chaudhry", "choudhary", "nair", "pillai",
    "iyer", "naidu", "babu", "lal", "chand", "nath", "raj", "ram", "mohammad",
}


def common_name(o: Officer) -> bool:
    from app.services.normalize import name_tokens, sounds_key

    common = {sounds_key(w) for w in _COMMON_NAME_WORDS}
    return any(sounds_key(t) in common for t in name_tokens(o.name))


def context_terms(o: Officer, *, strong_only: bool = False) -> set[str]:
    """Places and distinctive post words that tie a text to this officer.

    ``strong_only`` leaves out the state and cadre, which thousands of
    officers share: for a common name only a district or a post will do.
    """
    terms: set[str] = set()
    for m in o.moves:
        places = [m["to_district"], m["from_district"]]
        if not strong_only:
            places.append(m["state"])
        for place in places:
            if clean(place):
                terms.add(clean(place).lower())
        for word in re.split(r"[^A-Za-z]+", f"{m['role']} {m['from_posting'] or ''}"):
            if len(word) >= 4 and word.lower() not in _GENERIC:
                terms.add(word.lower())
    if not strong_only and o.cadre and o.cadre.upper() != "AGMUT":
        terms.add(o.cadre.lower())
    if strong_only:
        terms -= {clean(m["state"]).lower() for m in o.moves if m["state"]}
        terms -= {w for t in terms for w in t.split() if w in _COMMON_NAME_WORDS}
    return terms


def mentions_context(text: str, terms: set[str]) -> bool:
    low = f" {clean(text).lower()} "
    return any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low) for t in terms)


def officer_facts(o: Officer) -> dict:
    return {
        "name": o.name,
        "other_spellings": o.aliases,
        "batch": o.batch,
        "cadre": o.cadre,
        "states": sorted({m["state"] for m in o.moves if m["state"]}),
        "posts": [
            {"date": m["date"], "post": m["role"], "district": m["to_district"],
             "from": m["from_posting"] or m["from_district"]}
            for m in o.moves[:8]
        ],
    }


_HONORIFICS = {"dr", "shri", "shree", "smt", "sri", "mr", "mrs", "ms", "ias"}


def search_name(name: str) -> str:
    """The name as the press writes it: initials and honorifics dropped.

    'A. Katherine Saranya' -> 'Katherine Saranya'. Headlines rarely carry the
    initial, and Google News finds nothing for a phrase they never print.
    """
    words = []
    for w in clean(name).split():
        bare = w.strip(".,")
        if len(bare.replace(".", "")) <= 2 or bare.lower() in _HONORIFICS:
            continue
        words.append(bare)
    return " ".join(words) or clean(name)


def search_queries(o: Officer) -> list[str]:
    # Unquoted: Google News phrase search misses most real coverage. Precision
    # comes from the checks after the search, not from the query.
    name = search_name(o.name)
    place = o.cadre if o.cadre and o.cadre.upper() != "AGMUT" else o.state
    queries = [f"{name} IAS"]
    if place:
        queries.append(f"{name} {place}")
    return queries


def body_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    return re.sub(r"\s+", " ", container.get_text(" ", strip=True))


def page_excerpt(html: str, names: list[str]) -> str | None:
    """Where the article itself names the officer.

    Paragraphs first (story text lives in <p>), then list items and table cells
    (reshuffle lists), and only then the whole page, so a headline repeated in
    the page's sidebar or menu is not taken for the story.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    for tags in (["p"], ["li", "td"]):
        for el in soup.find_all(tags):
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if len(text) >= 20 and text_mentions(text, names):
                found = excerpt_around(text, names)
                if found:
                    return found
    return excerpt_around(body_text(str(soup)), names)


def excerpt_around(text: str, names: list[str], width: int = 220) -> str | None:
    """A window of ``text`` around where it names the officer, or None."""
    from app.services.normalize import name_tokens, sounds_key, text_words

    words = text_words(text)
    for name in names:
        toks = name_tokens(name)
        if not toks:
            continue
        last = sounds_key(toks[-1])
        for pos, word in words:
            if word != last:
                continue
            lo, hi = max(0, pos - width), min(len(text), pos + len(toks[-1]) + width)
            # Start at the sentence that names them and stop at its end, so a
            # page's sidebar or the previous story does not lead the excerpt.
            start = max(text.rfind(". ", lo, pos), text.rfind("! ", lo, pos),
                        text.rfind("? ", lo, pos))
            if start != -1:
                lo = start + 2
            end = min((i for i in (text.find(". ", pos, hi), text.find("! ", pos, hi),
                                   text.find("? ", pos, hi)) if i != -1), default=-1)
            if end != -1:
                hi = end + 1
            window = text[lo:hi]
            if text_mentions(window, [name]):
                return ("…" if lo else "") + window.strip() + ("…" if hi < len(text) else "")
    return None


def _strip_source(title: str, source: str) -> str:
    """Google News appends ' - Publisher' to every headline."""
    title, source = clean(title), clean(source)
    if source and title.endswith(f" - {source}"):
        return title[: -len(source) - 3].strip()
    return title


def _iso_day(raw: str) -> str | None:
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def to_press(item: dict) -> dict:
    source = clean(item.get("source"))
    return {
        "url": clean(item.get("link")),
        "title": _strip_source(item.get("title", ""), source),
        "source": source or None,
        "published": _iso_day(item.get("published", "")),
        "snippet": clean(item.get("summary"))[:300] or None,
    }


def extract_images(html: str, page_url: str, names: list[str]) -> list[dict]:
    """Photos on a page whose caption, alt or title text names the officer."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    seen: set[str] = set()

    def src_of(img) -> str | None:
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            v = clean(img.get(attr))
            if v and not v.startswith("data:"):
                return urljoin(page_url, v)
        srcset = clean(img.get("srcset") or img.get("data-srcset"))
        if srcset:
            return urljoin(page_url, srcset.split(",")[0].split()[0])
        return None

    def too_small(img) -> bool:
        for attr in ("width", "height"):
            v = clean(str(img.get(attr) or ""))
            if v.isdigit() and int(v) < 100:
                return True
        return False

    def add(img, caption: str) -> None:
        url = src_of(img)
        caption = clean(caption)
        if not url or url in seen or not caption or len(caption) > 300:
            return
        path = urlparse(url).path.lower()
        if path.endswith((".svg", ".gif")) or _SKIP_IMAGE.search(path) or too_small(img):
            return
        if not text_mentions(caption, names):
            return
        seen.add(url)
        found.append({"image_url": url, "page_url": page_url, "caption": caption[:300]})

    for fig in soup.find_all("figure"):
        img, cap = fig.find("img"), fig.find("figcaption")
        if img is not None and cap is not None:
            add(img, cap.get_text(" ", strip=True))
    for img in soup.find_all("img"):
        add(img, img.get("alt") or img.get("title") or "")
    return found


def wikipedia_fits(extract: str, o: Officer) -> bool:
    """The page is about an IAS officer, and one with this officer's places."""
    text = clean(extract)
    # Intros say "IAS officer", "Indian Administrative Service" or just "Indian
    # civil servant"; the place check below is what rules out namesakes.
    if not re.search(r"Indian Administrative Service|\bIAS\b|civil servant|civil service|"
                     r"bureaucrat", text, re.I):
        return False
    places = {clean(m[k]).lower() for m in o.moves for k in ("to_district", "state")
              if clean(m[k])}
    if o.cadre:
        places.add(o.cadre.lower())
    return not places or mentions_context(text, places)


def merge_images(new: list[dict], old: list[dict] | None) -> list[dict]:
    """New candidates, keeping any image an admin hid hidden."""
    hidden = {i["image_url"] for i in (old or []) if i.get("hidden")}
    out, seen = [], set()
    for img in new:
        if img["image_url"] in seen:
            continue
        seen.add(img["image_url"])
        out.append({**img, "hidden": img["image_url"] in hidden})
    return out[:MAX_IMAGES]


def research_queue(officers: list[Officer], rows: dict[str, Any], *, now: datetime,
                   refresh_days: int, limit: int) -> list[Officer]:
    """Who to research next: queued by an admin, never researched, then stale
    (not refreshed in ``refresh_days``, or failed more than a day ago)."""
    queued, fresh, stale = [], [], []
    for o in officers:
        row = rows.get(o.key)
        if row is None:
            fresh.append(o)
        elif row.status == "queued":
            queued.append(o)
        elif row.researched_at is None or (now - row.researched_at).days >= (
                1 if row.status == "failed" else refresh_days):
            stale.append(o)
    queued.sort(key=lambda o: rows[o.key].requested_at or now)
    fresh.sort(key=lambda o: o.last_date, reverse=True)
    stale.sort(key=lambda o: rows[o.key].researched_at or datetime.min.replace(tzinfo=timezone.utc))
    return (queued + fresh + stale)[:limit]


# --- the agent ---------------------------------------------------------------
class OfficerResearchAgent(BaseAgent):
    name = "officer_research"

    # Network edges, kept as methods so tests can replace them.
    def search(self, query: str) -> list[dict]:
        return rag.web_search(query, limit=10)

    def fetch_html(self, url: str) -> tuple[str, str] | None:
        """(final publisher URL, HTML), or None when the page can't be read.

        Google News links are resolved to the publisher first: relative image
        paths must be joined to the publisher's page, not the redirector.
        """
        if gnews.is_google_news_url(url):
            if gnews.is_rate_limited():
                return None
            url = gnews.resolve(url) or ""
            if not url:
                return None
        if not self.allowed_by_robots(url):
            return None
        resp = self.http_get(url)
        resp.raise_for_status()
        if "html" not in resp.headers.get("content-type", "html"):
            return None
        return str(resp.url), resp.text

    def wiki(self, **params) -> dict:
        resp = httpx.get(
            WIKI_API, params={"format": "json", "formatversion": "2", **params},
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
        )
        resp.raise_for_status()
        return resp.json()

    def classify(self, o: Officer, items: list[dict]) -> list[str] | None:
        """LLM verdict per item, or None when no LLM is available or it fails."""
        if not llm.is_available():
            return None
        listing = "\n".join(
            f"{i}. {it['title']} ({it.get('source') or 'unknown'})"
            + (f" Excerpt: {it['excerpt']}" if it.get("excerpt") else "")
            for i, it in enumerate(items)
        )
        user = (f"OFFICER: {json.dumps(officer_facts(o), ensure_ascii=False)}\n\n"
                f"RESULTS:\n{listing}")
        try:
            raw = llm.complete_json(_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001
            self.audit("classify", f"LLM check failed for {o.name}: {exc}",
                       level=LogLevel.WARNING)
            return None
        verdicts = ["unsure"] * len(items)
        for v in (raw.get("results") or []) if isinstance(raw, dict) else []:
            try:
                i = int(v.get("i"))
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= i < len(items):
                verdicts[i] = str(v.get("about_officer") or "unsure").lower()
        return verdicts

    # --- steps ---------------------------------------------------------------
    def candidates(self, o: Officer) -> list[dict]:
        """News results worth a look: the headline names the officer, or names
        one of their places (the body is then checked for the name)."""
        names, terms = officer_names(o), context_terms(o)
        found: list[dict] = []
        seen: set[str] = set()
        for q in search_queries(o):
            try:
                results = self.search(q)
            except Exception as exc:  # noqa: BLE001
                self.audit("search", f"News search failed for {o.name}: {exc}",
                           level=LogLevel.WARNING)
                continue
            for r in results:
                p = to_press(r)
                key = p["url"] or norm_name(p["title"])
                if key in seen:
                    continue
                seen.add(key)
                head = f"{p['title']} {p['snippet'] or ''}"
                if text_mentions(head, names):
                    found.append({**p, "named_in_title": True})
                elif mentions_context(head, terms):
                    found.append({**p, "named_in_title": False})
        found.sort(key=lambda p: p["published"] or "", reverse=True)
        return found

    def read(self, o: Officer, items: list[dict]) -> list[dict]:
        """Open up to OFFICER_RESEARCH_MAX_PAGES articles: confirm the body names
        the officer, keep an excerpt around the name, collect captioned photos.
        Results whose headline doesn't name the officer are dropped unless their
        page was read and names them."""
        names = officer_names(o)
        budget = settings.OFFICER_RESEARCH_MAX_PAGES
        out: list[dict] = []
        for p in items:
            fetched = None
            if budget > 0:
                budget -= 1
                try:
                    fetched = self.fetch_html(p["url"])
                except Exception:  # noqa: BLE001 — one bad page never stops the rest
                    fetched = None
            item = {**p, "excerpt": None, "_images": []}
            if fetched:
                page_url, html = fetched
                item["url"] = page_url  # the publisher's page, not the Google redirect
                item["excerpt"] = page_excerpt(html, names)
                item["_images"] = [
                    {**img, "source": p.get("source"), "origin": "press"}
                    for img in extract_images(html, page_url, names)
                ]
            if item["named_in_title"] or item["excerpt"]:
                out.append(item)
        return out

    def verify(self, o: Officer, items: list[dict]) -> list[dict]:
        """Keep the results about THIS officer: the LLM's 'yes', or (with no LLM)
        a headline or excerpt that also names one of their places."""
        if not items:
            return []
        verdicts = self.classify(o, items)
        if verdicts is not None:
            return [{**p, "verdict": "llm"} for p, v in zip(items, verdicts, strict=True)
                    if v == "yes"]
        # A common name ("Rajesh Kumar") is shared by officers across a state, so
        # it needs one of the officer's districts or posts, not just the state.
        terms = context_terms(o, strong_only=common_name(o))
        return [{**p, "verdict": "context"} for p in items
                if mentions_context(f"{p['title']} {p['snippet'] or ''} {p['excerpt'] or ''}",
                                    terms)]

    def find_press(self, o: Officer) -> tuple[list[dict], list[dict]]:
        """(press mentions, photos from those same articles)."""
        kept = self.verify(o, self.read(o, self.candidates(o)))
        kept.sort(key=lambda p: p["published"] or "", reverse=True)
        kept = kept[:MAX_PRESS]
        images = [img for p in kept for img in p["_images"]]
        press = [{k: v for k, v in p.items() if not k.startswith("_") and k != "named_in_title"}
                 for p in kept]
        return press, images

    def find_wikipedia(self, o: Officer) -> dict | None:
        names = officer_names(o)
        try:
            hits = self.wiki(action="query", list="search", srsearch=f"{search_name(o.name)} IAS",
                             srlimit=3).get("query", {}).get("search", [])
        except Exception as exc:  # noqa: BLE001
            self.audit("wikipedia", f"Wikipedia search failed for {o.name}: {exc}",
                       level=LogLevel.WARNING)
            return None
        for hit in hits:
            title = clean(hit.get("title"))
            bare = re.sub(r"\s*\(.*?\)\s*$", "", title)
            if not any(names_match(bare, n) for n in names):
                continue
            try:
                pages = self.wiki(
                    action="query", prop="extracts|pageimages|info", titles=title,
                    exintro=1, explaintext=1, exsentences=4, piprop="thumbnail|name",
                    pithumbsize=400, inprop="url", redirects=1,
                ).get("query", {}).get("pages", [])
            except Exception:  # noqa: BLE001
                continue
            page = pages[0] if pages else {}
            extract = clean(page.get("extract"))
            if not extract or not wikipedia_fits(extract, o):
                continue
            image = (page.get("thumbnail") or {}).get("source")
            file_name = page.get("pageimage")
            return {
                "title": title,
                "url": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "extract": extract[:1200],
                "image_url": image,
                "image_page": (f"https://en.wikipedia.org/wiki/File:{file_name}"
                               if file_name else None),
            }
        return None

    def research(self, o: Officer, row) -> bool:
        """Research one officer into ``row`` (an ``OfficerResearch``). Returns success.

        If Google rate-limits link resolution mid-run, the articles could not be
        read: the row is marked failed (retried the next day) and keeps what
        an earlier run found, instead of being saved as "nothing found".
        """
        row.officer_id = o.id
        row.officer_name = o.name
        row.attempts = (row.attempts or 0) + 1
        try:
            press, press_images = self.find_press(o)
            if not press and gnews.is_rate_limited():
                row.status = "failed"
                row.error = "Google News rate-limited before the articles could be read"
                row.researched_at = datetime.now(timezone.utc)
                self.audit("research", f"Deferred {o.name}: Google News rate-limited",
                           level=LogLevel.WARNING, officer=o.id)
                return False
            wiki = self.find_wikipedia(o)
            images: list[dict] = []
            if wiki and wiki.get("image_url"):
                images.append({"image_url": wiki["image_url"], "page_url": wiki["image_page"]
                               or wiki["url"], "caption": wiki["title"],
                               "source": "Wikipedia", "origin": "wikipedia"})
            images += press_images
        except Exception as exc:  # noqa: BLE001
            row.status, row.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
            row.researched_at = datetime.now(timezone.utc)
            self.audit("research", f"Research failed for {o.name}: {exc}",
                       level=LogLevel.WARNING, officer=o.id)
            return False

        row.press = press
        row.wikipedia = wiki
        row.images = merge_images(images, row.images)
        row.status, row.error = "done", None
        row.researched_at = datetime.now(timezone.utc)
        self.audit("research", f"Researched {o.name}: {len(press)} press, "
                   f"{len(row.images)} images, wikipedia={'yes' if wiki else 'no'}",
                   officer=o.id, press=len(press), images=len(row.images))
        return True
