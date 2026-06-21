from __future__ import annotations

import json
from datetime import datetime

from openai import OpenAI
from sqlalchemy.orm import Session

from apps.backend.config import settings
from apps.backend.models import ChatSession, Message, User
from apps.backend.schemas import MessageSchema, RefSchema, SessionSchema
from apps.backend.services import search_service

SYSTEM_PROMPT = (
    "You are ReActAgent, a helpful assistant for a WeChat mini app. "
    "Answer clearly and concisely in Chinese unless the user asks for another language. "
    "If document context is provided, prioritize it and say when information is uncertain."
)
SUMMARY_HINT_KEYWORDS = (
    "总结",
    "概括",
    "摘要",
    "概述",
    "主要内容",
    "讲了什么",
    "说了什么",
    "介绍一下",
    "summarize",
    "summary",
    "overview",
    "tldr",
    "tl;dr",
)

_client: OpenAI | None = None


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
    _get_session(db, session_id, user)
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    result = []
    for message in messages:
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


def build_kimi_answer(db: Session, session_id: int, user: User, document_id: int | None = None) -> tuple[str, list[dict]]:
    _get_session(db, session_id, user)
    if not settings.kimi_api_key:
        raise RuntimeError("Kimi API key is not configured")

    refs = _build_retrieval_refs(db, session_id, user, document_id)
    messages = _build_kimi_messages(db, session_id, refs)

    try:
        response = _get_client().chat.completions.create(
            model=settings.kimi_model,
            messages=messages,
            temperature=1.0,
            max_tokens=settings.kimi_max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Kimi request failed: {exc}") from exc

    answer = _extract_text(response)
    if not answer:
        raise RuntimeError("Kimi returned an empty response")
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


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
            timeout=settings.kimi_timeout_seconds,
        )
    return _client


def _build_kimi_messages(db: Session, session_id: int, refs: list[dict]) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    document_context = _build_document_context(refs)
    if document_context:
        messages.append({"role": "system", "content": document_context})

    history = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    if settings.kimi_max_context_messages > 0:
        history = history[-settings.kimi_max_context_messages :]

    for item in history:
        if item.role not in {"user", "assistant"}:
            continue
        messages.append({"role": item.role, "content": item.content})
    return messages


def _build_document_context(refs: list[dict]) -> str:
    if not refs:
        return ""
    lines = [
        "Use the following retrieved knowledge snippets when they are relevant.",
        "Prefer these snippets over guesswork, and mention uncertainty when the snippets are incomplete.",
    ]
    for index, ref in enumerate(refs, start=1):
        lines.append(
            f"[Snippet {index}] Document {ref['document_id']} - {ref['title']}\n{ref['snippet']}"
        )
    return "\n\n".join(lines)


def _build_retrieval_refs(
    db: Session,
    session_id: int,
    user: User,
    document_id: int | None,
) -> list[dict]:
    query = _get_latest_user_query(db, session_id)
    if not query and document_id is None:
        return []

    retrieval_top_k = settings.retrieval_top_k
    if document_id is not None and _is_summary_request(query):
        matches = search_service.retrieve_relevant_chunks(
            db,
            user=user,
            query="",
            top_k=max(retrieval_top_k, 6),
            document_id=document_id,
            published_only=False,
        )
    else:
        matches = search_service.retrieve_relevant_chunks(
            db,
            user=user,
            query=query,
            top_k=retrieval_top_k,
            document_id=document_id,
            published_only=False,
        )

    if not matches and document_id is not None:
        matches = search_service.retrieve_relevant_chunks(
            db,
            user=user,
            query="",
            top_k=max(retrieval_top_k, 6),
            document_id=document_id,
            published_only=False,
        )

    return [
        {
            "document_id": match.document_id,
            "title": match.chunk_title or match.document_title,
            "snippet": match.snippet,
            "score": round(match.score, 4),
        }
        for match in matches
    ]


def _get_latest_user_query(db: Session, session_id: int) -> str:
    message = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    return message.content if message else ""


def _is_summary_request(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in SUMMARY_HINT_KEYWORDS)


def _extract_text(response) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as exc:
        raise RuntimeError("Unexpected response format from Kimi") from exc

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts).strip()
    return str(content).strip()
