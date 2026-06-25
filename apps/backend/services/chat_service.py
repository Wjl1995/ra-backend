from __future__ import annotations

import json
from datetime import datetime

from openai import OpenAI
from sqlalchemy.orm import Session

from apps.backend.agent_runtime import AgentOrchestrator, AgentRuntimePolicy, AgentTurnRequest, LocalToolProvider, MCPToolProvider
from apps.backend.config import settings
from apps.backend.models import ChatSession, Message, User
from apps.backend.mcp import MCPClientManager, build_default_stdio_registry, load_registry_from_json
from apps.backend.schemas import MessageSchema, RefSchema, SessionSchema
from apps.backend.services import search_service
from knowledge import KnowledgeStore
from memory import AgentMemory
from tools import ToolRegistry

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
_orchestrator: AgentOrchestrator | None = None


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


def build_kimi_answer(
    db: Session,
    session_id: int,
    user: User,
    document_id: int | None = None,
) -> tuple[str, list[dict]]:
    _get_session(db, session_id, user)
    if not settings.kimi_api_key:
        raise RuntimeError("Kimi API key is not configured")
    query = _get_latest_user_query(db, session_id)
    refs = _build_retrieval_refs(db, session_id, user, document_id)
    history = _build_history_messages(db, session_id)
    request = AgentTurnRequest(
        user_id=user.id,
        session_id=session_id,
        query=query,
        document_id=document_id,
        context={
            "history_messages": history,
            "initial_refs": refs,
            "document_scope": "single" if document_id is not None else "user",
            "role_scope": "user",
        },
    )
    response = _get_orchestrator().run_chat_turn(request)
    final_refs = response.refs or refs
    return response.answer, final_refs


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


def _get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator

    if settings.agent_tool_mode == "mcp":
        registry = (
            load_registry_from_json(settings.mcp_server_config_json)
            if settings.mcp_server_config_json
            else build_default_stdio_registry()
        )
        tool_provider = MCPToolProvider(MCPClientManager(registry))
    else:
        local_registry = ToolRegistry.create_default(
            memory=AgentMemory(),
            knowledge_store=KnowledgeStore(),
        )
        tool_provider = LocalToolProvider(local_registry)

    _orchestrator = AgentOrchestrator(
        tool_provider=tool_provider,
        llm_client=_get_client(),
        model=settings.kimi_model,
        max_tokens=settings.kimi_max_tokens,
        temperature=1.0,
        policy=AgentRuntimePolicy(max_tool_calls=settings.agent_max_tool_calls),
    )
    return _orchestrator


def _build_history_messages(db: Session, session_id: int) -> list[dict[str, str]]:
    history = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    if settings.kimi_max_context_messages > 0:
        history = history[-settings.kimi_max_context_messages :]

    messages: list[dict[str, str]] = []
    for item in history:
        if item.role not in {"user", "assistant"}:
            continue
        messages.append({"role": item.role, "content": item.content})
    return messages
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
