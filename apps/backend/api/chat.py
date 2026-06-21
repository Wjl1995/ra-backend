from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.backend.content_security import is_safe_text
from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User
from apps.backend.schemas import MessageCreateRequest, MessageSchema, SessionCreateRequest, SessionSchema, ThinkingResponse
from apps.backend.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[SessionSchema])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return chat_service.list_sessions(db, current_user)


@router.post("/sessions", response_model=SessionSchema)
def create_session(
    payload: SessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = chat_service.create_session(db, current_user, payload.title)
    return SessionSchema(
        id=session.id,
        title=session.title,
        last_msg_at=session.updated_at,
        message_count=0,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageSchema])
def list_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return chat_service.list_messages(db, session_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/messages", response_model=MessageSchema)
def send_message(
    session_id: int,
    payload: MessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_safe_text(payload.content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe content")

    try:
        chat_service.create_user_message(db, session_id, current_user, payload.content)
        answer, refs = chat_service.build_kimi_answer(db, session_id, current_user, payload.document_id)
        return chat_service.create_assistant_message(db, session_id, current_user, answer, refs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/thinking/{thinking_id}", response_model=ThinkingResponse)
def get_thinking_status(thinking_id: str):
    return ThinkingResponse(status="not_found", thinking_id=thinking_id)
