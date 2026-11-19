"""Bio line, feed officer ids, and the Officer Research Agent (network faked)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.agents.officer_research import (
    OfficerResearchAgent,
    excerpt_around,
    extract_images,
    merge_images,
    page_excerpt,
    research_queue,
    search_name,
    search_queries,
    to_press,
    wikipedia_fits,
)
from app.api.routes.feed import to_record
from app.services.normalize import name_tokens, text_mentions
from app.services.officers import (
    best_photo,
    bio_line,
    build_officers,
    canonical_ids,
    research_for,
    research_view,
)
from tests.test_officers import _T

TODAY = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def _saranya(**kw):
    rows = [_T(officer_name="A. Katherine Saranya", cadre="Tamil Nadu", state="Tamil Nadu",
               ias_batch=None, transfer_date="2026-09-09",
               new_posting="Commissioner, Vellore Corporation", previous_posting="SIPCOT",
               **kw)]
    return build_officers(rows, TODAY)[0]


def _row(**kw):
    base = dict(officer_key="x|y", name_key="x", state=None, status="done", attempts=0,
                requested_at=None, researched_at=None, error=None, press=[], images=[],
                wikipedia=None, officer_id=None, officer_name="")
    base.update(kw)
    return SimpleNamespace(**base)


# --- bio ---------------------------------------------------------------------
def test_bio_matches_the_portal_sentence():
    assert bio_line(_saranya()) == (
        "A. Katherine Saranya is an Indian Administrative Service officer (Tamil Nadu "
        "cadre). Currently Commissioner, Vellore Corporation, Tamil Nadu. "
        "1 tracked posting change."
    )


def test_bio_does_not_repeat_a_place_already_in_the_role():
    (o,) = build_officers([
        _T(transfer_date="2025-02-03", new_posting="DM Varanasi", new_district="Varanasi"),
        _T(transfer_date="2026-03-05", new_posting="District Magistrate, Lucknow",
           new_district="Lucknow"),
    ], TODAY)
    assert bio_line(o) == (
        "Anita Sharma is an Indian Administrative Service officer (Uttar Pradesh cadre, "
        "2009 batch). Currently District Magistrate, Lucknow, Uttar Pradesh. "
        "2 tracked posting changes since 2025."
    )


def test_bio_for_a_retirement_and_unknown_cadre():
    (o,) = build_officers([_T(officer_name="R. Iyer", cadre=None, state=None, ias_batch=None,
                              reason="retires on superannuation",
                              new_posting="Chief Secretary")], TODAY)
    assert bio_line(o).startswith("R. Iyer is an Indian Administrative Service officer. "
                                  "Retired as Chief Secretary.")


# --- feed officer ids --------------------------------------------------------
def test_feed_records_of_one_officer_share_an_officer_id():
    rows = [_T(id=501, officer_name="Mohd. Aijaz"), _T(id=502, officer_name="Mohammad Aijaz"),
            _T(id=503, officer_name="Rohit Menon")]
    ids = canonical_ids(rows)
    assert ids[501] == ids[502] == "mohammad-aijaz--uttar-pradesh"
    assert to_record(rows[0], ids[501])["officer_id"] == "mohammad-aijaz--uttar-pradesh"
    # Without the grouped id, the record's own spelling still gives a working link.
    assert to_record(rows[0])["officer_id"] == "mohd-aijaz--uttar-pradesh"


# --- names in text -----------------------------------------------------------
def test_text_mentions_tolerates_initials_honorifics_and_variants():
    names = ["A. Katherine Saranya"]
    assert name_tokens("A. Katherine Saranya") == ["katherine", "saranya"]
    assert text_mentions("Dr Katherine Saranya takes charge in Vellore", names)
    assert not text_mentions("Saranya K appointed", names)
    assert text_mentions("Mohammad Aijaz reviews works", ["Mohd. Aijaz"])
    assert text_mentions("Anirudh Yadav", ["Aniruddh Yadav"])
    # Romanisation variants seen in real coverage...
    assert text_mentions("Mrs A Catherine Saranya as Commissioner", names)
    assert text_mentions("Srinivas Rao", ["Sreenivas Rao"])
    assert text_mentions("Vishvanath", ["Vishwanath"])
    # ...but not different names that merely look alike.
    assert not text_mentions("Rakesh Kumar", ["Ramesh Kumar"])
    assert not text_mentions("Sunita Sharma", ["Anita Sharma"])
    assert not text_mentions("Brajesh Kumar", ["Rajesh Kumar"])


# --- photos ------------------------------------------------------------------
_PAGE = """
<html><body>
 <img src="/static/logo.png" alt="Katherine Saranya news">
 <figure><img src="https://cdn.example.in/photos/ks.jpg">
   <figcaption>Vellore Corporation Commissioner A. Katherine Saranya</figcaption></figure>
 <img data-src="/img/meeting.jpg" alt="Katherine Saranya chairs a meeting with officials">
 <img src="/img/other.jpg" alt="Collector P. Kumar inspects roads">
 <img src="/img/tiny.jpg" width="40" alt="Katherine Saranya">
 <img src="data:image/png;base64,AAAA" alt="Katherine Saranya">
 <img srcset="/img/hero-800.jpg 800w, /img/hero-400.jpg 400w" alt="K. Saranya, IAS">
