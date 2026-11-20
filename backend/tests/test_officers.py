"""Officer profiles: identity grouping, id resolution, timeline and relations."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.services import officers as svc
from app.services.officers import (
    build_officers,
    directory,
    group_officers,
    officer_slug,
    profile,
    resolve,
    timeline,
)

TODAY = date(2026, 11, 19)


class _T:
    """Stand-in for an IasTransfer row."""

    _next_id = 1

    def __init__(self, **kw):
        defaults = dict(
            id=_T._next_id, officer_name="Anita Sharma", ias_batch="2009",
            cadre="Uttar Pradesh", state="Uttar Pradesh", current_designation=None,
            previous_district=None, previous_posting=None,
            new_district=None, new_posting=None,
            transfer_date=None, effective_date=None, reason=None,
            notification_number=None, gov_order_link=None,
            source_name="The Hindu", source_url=None,
            source_headline=None, corroborating_sources=[], status="verified",
            article_id=None,
            created_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            _news_date=None,
        )
        _T._next_id += 1
        defaults.update(kw)
        # Like a real record, the article reporting a transfer is published
        # around the transfer date (the feed distrusts dates far from it).
        if defaults["transfer_date"] and "_news_date" not in kw:
            day = date.fromisoformat(defaults["transfer_date"])
            defaults["_news_date"] = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        for k, v in defaults.items():
            setattr(self, k, v)

    @property
    def news_date(self):
        return self._news_date


def _names(groups):
    return sorted(sorted(r.officer_name for r in g) for g in groups)


# --- ids ---------------------------------------------------------------------
def test_slug_is_url_safe_and_carries_the_state():
    assert officer_slug("Anita Sharma", "Uttar Pradesh") == "anita-sharma--uttar-pradesh"
    assert officer_slug("Dr. K.  Rajan", None) == "dr-k-rajan"
    assert officer_slug(None, None) == "officer"


def test_transfer_records_expose_their_profile_id():
    from app.models import IasTransfer

    t = IasTransfer(officer_name="Rohit Menon", state="Maharashtra")
    assert t.officer_id == "rohit-menon--maharashtra"


# --- grouping ----------------------------------------------------------------
def test_spelling_variants_in_one_state_are_one_officer():
    rows = [_T(officer_name="Mohd. Aijaz"), _T(officer_name="Mohammad Aijaz"),
            _T(officer_name="Rohit Menon")]
    assert _names(group_officers(rows)) == [["Mohammad Aijaz", "Mohd. Aijaz"], ["Rohit Menon"]]


def test_same_name_in_two_cadres_stays_two_officers():
    rows = [_T(officer_name="Rajesh Kumar", state="Bihar", cadre="Bihar", ias_batch=None),
            _T(officer_name="Rajesh Kumar", state="Odisha", cadre="Odisha", ias_batch=None)]
    assert len(group_officers(rows)) == 2


def test_agmut_officer_is_joined_across_states():
    rows = [_T(officer_name="Neha Gupta", state="Delhi", cadre="AGMUT"),
            _T(officer_name="Neha Gupta", state="Goa", cadre="AGMUT", ias_batch=None)]
    assert len(group_officers(rows)) == 1


def test_id_does_not_depend_on_load_order():
    # One record per state: the tie goes to the most recent posting (Goa).
    rows = [_T(id=1, officer_name="Neha Gupta", state="Delhi", cadre="AGMUT",
               transfer_date="2025-06-04"),
            _T(id=2, officer_name="Neha Gupta", state="Goa", cadre="AGMUT",
               transfer_date="2026-09-01")]
    ids = {build_officers(order, TODAY)[0].id for order in (rows, rows[::-1])}
    assert ids == {"neha-gupta--goa"}


def test_a_different_batch_is_never_joined_across_states():
    rows = [_T(officer_name="Neha Gupta", state="Delhi", cadre="AGMUT", ias_batch="2010"),
            _T(officer_name="Neha Gupta", state="Goa", cadre="AGMUT", ias_batch="2014")]
    assert len(group_officers(rows)) == 2


def test_stateless_record_joins_the_only_officer_it_can_be():
    rows = [_T(officer_name="Anita Sharma"),
            _T(officer_name="Anita Sharma", state=None, cadre=None, ias_batch=None)]
    assert len(group_officers(rows)) == 1


def test_stateless_record_stays_apart_when_ambiguous():
    rows = [_T(officer_name="Rajesh Kumar", state="Bihar", cadre="Bihar", ias_batch=None),
            _T(officer_name="Rajesh Kumar", state="Odisha", cadre="Odisha", ias_batch=None),
            _T(officer_name="Rajesh Kumar", state=None, cadre=None, ias_batch=None)]
    assert len(group_officers(rows)) == 3


def test_pipeline_and_profiles_share_one_clustering():
    from app.workers import tasks

    assert tasks._officer_clusters is svc.cluster_by_officer
    assert tasks._better_name is svc.better_name


# --- identity ----------------------------------------------------------------
def test_display_name_prefers_the_full_spelling_and_lists_variants():
    (o,) = build_officers([_T(officer_name="Mohd. Aijaz"), _T(officer_name="Mohd. Aijaz"),
                           _T(officer_name="Mohammad Aijaz")], TODAY)
    assert o.name == "Mohammad Aijaz"
    assert o.aliases == ["Mohd. Aijaz"]
    assert o.id == "mohammad-aijaz--uttar-pradesh"


def test_batch_is_normalised():
    (o,) = build_officers([_T(ias_batch="2009 batch"), _T(ias_batch="IAS 2009")], TODAY)
    assert o.batch == "2009"


# --- timeline ----------------------------------------------------------------
def test_timeline_is_newest_first_with_tenure():
    rows = [
        _T(transfer_date="2025-01-10", new_posting="DM Varanasi", new_district="Varanasi"),
        _T(transfer_date="2026-01-10", new_posting="DM Lucknow", new_district="Lucknow",
           previous_posting="DM Varanasi", previous_district="Varanasi"),
    ]
    moves = timeline(rows, TODAY)
    assert [m["to_posting"] for m in moves] == ["DM Lucknow", "DM Varanasi"]
    assert moves[0]["is_current"] and not moves[1]["is_current"]
    assert moves[1]["tenure_days"] == 365                      # Varanasi -> Lucknow
    assert moves[0]["tenure_days"] == (TODAY - date(2026, 1, 10)).days
    assert moves[0]["movement"] == "Transfer"
    assert moves[1]["movement"] == "Appointment"


def test_two_charges_on_one_day_are_both_current():
    rows = [_T(transfer_date="2026-03-01", new_posting="Secretary, Finance"),
            _T(transfer_date="2026-03-01", new_posting="Additional charge, Planning")]
    moves = timeline(rows, TODAY)
    assert all(m["is_current"] for m in moves)


# --- resolution --------------------------------------------------------------
def test_resolve_by_slug_variant_or_bare_name():
    officers = build_officers([_T(officer_name="Mohammad Aijaz"),
                               _T(officer_name="Mohd. Aijaz")], TODAY)
    for ref in ("mohammad-aijaz--uttar-pradesh", "mohd-aijaz--uttar-pradesh",
                "Mohammad Aijaz", "mohd. aijaz"):
        found, alternates = resolve(officers, ref)
        assert found is not None and found.name == "Mohammad Aijaz", ref
        assert alternates == []


def test_resolve_prefers_the_state_in_the_id_and_lists_the_rest():
    officers = build_officers([
        _T(officer_name="Rajesh Kumar", state="Bihar", cadre="Bihar", ias_batch=None,
           transfer_date="2026-01-01"),
        _T(officer_name="Rajesh Kumar", state="Odisha", cadre="Odisha", ias_batch=None,
           transfer_date="2026-06-01"),
    ], TODAY)
    found, alternates = resolve(officers, "rajesh-kumar--bihar")
    assert found.state == "Bihar"
    assert [a.state for a in alternates] == ["Odisha"]
    # A bare name picks the most recently moved officer.
    found, alternates = resolve(officers, "Rajesh Kumar")
    assert found.state == "Odisha" and len(alternates) == 1


def test_resolve_unknown_officer():
    officers = build_officers([_T()], TODAY)
    assert resolve(officers, "nobody-here") == (None, [])
    assert resolve(officers, "") == (None, [])


# --- profile -----------------------------------------------------------------
def test_profile_stats_sources_orders_and_relations():
    rows = [
        _T(id=101, officer_name="Anita Sharma", transfer_date="2025-01-10",
           new_district="Varanasi", new_posting="DM Varanasi",
           source_url="https://thehindu.com/a", source_name="The Hindu",
           corroborating_sources=["https://thehindu.com/a", "https://www.ndtv.com/b"]),
        _T(id=102, officer_name="Anita Sharma", transfer_date="2026-01-10",
           previous_district="Varanasi", new_district="Lucknow", new_posting="DM Lucknow",
           notification_number="UP/APP/2026/441", gov_order_link="https://up.gov.in/o.pdf",
           article_id=7, status="pending"),
        _T(id=103, officer_name="Vikas Rai", ias_batch="2011", notification_number="UP/APP/2026/441"),
        _T(id=104, officer_name="Meena Iyer", ias_batch="2014", article_id=7),
        _T(id=105, officer_name="Sunita Devi", ias_batch="2009"),
        _T(id=106, officer_name="Kiran Rao", ias_batch="2009", state="Kerala", cadre="Kerala"),
    ]
    officers = build_officers(rows, TODAY)
    anita = next(o for o in officers if o.name == "Anita Sharma")
    p = profile(anita, officers)

    assert p["current"]["to_district"] == "Lucknow"
    assert p["stats"]["movements"] == 2
    assert p["stats"]["districts"] == ["Varanasi", "Lucknow"]
    assert p["stats"]["average_tenure_days"] == 365
    assert p["stats"]["verified_movements"] == 1
    assert p["stats"]["sources"] == 2
    assert {"name": "ndtv.com", "url": "https://www.ndtv.com/b"} in p["sources"]
    assert p["orders"] == [{"number": "UP/APP/2026/441", "url": "https://up.gov.in/o.pdf",
                            "date": "2026-01-10"}]
    assert [(c["name"], c["relation"]) for c in p["co_transferred"]] == [
        ("Vikas Rai", "same_order"), ("Meena Iyer", "same_article")]
    # Same batch AND same cadre; Kerala's 2009 officer is not a batchmate.
    assert [b["name"] for b in p["batchmates"]] == ["Sunita Devi"]
    assert p["identity_notes"] == []

    # The payload satisfies the response model.
    from app.schemas.officer import OfficerProfile
    OfficerProfile(**p)


def test_profile_flags_conflicting_batches():
    (o,) = build_officers([_T(ias_batch="2009"), _T(ias_batch="2010")], TODAY)
    assert "2009, 2010" in profile(o, [o])["identity_notes"][0]


# --- directory ---------------------------------------------------------------
def test_directory_filters_and_sorts():
    officers = build_officers([
        _T(officer_name="Anita Sharma", transfer_date="2026-01-10"),
        _T(officer_name="Anita Sharma", transfer_date="2025-01-10"),
        _T(officer_name="Rohit Menon", ias_batch="2012", state="Maharashtra",
           cadre="Maharashtra", transfer_date="2026-06-01"),
        _T(officer_name="Mohd. Aijaz", ias_batch="2015", transfer_date="2024-03-01"),
    ], TODAY)
    names = lambda xs: [o.name for o in xs]  # noqa: E731
    assert names(directory(officers)) == ["Rohit Menon", "Anita Sharma", "Mohd. Aijaz"]
    assert names(directory(officers, sort="name")) == ["Anita Sharma", "Mohd. Aijaz", "Rohit Menon"]
    assert names(directory(officers, sort="movements"))[0] == "Anita Sharma"
    assert names(directory(officers, q="mohammad")) == ["Mohd. Aijaz"]   # variant search
    assert names(directory(officers, state="maha")) == ["Rohit Menon"]
    assert names(directory(officers, batch="2012 batch")) == ["Rohit Menon"]
    assert names(directory(officers, cadre="uttar")) == ["Anita Sharma", "Mohd. Aijaz"]


# --- public portal profile ---------------------------------------------------
def _public_case(wiki_hidden: bool = False):
    rows = [
        _T(id=201, officer_name="Ravi Menon", transfer_date="2025-03-01",
           new_district="Kozhikode", new_posting="Collector Kozhikode",
           state="Kerala", cadre="Kerala",
           source_url="https://news.example/ravi-1",
           corroborating_sources=["https://news.example/ravi-1", "https://other.example/r"]),
        _T(id=202, officer_name="Ravi Menon", transfer_date="2026-02-01",
           previous_district="Kozhikode", new_posting="Secretary, Health",
           state="Kerala", cadre="Kerala", source_url="https://news.example/ravi-2",
           gov_order_link="https://kerala.gov.in/order.pdf", notification_number="GO/12"),
    ]
    officers = build_officers(rows, TODAY)
    ravi = officers[0]
    wiki_img = "https://upload.wikimedia.org/ravi.jpg"
    research = {
        "status": "done", "requested_at": None, "researched_at": None, "error": None,
        "press": [{"url": "https://press.example/story", "title": "Ravi Menon takes charge",
                   "source": "Mathrubhumi", "published": "2026-02-02",
                   "snippet": "quoted snippet", "excerpt": "quoted excerpt", "verdict": "llm"}],
        "images": [
            {"image_url": wiki_img, "page_url": "https://en.wikipedia.org/wiki/File:Ravi.jpg",
             "caption": "Ravi Menon", "source": "Wikipedia", "origin": "wikipedia",
             "hidden": wiki_hidden},
            {"image_url": "https://press.example/photo.jpg", "page_url": "https://press.example/story",
             "caption": "Ravi Menon at an event", "source": "Mathrubhumi", "origin": "press"},
        ],
        "wikipedia": {"title": "Ravi Menon", "url": "https://en.wikipedia.org/wiki/Ravi_Menon",
                      "extract": "Ravi Menon is an IAS officer.", "image_url": wiki_img,
                      "image_page": "https://en.wikipedia.org/wiki/File:Ravi.jpg"},
    }
    if wiki_hidden:
        research["images"] = [i for i in research["images"] if not i.get("hidden")]
    return svc.public_profile(profile(ravi, officers), research)


def test_public_profile_publishes_no_article_links_or_quotes():
    import json

    from app.schemas.officer import PublicOfficerProfile

    out = _public_case()
    PublicOfficerProfile(**out)
    text = json.dumps(out)
    for private in ("news.example", "other.example", "press.example",
                    "quoted snippet", "quoted excerpt"):
        assert private not in text, private
    assert all("source_url" not in m for m in out["timeline"])
    assert "sources" not in out and "research" not in out and "identity_notes" not in out
    # Government orders are official documents and stay, as in the feed.
    assert out["orders"][0]["url"] == "https://kerala.gov.in/order.pdf"
    assert out["in_the_news"] == [
        {"title": "Ravi Menon takes charge", "source": "Mathrubhumi", "published": "2026-02-02"}]


def test_public_profile_shows_only_a_visible_wikipedia_photo():
    out = _public_case()
    assert out["photo_url"] == "https://upload.wikimedia.org/ravi.jpg"
    assert out["wikipedia"]["url"] == "https://en.wikipedia.org/wiki/Ravi_Menon"

    hidden = _public_case(wiki_hidden=True)
    assert hidden["photo_url"] is None
    assert hidden["wikipedia"]["image_url"] is None and hidden["wikipedia"]["image_page"] is None
    assert hidden["wikipedia"]["extract"]  # the text itself is still published


def test_public_profile_before_research():
    rows = [_T(id=301, officer_name="Lata Bose", transfer_date="2026-05-01")]
    officers = build_officers(rows, TODAY)
    out = svc.public_profile(profile(officers[0], officers), None)
    assert out["photo_url"] is None and out["wikipedia"] is None and out["in_the_news"] == []
