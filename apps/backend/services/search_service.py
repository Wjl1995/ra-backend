from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from apps.backend.models import Document, DocumentChunk, User
from apps.backend.schemas import SearchResultSchema


@dataclass
class ChunkMatch:
    chunk_id: int
    document_id: int
    document_title: str
    chunk_title: str
    snippet: str
    score: float


def search_documents(
    db: Session,
    user: User,
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    published_only: bool = True,
) -> list[SearchResultSchema]:
    matches = retrieve_relevant_chunks(
        db,
        user=user,
        query=query,
        top_k=top_k,
        domain=domain,
        published_only=published_only,
    )
    if matches:
        unique_matches: dict[int, ChunkMatch] = {}
        for match in matches:
            existing = unique_matches.get(match.document_id)
            if existing is None or match.score > existing.score:
                unique_matches[match.document_id] = match
        ordered = sorted(unique_matches.values(), key=lambda item: item.score, reverse=True)[:top_k]
        return [
            SearchResultSchema(
                id=match.document_id,
                title=match.document_title,
                snippet=match.snippet,
                score=match.score,
                document_id=match.document_id,
            )
            for match in ordered
        ]

    rows = db.query(Document).filter(Document.user_id == user.id)
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


def retrieve_relevant_chunks(
    db: Session,
    user: User,
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    document_id: int | None = None,
    published_only: bool = True,
) -> list[ChunkMatch]:
    chunk_query = (
        db.query(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.user_id == user.id)
    )
    if domain:
        chunk_query = chunk_query.filter(Document.domain == domain)
    if document_id is not None:
        chunk_query = chunk_query.filter(Document.id == document_id)
    if published_only:
        chunk_query = chunk_query.filter(Document.is_published.is_(True))

    rows = chunk_query.order_by(Document.created_at.desc(), DocumentChunk.id.asc()).all()
    if not rows:
        return []

    query_text = (query or "").strip()
    if not query_text:
        matches = []
        for chunk, document in rows[:top_k]:
            matches.append(
                ChunkMatch(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    chunk_title=chunk.title,
                    snippet=chunk.content[:160],
                    score=0.5,
                )
            )
        return matches

    query_tokens = _tokenize(query_text)
    scored = []
    for chunk, document in rows:
        text = f"{document.title}\n{document.summary}\n{chunk.title}\n{chunk.content}"
        score = _score_text(query_text, query_tokens, text)
        if score <= 0:
            continue
        scored.append(
            ChunkMatch(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                chunk_title=chunk.title,
                snippet=chunk.content[:160],
                score=score,
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def _score_text(query_text: str, query_tokens: set[str], text: str) -> float:
    lowered_query = query_text.lower()
    lowered_text = text.lower()
    score = 0.0
    if lowered_query and lowered_query in lowered_text:
        score += 3.0

    text_tokens = _tokenize(text)
    overlap = query_tokens & text_tokens
    if overlap:
        score += float(len(overlap))

    if not score and any(token in lowered_text for token in query_tokens if len(token) > 1):
        score += 0.5
    return score


def _tokenize(text: str) -> set[str]:
    normalized = text.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9_]{2,}", normalized))
    cjk_sequences = re.findall(r"[\u4e00-\u9fff]+", normalized)
    cjk_tokens: set[str] = set()
    for seq in cjk_sequences:
        if len(seq) <= 3:
            cjk_tokens.add(seq)
            continue
        for size in (2, 3):
            for idx in range(len(seq) - size + 1):
                cjk_tokens.add(seq[idx : idx + size])
    return ascii_tokens | cjk_tokens
