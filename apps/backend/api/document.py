from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User
from apps.backend.schemas import DocumentSchema
from apps.backend.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSchema])
def list_documents(
    domain: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return document_service.list_documents(db, current_user, domain=domain, published_only=False)


@router.get("/{document_id}", response_model=DocumentSchema)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = document_service.get_document(db, document_id, current_user)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("", response_model=DocumentSchema)
async def create_document(
    file: UploadFile = File(...),
    domain: str = Form(default="general"),
    tags: str = Form(default=""),
    title: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parsed_tags = [item.strip() for item in tags.split(",") if item.strip()]
    return await document_service.save_uploaded_document(
        db,
        current_user,
        file,
        domain,
        parsed_tags,
        title=title,
    )
