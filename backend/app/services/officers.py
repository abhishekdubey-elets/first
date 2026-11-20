"""Officer profiles: one page for every officer the pipeline has seen moved.

There is no officers table. An officer is the set of transfer records the
pipeline already treats as one person, so a profile never disagrees with how
records were merged. Everything here is pure: the caller loads the rows (any
objects shaped like ``IasTransfer``), these functions group and shape them.

Identity
--------
1. ``cluster_by_officer`` — the pipeline's own grouping (near-duplicate merging
   and batch/cadre propagation use it): records bucketed by state, joined when
   ``names_match`` says the names are spelling variants.
2. ``group_officers`` then joins those clusters where the state differs but the
   person plainly does not: an identical name (under ``name_key``) with the same
   cadre, e.g. an AGMUT officer posted to Delhi and later Goa. A record that
   never named a state joins the one officer it can belong to, and stays apart
   when more than one could claim it. Two different batch years are never joined.

Ids
---
An officer's id is a URL slug of name and state, ``anita-sharma--uttar-pradesh``.
``resolve`` is tolerant: any spelling variant, any state the officer has served
in, or a bare name (links made before ids existed) reach the same profile.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from itertools import combinations
from typing import Any

from app.api.routes.feed import headline_of, movement_of, record_date, role_of
from app.services.normalize import (
    clean,
    name_key,
    names_match,
    norm_batch,
    norm_name,
    role_group_of,
    strip_state_suffix,
)

STATE_SEP = "--"
_SLUG_STRIP = re.compile(r"[^a-z0-9ऀ-ॿ]+")
_VERIFIED = {"verified", "exported"}

# How many related officers a profile lists in each group.
MAX_RELATED = 24
MAX_BATCHMATES = 12


# --- ids ---------------------------------------------------------------------
def slugify(value: str | None) -> str:
    """Lowercase, punctuation and spaces to single hyphens; keeps Devanagari."""
    return _SLUG_STRIP.sub("-", clean(value).lower()).strip("-")


def officer_slug(name: str | None, state: str | None) -> str:
    """``Anita Sharma`` + ``Uttar Pradesh`` -> ``anita-sharma--uttar-pradesh``."""
    n = slugify(name) or "officer"
    s = slugify(state)
    return f"{n}{STATE_SEP}{s}" if s else n


# --- grouping ----------------------------------------------------------------
def better_name(a: str, b: str) -> str:
    """Prefer the unabbreviated, fuller spelling of an officer's name."""
    a, b = (a or "").strip(), (b or "").strip()
    a_abbr, b_abbr = "." in a, "." in b
    if a_abbr != b_abbr:
        return b if a_abbr else a
    return b if len(b) > len(a) else a


def cluster_by_officer(rows: Iterable[Any]) -> list[list[Any]]:
    """Group records by officer, tolerating spelling variants of the name.

    Records are bucketed by state first so the pairwise comparison stays cheap,
    then joined when their names match under ``names_match``.
    """
    by_state: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        by_state[clean(r.state).lower()].append(r)
    clusters: list[list[Any]] = []
    for bucket in by_state.values():
        local: list[list[Any]] = []
        for r in bucket:
            home = next((c for c in local if names_match(c[0].officer_name, r.officer_name)), None)
            if home is None:
                local.append([r])
            else:
                home.append(r)
        clusters.extend(local)
    return clusters


def _keys(recs: Iterable[Any]) -> set[str]:
    return {k for k in (name_key(r.officer_name) for r in recs) if k}


def _batches(recs: Iterable[Any]) -> set[str]:
    return {b for b in (norm_batch(r.ias_batch) for r in recs) if b}


def _cadres(recs: Iterable[Any]) -> set[str]:
    return {norm_name(r.cadre) for r in recs if norm_name(r.cadre)}


def _batch_ok(a: Sequence[Any], b: Sequence[Any]) -> bool:
    return len(_batches(a) | _batches(b)) <= 1


