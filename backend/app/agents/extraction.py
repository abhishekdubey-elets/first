"""Article Extraction Agent.

For a discovered article it fetches the page and extracts: clean full text,
image URLs, PDF links, and likely government-order links. Government-order PDFs
are OCR'd (multimodal) and appended to the text so the Information Extraction
Agent can read scanned notifications too.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

from app.agents.base import BaseAgent
from app.agents.sources import source_weight
from app.core.logging import get_logger
from app.models.article import Article
from app.models.enums import ArticleStatus, LogLevel
from app.services import ocr

log = get_logger(__name__)

_GOV_HINTS = ("gov.in", "nic.in", "dopt", "gazette", "notification", "order")


def _looks_like_gov_order(href: str) -> bool:
    low = href.lower()
    return any(h in low for h in _GOV_HINTS)


class ExtractionAgent(BaseAgent):
    name = "extraction"

    def run(self, article: Article) -> bool:
        """Populate ``article`` with full text + media. Returns success.

        The page body is best-effort: Google News discovery links are encoded
        redirect URLs that can't be fetched (robots-disallowed / HTTP 400), and
        some publishers paywall or JS-render their text. Rather than dropping
        the article in those cases, we fall back to the HEADLINE — the
        Information Agent is designed to extract from sparse text and the
        Enrichment Agent backfills missing fields via web search on the next
        cycle. We only give up when there is no usable text at all.
        """
        # Prefer the publisher URL resolved at discovery: Google News redirect
        # links cannot be fetched by a bot, the real article can.
        url = article.resolved_url or article.url
        text, images, links, final_url = "", [], [], url

        if self.allowed_by_robots(url):
            try:
                resp = self.http_get(url)
                resp.raise_for_status()
                final_url = str(resp.url)
                text, images, links = self._parse_html(resp.text, final_url)
            except Exception as exc:  # noqa: BLE001 — fall back to the headline
                self.audit("extract", f"Fetch failed, using headline: {url}",
                           level=LogLevel.WARNING, article_id=article.id, error=str(exc))
        else:
            self.audit("extract", f"Robots-disallowed, using headline: {url}",
                       level=LogLevel.INFO, article_id=article.id)

        pdfs = [l for l in links if l.lower().endswith(".pdf")]
        gov_links = [l for l in links if _looks_like_gov_order(l)]

        # Multimodal: append OCR'd text from government-order PDFs.
        for pdf in pdfs[:3]:
            if _looks_like_gov_order(pdf):
                ocr_text = ocr.extract_pdf_text(pdf)
                if ocr_text.strip():
                    text += f"\n\n[GOVERNMENT ORDER PDF: {pdf}]\n{ocr_text}"

        # Use the fetched body when it's substantial; otherwise lean on the
        # headline so the article still gets a chance at extraction.
        body = (text or "").strip()
        full_text = body if len(body) >= 200 else (article.title or body or "").strip()
        if not full_text:
            article.status = ArticleStatus.IRRELEVANT
            article.error = "No usable text (empty body and no headline)"
            self.audit("extract", f"No usable text: {url}",
                       level=LogLevel.WARNING, article_id=article.id)
            return False

        article.full_text = full_text[:60000]
        # Remember where the text actually came from (after redirects) so the
        # transfer's source link points at the publisher, not a redirector.
        if final_url and final_url != article.url and not article.resolved_url:
            article.resolved_url = final_url[:2048]
        article.images = images[:20]
        article.pdf_links = pdfs[:20]
        article.gov_order_links = list(dict.fromkeys(gov_links))[:20]
        article.relevance_score = source_weight(article.source_name, final_url)
        article.status = ArticleStatus.EXTRACTED
        article.error = None
        self.audit("extract", f"Extracted {len(article.full_text)} chars: {final_url}",
                   article_id=article.id, chars=len(article.full_text),
                   pdfs=len(pdfs), gov_links=len(gov_links))
        return True

    def _parse_html(self, html: str, base_url: str):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # Prefer <article>, else the densest text container, else body.
        container = soup.find("article") or soup.find("main") or soup.body or soup
        text = container.get_text("\n", strip=True)

        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                images.append(urljoin(base_url, src))

        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if urlparse(href).scheme in ("http", "https"):
                links.append(href)

        return text, images, list(dict.fromkeys(links))