</body></html>
"""


def test_extract_images_keeps_only_photos_that_name_the_officer():
    found = extract_images(_PAGE, "https://news.example.in/story", ["A. Katherine Saranya"])
    assert [f["image_url"] for f in found] == [
        "https://cdn.example.in/photos/ks.jpg",
        "https://news.example.in/img/meeting.jpg",
    ]
    assert found[0]["caption"] == "Vellore Corporation Commissioner A. Katherine Saranya"
    assert found[0]["page_url"] == "https://news.example.in/story"


def test_best_photo_prefers_wikipedia_then_a_short_caption_and_skips_hidden():
    imgs = [
        {"image_url": "a", "caption": "Katherine Saranya chairs a meeting", "origin": "press"},
        {"image_url": "b", "caption": "Katherine Saranya", "origin": "press", "hidden": True},
        {"image_url": "c", "caption": "Commissioner Katherine Saranya", "origin": "press"},
    ]
    assert best_photo(imgs)["image_url"] == "c"
    assert best_photo([*imgs, {"image_url": "w", "caption": "x" * 50,
                               "origin": "wikipedia"}])["image_url"] == "w"
    assert best_photo([imgs[1]]) is None


def test_hidden_images_stay_hidden_after_research_again():
    old = [{"image_url": "a", "hidden": True}, {"image_url": "b", "hidden": False}]
    new = [{"image_url": "a", "caption": "x"}, {"image_url": "c", "caption": "y"}]
    assert [(i["image_url"], i["hidden"]) for i in merge_images(new, old)] == [
        ("a", True), ("c", False)]


# --- press -------------------------------------------------------------------
_NEWS = [
    {"title": "Katherine Saranya takes charge as Vellore Corporation Commissioner - The Hindu",
     "summary": "", "link": "https://news.google.com/rss/articles/1", "source": "The Hindu",
     "published": "Wed, 10 Sep 2026 04:00:00 GMT"},
    {"title": "Katherine Saranya wins state chess title - Local Times",
     "summary": "", "link": "https://news.google.com/rss/articles/2", "source": "Local Times",
     "published": "Mon, 01 Sep 2026 04:00:00 GMT"},
    {"title": "IAS reshuffle in Tamil Nadu - DT Next", "summary": "", "source": "DT Next",
     "link": "https://news.google.com/rss/articles/3", "published": ""},
]


class _FakeAgent(OfficerResearchAgent):
    def __init__(self, *, verdicts=None, wiki_pages=None, html=None):
        super().__init__(db=None)
        self.verdicts, self.wiki_pages, self.html = verdicts, wiki_pages or {}, html or {}

    def search(self, query):
        return _NEWS

    def classify(self, o, items):
        return None if self.verdicts is None else self.verdicts[: len(items)]

    def fetch_html(self, url):
        # Like the real one: a Google link comes back as the publisher's page.
        return self.html.get(url)

    def wiki(self, **params):
        if params.get("list") == "search":
            return {"query": {"search": [{"title": t} for t in self.wiki_pages]}}
        page = self.wiki_pages.get(params["titles"])
        return {"query": {"pages": [page] if page else []}}


def test_to_press_strips_the_publisher_suffix_and_parses_the_date():
    p = to_press(_NEWS[0])
    assert p["title"] == "Katherine Saranya takes charge as Vellore Corporation Commissioner"
    assert p["published"] == "2026-09-10" and p["source"] == "The Hindu"


def test_without_an_llm_press_must_mention_the_officers_places():
    press, _ = _FakeAgent().find_press(_saranya())
    # The chess story names her but nothing ties it to this officer; the
    # reshuffle story does not name her at all.
    assert [p["title"] for p in press] == [
        "Katherine Saranya takes charge as Vellore Corporation Commissioner"]
    assert press[0]["verdict"] == "context"


def test_with_an_llm_only_yes_verdicts_are_kept():
    press, _ = _FakeAgent(verdicts=["no", "yes"]).find_press(_saranya())
    assert [p["title"] for p in press] == ["Katherine Saranya wins state chess title"]
    assert press[0]["verdict"] == "llm"


# --- wikipedia ---------------------------------------------------------------
def test_wikipedia_namesake_is_rejected_and_the_officer_accepted():
    o = _saranya()
    assert not wikipedia_fits("Katherine Saranya is an Indian actress.", o)
    assert not wikipedia_fits("Katherine Saranya is an IAS officer of the Kerala cadre.", o)
    assert wikipedia_fits("A. Katherine Saranya is an Indian Administrative Service "
                          "officer of the Tamil Nadu cadre.", o)

    agent = _FakeAgent(wiki_pages={
        "Katherine Saranya (actress)": {"extract": "Katherine Saranya is an Indian actress."},
        "A. Katherine Saranya": {
            "extract": "A. Katherine Saranya is an IAS officer of the Tamil Nadu cadre.",
            "fullurl": "https://en.wikipedia.org/wiki/A._Katherine_Saranya",
            "thumbnail": {"source": "https://upload.wikimedia.org/ks.jpg"},
            "pageimage": "KS.jpg",
        },
    })
    wiki = agent.find_wikipedia(o)
    assert wiki["title"] == "A. Katherine Saranya"
    assert wiki["image_url"] == "https://upload.wikimedia.org/ks.jpg"
    assert wiki["image_page"] == "https://en.wikipedia.org/wiki/File:KS.jpg"


# --- the whole run -----------------------------------------------------------
def test_research_fills_the_row_and_keeps_admin_hidden_photos_hidden():
    google = "https://news.google.com/rss/articles/1"
    publisher = "https://news.example.in/story"
    agent = _FakeAgent(html={google: (publisher, _PAGE)})
    row = _row(images=[{"image_url": "https://cdn.example.in/photos/ks.jpg", "hidden": True}])
    assert agent.research(_saranya(), row)
    assert row.status == "done" and row.attempts == 1 and row.error is None
    # The press item now links to the publisher, and relative image paths are
    # resolved against the publisher's page, not the Google redirect.
    assert [p["url"] for p in row.press] == [publisher]
    assert {i["image_url"]: i["hidden"] for i in row.images} == {
        "https://cdn.example.in/photos/ks.jpg": True,
        "https://news.example.in/img/meeting.jpg": False,
    }
    assert all(i["origin"] == "press" and i["page_url"] == publisher for i in row.images)


def test_a_crash_marks_the_row_failed_instead_of_raising(monkeypatch):
    agent = _FakeAgent()
    monkeypatch.setattr(agent, "find_press", lambda o: 1 / 0)
    row = _row()
    assert agent.research(_saranya(), row) is False
    assert row.status == "failed" and "ZeroDivisionError" in row.error


# --- scheduling and read side -------------------------------------------------
def test_queue_order_is_requested_then_new_then_stale():
    officers = build_officers([
        _T(officer_name="Queued One", transfer_date="2026-01-01"),
        _T(officer_name="Never Seen", transfer_date="2026-06-01"),
        _T(officer_name="Never Again", transfer_date="2026-08-01"),
        _T(officer_name="Long Ago", transfer_date="2026-02-01"),
        _T(officer_name="Just Done", transfer_date="2026-02-01"),
    ], TODAY)
    by_name = {o.name: o for o in officers}
    rows = {
        by_name["Queued One"].key: _row(status="queued", requested_at=NOW),
        by_name["Long Ago"].key: _row(researched_at=NOW - timedelta(days=45)),
        by_name["Just Done"].key: _row(researched_at=NOW - timedelta(days=2)),
    }
    queue = research_queue(officers, rows, now=NOW, refresh_days=30, limit=10)
    assert [o.name for o in queue] == ["Queued One", "Never Again", "Never Seen", "Long Ago"]
    assert len(research_queue(officers, rows, now=NOW, refresh_days=30, limit=2)) == 2


def test_research_is_found_by_name_and_state_and_merged():
    o = build_officers([_T(officer_name="Neha Gupta", state="Delhi", cadre="AGMUT",
                           transfer_date="2025-06-04"),
                        _T(officer_name="Neha Gupta", state="Goa", cadre="AGMUT",
                           transfer_date="2026-09-01")], TODAY)[0]
    mine = _row(officer_key=o.key, name_key="nehagupta", state="Goa", researched_at=NOW,
                press=[{"url": "u1", "title": "a", "published": "2026-09-02"}],
                images=[{"image_url": "i1", "caption": "Neha Gupta", "origin": "press"}])
    older = _row(officer_key="nehagupta|delhi", name_key="nehagupta", state="Delhi",
                 researched_at=NOW - timedelta(days=60),
                 press=[{"url": "u1", "title": "a", "published": "2026-09-02"},
                        {"url": "u2", "title": "b", "published": "2025-06-05"}])
    namesake = _row(officer_key="nehagupta|bihar", name_key="nehagupta", state="Bihar",
                    press=[{"url": "u9", "title": "z"}])
    rows = research_for(o, [older, namesake, mine])
    assert rows == [mine, older]
    view = research_view(rows)
    assert [p["url"] for p in view["press"]] == ["u1", "u2"]
    assert view["photo"]["image_url"] == "i1"



# --- names only in the body; namesakes ---------------------------------------
_RESHUFFLE = """<html><body><article>
 <h1>Tamil Nadu government transfers 27 IAS officers</h1>
 <p>Several district collectors were moved on Tuesday.</p>
 <p>A. Katherine Saranya, Joint Managing Director, SIPCOT, has been posted as
 Commissioner, Vellore Corporation.</p>
 <figure><img src="/p/group.jpg"><figcaption>Secretariat, Chennai</figcaption></figure>
