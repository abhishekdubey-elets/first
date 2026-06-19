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
        """Populate ``article`` with full text + media. Returns success."""
        url = article.url
        if not self.allowed_by_robots(url):
            article.status = ArticleStatus.IRRELEVANT
            article.error = "Disallowed by robots.txt"
            self.audit("extract", f"Skipped (robots.txt): {url}",
                       level=LogLevel.WARNING, article_id=article.id)
            return False

        try:
            resp = self.http_get(url)
            resp.raise_for_status()
            html = resp.text
            final_url = str(resp.url)
        except Exception as exc:  # noqa: BLE001
            article.status = ArticleStatus.FAILED
            article.error = f"Fetch failed: {exc}"
            self.audit("extract", f"Fetch failed: {url}", level=LogLevel.ERROR,
                       article_id=article.id, error=str(exc))
            return False

        text, images, links = self._parse_html(html, final_url)

        pdfs = [l for l in links if l.lower().endswith(".pdf")]
        gov_links = [l for l in links if _looks_like_gov_order(l)]

        # Multimodal: append OCR'd text from government-order PDFs.
        for pdf in pdfs[:3]:
            if _looks_like_gov_order(pdf):
                ocr_text = ocr.extract_pdf_text(pdf)
                if ocr_text.strip():
                    text += f"\n\n[GOVERNMENT ORDER PDF: {pdf}]\n{ocr_text}"

        article.full_text = (text or article.title or "")[:60000]
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
