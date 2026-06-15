from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("")
def list_suggestions():
    return [
        "What can this assistant help with?",
        "Show me the latest uploaded documents.",
        "How does the knowledge search flow work?",
    ]