</article></body></html>"""

_CHESS = """<html><body><article><p>Katherine Saranya, 14, won the under-16 title.</p>
 <img src="/p/chess.jpg" alt="Katherine Saranya with her trophy"></article></body></html>"""


def test_search_drops_initials_and_does_not_quote():
    assert search_name("A. Katherine Saranya") == "Katherine Saranya"
    assert search_name("Dr. K.K. Pathak") == "Pathak"
    assert search_name("Mohd. Aijaz") == "Mohd Aijaz"
    assert search_queries(_saranya()) == ["Katherine Saranya IAS", "Katherine Saranya Tamil Nadu"]


def test_excerpt_is_cut_around_the_name():
    text = "x " * 300 + "posted A. Katherine Saranya as Commissioner, Vellore " + "y " * 300
    ex = excerpt_around(text, ["A. Katherine Saranya"], width=40)
    assert ex.startswith("…") and ex.endswith("…") and "Katherine Saranya" in ex
    assert excerpt_around("no names here", ["A. Katherine Saranya"]) is None
    # Cut to the sentence that names the officer, not the sidebar before it.
    page = ("Rahul Gandhi says the opposition will expose irregularities. "
            "Prominent IAS officer Tina Dabi assumed charge as Collector of Tonk. "
            "Read more: weather updates for Jaipur.")
    assert excerpt_around(page, ["Tina Dabi"]) == (
        "…Prominent IAS officer Tina Dabi assumed charge as Collector of Tonk.…")


def test_reshuffle_story_counts_when_only_its_body_names_the_officer():
    reshuffle = "https://news.google.com/rss/articles/3"
    agent = _FakeAgent(html={reshuffle: ("https://dtnext.in/tn-reshuffle", _RESHUFFLE)})
    press, images = agent.find_press(_saranya())
    titles = {p["title"]: p for p in press}
    assert "IAS reshuffle in Tamil Nadu" in titles
    item = titles["IAS reshuffle in Tamil Nadu"]
    assert item["url"] == "https://dtnext.in/tn-reshuffle"
    assert "SIPCOT" in item["excerpt"] and item["verdict"] == "context"
    # The group photo's caption doesn't name her, so it isn't her photo.
    assert images == []


def test_a_namesakes_captioned_photo_is_never_kept():
    chess = "https://news.google.com/rss/articles/2"
    agent = _FakeAgent(html={chess: ("https://localtimes.in/chess", _CHESS)})
    press, images = agent.find_press(_saranya())
    assert "Katherine Saranya wins state chess title" not in {p["title"] for p in press}
    assert images == []


def test_wikipedia_accepts_civil_servant_wording_with_the_right_state():
    (o,) = build_officers([_T(officer_name="Tina Dabi", state="Rajasthan", cadre="Rajasthan",
                              ias_batch="2016", new_posting="Collector, Barmer",
                              new_district="Barmer", transfer_date="2024-02-20")], TODAY)
    assert wikipedia_fits("Tina Dabi (born 1993) is an Indian civil servant in Rajasthan.", o)
    assert not wikipedia_fits("Tina Dabi is an Indian civil servant in Kerala.", o)


def test_rate_limited_run_keeps_earlier_results_and_is_retried_next_day(monkeypatch):
    from app.services import gnews

    monkeypatch.setattr(gnews, "is_rate_limited", lambda: True)
    agent = _FakeAgent()
    monkeypatch.setattr(agent, "find_press", lambda o: ([], []))
    earlier = [{"url": "u", "title": "t"}]
    row = _row(press=earlier, status="done")
    assert agent.research(_saranya(), row) is False
    assert row.status == "failed" and "rate-limited" in row.error
    assert row.press == earlier                       # not wiped

    o = _saranya()
    failed = {o.key: _row(status="failed", researched_at=NOW - timedelta(days=2))}
    assert research_queue([o], failed, now=NOW, refresh_days=30, limit=5) == [o]
    recent = {o.key: _row(status="failed", researched_at=NOW - timedelta(hours=3))}
    assert research_queue([o], recent, now=NOW, refresh_days=30, limit=5) == []


def test_page_excerpt_prefers_the_story_paragraph_over_sidebar_headlines():
    html = """<html><body><div class="sidebar">
      <a>Prominent IAS officer Tina Dabi assumes charge as District Collector of Tonk</a>
      <a>Rahul Gandhi says opposition will expose irregularities</a></div>
      <div class="story"><p>Jaipur, April 5: Tina Dabi took charge as Collector of Tonk on
      Sunday after the state's reshuffle.</p></div></body></html>"""
    assert page_excerpt(html, ["Tina Dabi"]) == (
        "Jaipur, April 5: Tina Dabi took charge as Collector of Tonk on Sunday after the "
        "state's reshuffle.")