def _cadre_ok(a: Sequence[Any], b: Sequence[Any]) -> bool:
    ca, cb = _cadres(a), _cadres(b)
    return not ca or not cb or bool(ca & cb)


def group_officers(rows: Iterable[Any]) -> list[list[Any]]:
    """Records per officer (see the module docstring for the rules)."""
    clusters = cluster_by_officer(rows)
    stated = [c for c in clusters if clean(c[0].state)]
    stateless = [c for c in clusters if not clean(c[0].state)]

    members: dict[int, list[Any]] = {i: list(c) for i, c in enumerate(stated)}
    parent = list(range(len(stated)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_key: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(stated):
        for k in _keys(c):
            by_key[k].append(i)

    # The same person across states: identical name, same cadre, one batch.
    for idxs in by_key.values():
        for a, b in combinations(idxs, 2):
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            ga, gb = members[ra], members[rb]
            if _cadres(ga) & _cadres(gb) and _batch_ok(ga, gb):
                parent[rb] = ra
                ga.extend(members.pop(rb))

    # Records with no state join the single officer that can claim them.
    loose: list[list[Any]] = []
    for c in stateless:
        roots = {find(i) for k in _keys(c) for i in by_key.get(k, ())}
        fits = [r for r in roots if _batch_ok(members[r], c) and _cadre_ok(members[r], c)]
        if len(fits) == 1:
            members[fits[0]].extend(c)
        else:
            loose.append(list(c))
    return list(members.values()) + loose


# --- shaping -----------------------------------------------------------------
def _status(t: Any) -> str:
    s = t.status
    return s.value if hasattr(s, "value") else str(s)


def _mode(values: Iterable[str]) -> str | None:
    """Most frequent value; on a tie, the one seen first."""
    counted = Counter(v for v in values if v)
    return counted.most_common(1)[0][0] if counted else None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _movement(t: Any) -> dict:
    role = role_of(t)
    movement = movement_of(t)
    return {
        "transfer_id": t.id,
        "date": record_date(t),
        "stated_date": clean(t.transfer_date) or clean(t.effective_date) or None,
        "movement": movement,
        "role": role,
        "role_group": role_group_of(role),
        "from_posting": clean(t.previous_posting) or None,
        "from_district": strip_state_suffix(t.previous_district),
        "to_posting": clean(t.new_posting) or clean(t.current_designation) or None,
        "to_district": strip_state_suffix(t.new_district),
        "state": clean(t.state) or None,
        "reason": clean(t.reason) or None,
        "order_number": clean(t.notification_number) or None,
        "order_link": clean(t.gov_order_link) or None,
        "headline": headline_of(t, role, movement),
        "source_name": clean(t.source_name) or None,
        "source_url": clean(t.source_url) or None,
        "source_count": max(len(t.corroborating_sources or []), 1),
        "status": _status(t),
        "is_current": False,
        "tenure_days": None,
    }


def timeline(recs: Sequence[Any], today: date | None = None) -> list[dict]:
    """Movements newest first, each with how long the officer held that post.

    Several records on one day (an order giving two charges at once) share the
    tenure up to the next later date. The most recent day's postings are current
    and their tenure runs to today.
    """
    today = today or _today()
    items = [_movement(t) for t in recs]
    items.sort(key=lambda m: (m["date"], m["transfer_id"]), reverse=True)
    days = sorted({m["date"] for m in items})
    nxt = {d: days[i + 1] if i + 1 < len(days) else None for i, d in enumerate(days)}
    latest = days[-1] if days else None
    for m in items:
        start = date.fromisoformat(m["date"])
        end = nxt[m["date"]]
        if end is None:
            m["is_current"] = m["date"] == latest
            m["tenure_days"] = max((today - start).days, 0)
        else:
            m["tenure_days"] = (date.fromisoformat(end) - start).days
    return items


class Officer:
    """One officer's records, with the derived identity computed once."""

    __slots__ = ("records", "moves", "last_date", "name", "aliases", "batch", "cadre",
                 "state", "id")

    def __init__(self, records: Sequence[Any], today: date | None = None):
        self.moves = timeline(records, today)
        # Newest first, like the timeline, so every tie below (a batch, cadre or
        # state seen equally often) goes to the most recent record. Load order
        # is not stable enough to decide it: rows inserted in one transaction
        # share a created_at.
        by_id = {r.id: r for r in records}
        self.records = [by_id[m["transfer_id"]] for m in self.moves]
        self.last_date = self.moves[0]["date"] if self.moves else ""

        spellings = Counter(clean(r.officer_name) for r in self.records if clean(r.officer_name))
        ordered = sorted(spellings, key=lambda s: (-spellings[s], s))
        name = ordered[0] if ordered else "Unknown officer"
        for s in ordered[1:]:
            name = better_name(name, s)
        self.name = name
        seen = {name.lower()}
        self.aliases = []
        for s in ordered:
            if s.lower() not in seen:
                seen.add(s.lower())
                self.aliases.append(s)

        self.batch = _mode(norm_batch(r.ias_batch) for r in self.records)
        self.cadre = _mode(clean(r.cadre) for r in self.records)
        self.state = _mode(clean(r.state) for r in self.records)
        self.id = officer_slug(self.name, self.state)

    @property
    def current(self) -> dict | None:
        return self.moves[0] if self.moves else None

    @property
    def key(self) -> str:
        """Identity used to file research results: name key + home state."""
        return f"{name_key(self.name)}|{slugify(self.state)}"

    @property
    def keys(self) -> set[str]:
        """Name keys of every spelling seen for this officer."""
        return _keys(self.records)

    @property
    def state_slugs(self) -> set[str]:
        return {slugify(r.state) for r in self.records if clean(r.state)}

    def bio(self) -> str:
        return bio_line(self)

    def summary(self) -> dict:
        cur = self.current or {}
        return {
            "id": self.id,
            "name": self.name,
            "aliases": self.aliases,
            "batch": self.batch,
            "cadre": self.cadre,
            "state": self.state,
            "bio": self.bio(),
            "photo_url": None,
            "current_role": cur.get("role") or "IAS Officer",
            "current_district": cur.get("to_district"),
            "current_state": cur.get("state"),
            "movements_count": len(self.moves),
            "first_seen": self.moves[-1]["date"] if self.moves else "",
            "last_movement_date": cur.get("date") or "",
            "last_movement": cur.get("movement") or "",
        }

    def link(self, relation: str) -> dict:
        cur = self.current or {}
        return {
            "id": self.id, "name": self.name, "batch": self.batch, "state": self.state,
            "current_role": cur.get("role") or "IAS Officer", "relation": relation,
        }

    def matches_text(self, q: str) -> bool:
        needle = clean(q).lower()
        key = name_key(q)
        names = [self.name, *self.aliases]
        return any(needle in n.lower() for n in names) or bool(
            key and any(key in name_key(n) for n in names)
        )


def build_officers(rows: Iterable[Any], today: date | None = None) -> list[Officer]:
    return [Officer(g, today) for g in group_officers(rows) if g]


def canonical_ids(rows: Iterable[Any]) -> dict[int, str]:
    """Transfer record id -> the profile id of the officer it belongs to.

    Unlike ``IasTransfer.officer_id`` (built from that one record's spelling
    and state), every record of one officer gets the same id, so a consumer
    can group by it.
    """
    return {r.id: o.id for o in build_officers(rows) for r in o.records}


# --- bio ---------------------------------------------------------------------
def _where(role: str, *places: str | None) -> str:
    """Places not already named in the role text, comma-joined."""
    low = role.lower()
    seen: list[str] = []
    for p in places:
        p = clean(p)
        if p and p.lower() not in low and p.lower() not in (s.lower() for s in seen):
            seen.append(p)
    return ", ".join(seen)


def bio_line(o: Officer) -> str:
    """One factual sentence or three, built only from the tracked records.

    'A. Katherine Saranya is an Indian Administrative Service officer (Tamil
    Nadu cadre). Currently Commissioner, Vellore Corporation, Tamil Nadu.
    1 tracked posting change.'
    """
    traits = ", ".join(x for x in (
        f"{o.cadre} cadre" if o.cadre else "",
        f"{o.batch} batch" if o.batch else "",
    ) if x)
    parts = [f"{o.name} is an Indian Administrative Service officer"
             + (f" ({traits})" if traits else "") + "."]
    cur = o.current
    if cur:
        role = cur["role"]
        place = _where(role, cur["to_district"], cur["state"])
        lead = "Retired as" if cur["movement"] == "Retirement" else "Currently"
        parts.append(f"{lead} {role}{', ' + place if place else ''}.")
    n = len(o.moves)
    count = f"{n} tracked posting change{'s' if n != 1 else ''}"
    if n > 1 and o.moves[-1]["date"][:4] != o.moves[0]["date"][:4]:
        count += f" since {o.moves[-1]['date'][:4]}"
    parts.append(count + ".")
    return " ".join(parts)


# --- directory ---------------------------------------------------------------
# sort name -> (key, default order)
_SORTS = {
    "recent": (lambda o: (o.last_date, o.name.lower()), "desc"),
    "name": (lambda o: o.name.lower(), "asc"),
    "movements": (lambda o: (len(o.moves), o.last_date), "desc"),
}
SORT_NAMES = tuple(_SORTS)


def directory(
    officers: Sequence[Officer], *, q: str | None = None, state: str | None = None,
    batch: str | None = None, cadre: str | None = None, sort: str = "recent",
    order: str | None = None,
) -> list[Officer]:
    """Filter and sort officers for the directory page.

    ``order`` defaults per sort: newest / most-moved first, names A to Z.
    """
    out = list(officers)
    if clean(q):
        out = [o for o in out if o.matches_text(q)]
    if clean(state):
        s = clean(state).lower()
        out = [o for o in out if any(s in clean(r.state).lower() for r in o.records)]
    if clean(batch):
        b = norm_batch(batch) or clean(batch)
        out = [o for o in out if o.batch == b]
    if clean(cadre):
        c = clean(cadre).lower()
        out = [o for o in out if o.cadre and c in o.cadre.lower()]
    key, default_order = _SORTS.get(sort, _SORTS["recent"])
    out.sort(key=key, reverse=(order or default_order) == "desc")
    return out


# --- resolution --------------------------------------------------------------
def resolve(officers: Sequence[Officer], officer_id: str) -> tuple[Officer | None, list[Officer]]:
    """Find the officer an id (or a bare name) refers to, plus other candidates.

    Exact name matches beat spelling-variant matches; an officer who has served
    in the id's state beats one who has not; then the most recently moved wins.
    """
    raw = clean(officer_id)
    name_part, _, state_part = raw.lower().partition(STATE_SEP)
    query_name = name_part.replace("-", " ")
    want = name_key(query_name)
    if not want:
        return None, []
    want_state = slugify(state_part)

    exact, fuzzy = [], []
    for o in officers:
        names = [o.name, *o.aliases]
        if any(name_key(n) == want for n in names):
            exact.append(o)
        elif any(names_match(n, query_name) for n in names):
            fuzzy.append(o)
    candidates = exact or fuzzy
    if not candidates:
        return None, []

    def rank(o: Officer):
        in_state = bool(want_state) and (
            o.id == raw.lower() or any(slugify(r.state) == want_state for r in o.records)
        )
        return (in_state, o.last_date, len(o.moves))

    candidates.sort(key=rank, reverse=True)
    return candidates[0], candidates[1:]


# --- the profile -------------------------------------------------------------
def _order_key(value: str | None) -> str:
    return norm_name(value)


def related(officer: Officer, officers: Sequence[Officer]) -> tuple[list[dict], list[dict]]:
    """Officers moved in the same order or article, and same-batch, same-cadre peers."""
    own_orders = {_order_key(r.notification_number) for r in officer.records} - {""}
    own_articles = {r.article_id for r in officer.records if getattr(r, "article_id", None)}
    co: list[dict] = []
    mates: list[dict] = []
    for other in officers:
        if other is officer:
            continue
        if own_orders and any(_order_key(r.notification_number) in own_orders for r in other.records):
            co.append(other.link("same_order"))
        elif own_articles and any(getattr(r, "article_id", None) in own_articles
                                  for r in other.records):
            co.append(other.link("same_article"))
        if (officer.batch and other.batch == officer.batch and officer.cadre
                and other.cadre and norm_name(other.cadre) == norm_name(officer.cadre)):
            mates.append(other.link("batchmate"))
    co.sort(key=lambda x: (x["relation"] != "same_order", x["name"].lower()))
    mates.sort(key=lambda x: x["name"].lower())
    return co[:MAX_RELATED], mates[:MAX_BATCHMATES]


def _identity_notes(officer: Officer) -> list[str]:
    notes = []
    batches = sorted(_batches(officer.records))
    if len(batches) > 1:
        notes.append(f"Records disagree on the batch year: {', '.join(batches)}.")
    cadres = sorted({clean(r.cadre) for r in officer.records if clean(r.cadre)}, key=str.lower)
    if len({norm_name(c) for c in cadres}) > 1:
        notes.append(f"Records disagree on the cadre: {', '.join(cadres)}.")
    return notes


def profile(officer: Officer, officers: Sequence[Officer],
            alternates: Sequence[Officer] = ()) -> dict:
    """The full profile payload (``OfficerProfile``)."""
    moves = officer.moves
    chronological = list(reversed(moves))

    districts: list[str] = []
    for m in chronological:
        for d in (m["from_district"], m["to_district"]):
            if d and d.lower() not in {x.lower() for x in districts}:
                districts.append(d)
    states: list[str] = []
    for m in chronological:
        if m["state"] and m["state"] not in states:
            states.append(m["state"])

    groups = Counter(m["role_group"] for m in moves)
    days = sorted({m["date"] for m in moves})
    gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days for a, b in zip(days, days[1:], strict=False)]

    source_urls: dict[str, str] = {}
    for r in sorted(officer.records, key=lambda r: r.id):
        primary = clean(r.source_url)
        if primary and primary not in source_urls:
            source_urls[primary] = clean(r.source_name) or primary
        for u in r.corroborating_sources or []:
            u = clean(u)
            if u and u not in source_urls:
                source_urls[u] = _host(u)

    orders: list[dict] = []
    seen_orders: set[str] = set()
    for m in moves:
        if not (m["order_number"] or m["order_link"]):
            continue
        k = _order_key(m["order_number"]) or clean(m["order_link"])
        if k in seen_orders:
            continue
        seen_orders.add(k)
        orders.append({"number": m["order_number"], "url": m["order_link"], "date": m["date"]})

    co, mates = related(officer, officers)
    return {
        **officer.summary(),
        "current": officer.current,
        "timeline": moves,
        "stats": {
            "movements": len(moves),
            "distinct_postings": len({norm_name(m["role"]) for m in moves}),
            "districts": districts,
            "states": states,
            "role_groups": [{"role_group": g, "count": n} for g, n in groups.most_common()],
            "first_seen": days[0] if days else "",
            "last_seen": days[-1] if days else "",
            "average_tenure_days": round(sum(gaps) / len(gaps)) if gaps else None,
            "sources": len(source_urls),
            "verified_movements": sum(1 for m in moves if m["status"] in _VERIFIED),
        },
        "sources": [{"name": n, "url": u} for u, n in source_urls.items()],
        "orders": orders,
        "co_transferred": co,
        "batchmates": mates,
        "alternates": [o.link("same_name") for o in alternates][:MAX_RELATED],
        "identity_notes": _identity_notes(officer),
    }


def _host(url: str) -> str:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return url
    return host.removeprefix("www.") or url


# --- research (Officer Research Agent results) -------------------------------
def research_for(officer: Officer, rows: Iterable[Any]) -> list[Any]:
    """Research rows filed under this officer: a matching name key, in a state
    they served in (or filed without a state). Their own row comes first."""
    keys, states = officer.keys, officer.state_slugs
    found = [r for r in rows
             if r.name_key in keys and (not r.state or slugify(r.state) in states)]
    found.sort(key=lambda r: (r.officer_key != officer.key,
                              -(r.researched_at.timestamp() if r.researched_at else 0)))
    return found


def best_photo(images: Iterable[dict]) -> dict | None:
    """Wikipedia first, then the shortest caption (a portrait's caption is
    usually just the name and post; an event photo's is a sentence)."""
    visible = [i for i in images if not i.get("hidden")]
    visible.sort(key=lambda i: (i.get("origin") != "wikipedia", len(i.get("caption") or "")))
    return visible[0] if visible else None


def research_view(rows: Sequence[Any], *, include_hidden: bool = False) -> dict | None:
    """The ``research`` block of a profile, merged over the officer's rows."""
    if not rows:
        return None
    main = rows[0]
    press: list[dict] = []
    images: list[dict] = []
    seen_press: set[str] = set()
    seen_img: set[str] = set()
    wiki = None
    for r in rows:
        for p in r.press or []:
            k = p.get("url") or p.get("title")
            if k not in seen_press:
                seen_press.add(k)
                press.append(p)
        for i in r.images or []:
            if i["image_url"] not in seen_img:
                seen_img.add(i["image_url"])
                images.append(i)
        wiki = wiki or r.wikipedia
    press.sort(key=lambda p: p.get("published") or "", reverse=True)
    return {
        "status": main.status,
        "requested_at": main.requested_at,
        "researched_at": main.researched_at,
        "error": main.error,
        "press": press,
        "images": images if include_hidden else [i for i in images if not i.get("hidden")],
        "photo": best_photo(images),
        "wikipedia": wiki,
    }


# Profile keys the public portal never gets: the article list (the public feed
# does not publish article URLs) and the reviewers' identity notes.
_PRIVATE_PROFILE_KEYS = ("sources", "identity_notes", "research", "photo_url")


def public_profile(payload: dict, research: dict | None) -> dict:
    """The part of a profile that may be published without a login.

    Article links and the text quoted from articles stay in the dashboard, as
    in the public feed. Press photos are unverified (the agent matches them on
    a caption), so only a Wikipedia photo is shown, and only while no admin has
    hidden it; Wikipedia text and images are freely licensed and linked back.
    """
    out = {k: v for k, v in payload.items() if k not in _PRIVATE_PROFILE_KEYS}

    def movement(m: dict | None) -> dict | None:
        return {k: v for k, v in m.items() if k != "source_url"} if m else None

    out["current"] = movement(payload.get("current"))
    out["timeline"] = [movement(m) for m in payload.get("timeline", [])]

    research = research or {}
    visible = {
        i["image_url"] for i in research.get("images", [])
        if i.get("origin") == "wikipedia" and not i.get("hidden")
    }
    wiki = dict(research["wikipedia"]) if research.get("wikipedia") else None
    if wiki and wiki.get("image_url") not in visible:
        wiki["image_url"] = wiki["image_page"] = None
    out["wikipedia"] = wiki
    out["photo_url"] = wiki["image_url"] if wiki else None
    out["in_the_news"] = [
        {"title": p["title"], "source": p.get("source"), "published": p.get("published")}
        for p in research.get("press", []) if p.get("title")
    ]
    return out
