from __future__ import annotations

import json
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from apps.backend.config import settings
from apps.backend.models import Document
from apps.backend.schemas import DocumentSchema


def list_documents(db: Session, domain: str | None = None, published_only: bool = False) -> list[DocumentSchema]:
    query = db.query(Document)
    if domain:
        query = query.filter(Document.domain == domain)
    if published_only:
        query = query.filter(Document.is_published.is_(True))
    documents = query.order_by(Document.created_at.desc()).all()
    return [_to_schema(item) for item in documents]


def get_document(db: Session, document_id: int) -> DocumentSchema | None:
    document = db.query(Document).filter(Document.id == document_id).first()
    return _to_schema(document) if document else None


async def save_uploaded_document(
    db: Session,
    file: UploadFile,
    domain: str,
    tags: list[str],
) -> DocumentSchema:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / file.filename
    payload = await file.read()
    target.write_bytes(payload)

    document = Document(
        title=file.filename,
        domain=domain or "general",
        tags_json=json.dumps(tags, ensure_ascii=False),
        status="parsing",
        size=len(payload),
        summary="Upload accepted. Parsing pipeline is not wired yet.",
        source_path=str(target),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return _to_schema(document)


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