def test_common_names_need_a_district_or_post_not_just_the_state():
    (o,) = build_officers([_T(officer_name="Rajesh Kumar", state="Odisha", cadre="Odisha",
                              ias_batch=None, new_posting="Collector, Cuttack",
                              new_district="Cuttack", transfer_date="2026-10-07")], TODAY)

    class Agent(_FakeAgent):
        def search(self, query):
            return [
                {"title": "Odisha recalls Asika Municipality Executive Officer Rajesh Kumar "
                          "Mohapatra - Pragativadi", "summary": "", "source": "Pragativadi",
                 "link": "https://news.google.com/rss/articles/r1",
                 "published": "Wed, 04 Nov 2026 04:00:00 GMT"},
                {"title": "Rajesh Kumar takes charge as Cuttack Collector - Sambad",
                 "summary": "", "source": "Sambad", "link": "https://news.google.com/rss/articles/r2",
                 "published": "Thu, 08 Oct 2026 04:00:00 GMT"},
            ]

    press, _ = Agent().find_press(o)
    assert [p["title"] for p in press] == ["Rajesh Kumar takes charge as Cuttack Collector"]
    # A distinctive name may still match on the state alone.
    assert not ora_common(_saranya())


def ora_common(o):
    from app.agents.officer_research import common_name

    return common_name(o)


def test_name_words_must_appear_together():
    assert not text_mentions("Rajesh Sharma and Anil Kumar inspected the site", ["Rajesh Kumar"])
    assert text_mentions("Collector Rajesh Kumar, IAS, inspected", ["Rajesh Kumar"])
    assert text_mentions("Mrs A Catherine Saranya as Commissioner", ["A. Katherine Saranya"])
