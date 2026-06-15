from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User
from apps.backend.schemas import SearchResultSchema
from apps.backend.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[SearchResultSchema])
def search(
    q: str = "",
    top_k: int = 5,
    domain: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return search_service.search_documents(db, query=q, top_k=top_k, domain=domain, published_only=False)
