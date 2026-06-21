from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from apps.backend.config import settings
from apps.backend.models import Document, DocumentChunk, User
from apps.backend.schemas import DocumentSchema


def list_documents(
    db: Session,
    user: User,
    domain: str | None = None,
    published_only: bool = False,
) -> list[DocumentSchema]:
    query = db.query(Document).filter(Document.user_id == user.id)
    if domain:
        query = query.filter(Document.domain == domain)
    if published_only:
        query = query.filter(Document.is_published.is_(True))
    documents = query.order_by(Document.created_at.desc()).all()
    return [_to_schema(item) for item in documents]


def get_document(db: Session, document_id: int, user: User) -> DocumentSchema | None:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    return _to_schema(document) if document else None


async def save_uploaded_document(
    db: Session,
    user: User,
    file: UploadFile,
    domain: str,
    tags: list[str],
    title: str = "",
) -> DocumentSchema:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    source_name = (title or file.filename or "uploaded-document").strip()
    original_name = file.filename or source_name
    suffix = Path(original_name).suffix
    target = upload_dir / f"user-{user.id}-{uuid.uuid4().hex}{suffix}"
    payload = await file.read()
    target.write_bytes(payload)

    document = Document(
        user_id=user.id,
        title=source_name[:255],
        domain=domain or "general",
        tags_json=json.dumps(tags, ensure_ascii=False),
        status="parsing",
        size=len(payload),
        summary="",
        source_path=str(target),
        is_published=True,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        chunks = _parse_document_chunks(str(target), document.title, document.domain)
        for chunk in chunks:
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    title=chunk["title"],
                    content=chunk["content"],
                )
            )
        document.summary = _build_summary(chunks)
        document.status = "ready"
    except Exception as exc:  # noqa: BLE001
        document.status = "failed"
        document.summary = f"Parsing failed: {exc}"
        db.add(document)
        db.commit()
        db.refresh(document)
        return _to_schema(document)

    db.add(document)
    db.commit()
    db.refresh(document)
    return _to_schema(document)


def _parse_document_chunks(file_path: str, title: str, domain: str) -> list[dict[str, str]]:
    from knowledge import DocumentProcessor

    processor = DocumentProcessor(
        default_domain=domain or "general",
        chunk_size=settings.retrieval_chunk_size,
        chunk_overlap=settings.retrieval_chunk_overlap,
    )
    parsed_chunks = processor.process_file(
        file_path,
        doc_id=Path(file_path).stem,
        domain=domain or "general",
        doc_type="knowledge",
        source=file_path,
    )
    results = []
    for index, chunk in enumerate(parsed_chunks, start=1):
        content = (chunk.content or "").strip()
        if not content:
            continue
        chunk_title = chunk.title_path or chunk.title or f"{title} - Chunk {index}"
        results.append({"title": chunk_title[:255], "content": content})
    if results:
        return results

    raw_text = Path(file_path).read_text(encoding="utf-8", errors="ignore").strip()
    if not raw_text:
        return []
    return [{"title": title[:255], "content": raw_text[: settings.retrieval_chunk_size * 2]}]


def _build_summary(chunks: list[dict[str, str]]) -> str:
    if not chunks:
        return "Document parsed successfully, but no text content was extracted."
    parts = []
    for chunk in chunks[:2]:
        parts.append(chunk["content"].strip())
    summary = "\n\n".join(parts).strip()
    return summary[:500]


def _to_schema(document: Document) -> DocumentSchema:
    return DocumentSchema(
        id=document.id,
        title=document.title,
        domain=document.domain,
        size=document.size,
        chunk_count=len(document.chunks),
        created_at=document.created_at,
        summary=document.summary,
        status=document.status,
        is_published=document.is_published,
    )
