"""Ingest a single real article through the InformationAgent + DedupeAgent.

Used to demonstrate the live LLM extraction pipeline on a known IAS-transfer
article without waiting for the (CPU-slow) full discovery queue. Reads the
article text from a file passed as argv[1].
"""
from __future__ import annotations

import hashlib
import sys

from app.agents.dedupe import DedupeAgent
from app.agents.information import InformationAgent
from app.core.database import session_scope
from app.models.article import Article
from app.models.enums import ArticleStatus
from app.services import llm


def main(text_path: str) -> None:
    with open(text_path, encoding="utf-8") as fh:
        full_text = fh.read()

    url = "https://bureaucratsindia.in/news/appointments-transfers/andhra-pradesh-government-transfers-18-ias-officers-in-major-reshuffle"
    url_hash = hashlib.sha256(url.encode()).hexdigest()

    with session_scope() as db:
        article = db.query(Article).filter_by(url_hash=url_hash).one_or_none()
        if article is None:
            article = Article(
                url=url,
                url_hash=url_hash,
                title="Andhra Pradesh government transfers 18 IAS officers in major reshuffle",
                source_name="Bureaucrats India",
                publication="Bureaucrats India",
                language="en",
                full_text=full_text,
                status=ArticleStatus.EXTRACTED,
            )
            db.add(article)
            db.flush()

        print(f"Article id={article.id}; running InformationAgent (Ollama)...")
        extracted = InformationAgent(db).run(article)
        model_name = llm.active_model()
        print(f"LLM extracted {len(extracted)} transfer(s) using {model_name}")

        deduper = DedupeAgent(db)
        created_count = 0
        for item in extracted:
            record, created = deduper.upsert(item, article=article, model=model_name)
            created_count += int(created)
            print(f"  - {record.officer_name}: {record.previous_district} -> {record.new_district} "
                  f"(conf={record.confidence_score}, {'NEW' if created else 'updated'})")
        db.commit()
        print(f"Done. {created_count} new record(s) stored; article status={article.status.value}")


if __name__ == "__main__":
    main(sys.argv[1])
