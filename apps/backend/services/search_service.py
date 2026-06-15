from __future__ import annotations

from sqlalchemy.orm import Session

from apps.backend.models import Document
from apps.backend.schemas import SearchResultSchema


def search_documents(
    db: Session,
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    published_only: bool = True,
) -> list[SearchResultSchema]:
    rows = db.query(Document)
    if domain:
        rows = rows.filter(Document.domain == domain)
    if published_only:
        rows = rows.filter(Document.is_published.is_(True))

    results = []
    lowered = query.lower()
    for document in rows.order_by(Document.created_at.desc()).all():
        haystack = f"{document.title} {document.summary}".lower()
        if lowered in haystack or not query:
            results.append(
                SearchResultSchema(
                    id=document.id,
                    title=document.title,
                    snippet=document.summary[:160] or "No summary yet.",
                    score=0.8 if lowered in haystack else 0.5,
                    document_id=document.id,
                )
            )
        if len(results) >= top_k:
            break
    return results
