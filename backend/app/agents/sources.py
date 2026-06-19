"""Discovery sources and search keywords for IAS transfer news."""
from __future__ import annotations

# Keywords searched on Google News (English; regional handled via hl/ceid).
SEARCH_KEYWORDS = [
    "IAS transfer",
    "IAS officer transferred",
    "District Magistrate transferred",
    "Collector transferred",
    "IAS reshuffle",
    "Administrative reshuffle",
    "Transfer posting IAS",
    "IAS posting",
    "Chief Secretary transfer",
]

# Hindi keyword variants (used when 'hi' is in DISCOVERY_LANGUAGES).
SEARCH_KEYWORDS_HI = [
    "आईएएस तबादला",
    "आईएएस अधिकारी स्थानांतरण",
    "जिलाधिकारी तबादला",
    "कलेक्टर स्थानांतरण",
    "प्रशासनिक फेरबदल",
]

# Direct RSS feeds from trusted outlets / portals. Discovery pulls these too,
# then filters headlines by keyword before queuing for extraction.
RSS_FEEDS = [
    ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ("The Hindu - National", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("Indian Express - India", "https://indianexpress.com/section/india/feed/"),
    ("Times of India - India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"),
    ("Hindustan Times - India", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"),
    ("LiveMint - News", "https://www.livemint.com/rss/news"),
    ("NDTV - India", "https://feeds.feedburner.com/ndtvnews-india-news"),
]

# Trusted source weighting for confidence scoring (government > wire > paper).
SOURCE_WEIGHTS = {
    "pib": 1.0,
    "dopt": 1.0,
    "gov.in": 0.95,
    "nic.in": 0.95,
    "ani": 0.85,
    "pti": 0.85,
    "thehindu": 0.8,
    "indianexpress": 0.8,
    "hindustantimes": 0.78,
    "timesofindia": 0.75,
    "livemint": 0.75,
    "ndtv": 0.72,
}


def source_weight(source_name: str | None, url: str | None) -> float:
    blob = f"{source_name or ''} {url or ''}".lower()
    best = 0.6  # default for an unknown but plausible news source
    for key, weight in SOURCE_WEIGHTS.items():
        if key in blob:
            best = max(best, weight)
    return best
