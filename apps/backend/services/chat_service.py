from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from apps.backend.models import ChatSession, Message, User
from apps.backend.schemas import MessageSchema, RefSchema, SessionSchema


def list_sessions(db: Session, user: User) -> list[SessionSchema]:
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        SessionSchema(
            id=session.id,
            title=session.title,
            last_msg_at=session.updated_at,
            message_count=len(session.messages),
        )
        for session in sessions
    ]


def create_session(db: Session, user: User, title: str) -> ChatSession:
    session = ChatSession(user_id=user.id, title=title, updated_at=datetime.utcnow())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_messages(db: Session, session_id: int, user: User) -> list[MessageSchema]:
    session = _get_session(db, session_id, user)
    result = []
    for message in session.messages:
        refs = [RefSchema(**item) for item in json.loads(message.refs_json or "[]")]
        result.append(
            MessageSchema(
                id=message.id,
                role=message.role,
                content=message.content,
                refs=refs,
                created_at=message.created_at,
            )
        )
    return result


def create_user_message(db: Session, session_id: int, user: User, content: str) -> Message:
    session = _get_session(db, session_id, user)
    message = Message(session_id=session.id, role="user", content=content, refs_json="[]")
    session.updated_at = datetime.utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def create_assistant_message(
    db: Session,
    session_id: int,
    user: User,
    content: str,
    refs: list[dict],
) -> MessageSchema:
    session = _get_session(db, session_id, user)
    raw_refs = json.dumps(refs, ensure_ascii=False)
    message = Message(session_id=session.id, role="assistant", content=content, refs_json=raw_refs)
    session.updated_at = datetime.utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageSchema(
        id=message.id,
        role=message.role,
        content=message.content,
        refs=[RefSchema(**item) for item in refs],
        created_at=message.created_at,
    )


def build_stubbed_answer(content: str, document_id: int | None = None) -> tuple[str, list[dict]]:
    refs = []
    if document_id is not None:
        refs.append(
            {
                "document_id": document_id,
                "title": f"Document {document_id}",
                "snippet": "Reference binding will be filled by the retrieval layer.",
                "score": 0.9,
            }
        )
    answer = (
        "Backend scaffold response: "
        f"received '{content[:80]}'"
        + (" with document scope." if document_id else ".")
    )
    return answer, refs


def _get_session(db: Session, session_id: int, user: User) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user.id)
        .first()
    )
    if session is None:
        raise ValueError("Session not found")
    return session
