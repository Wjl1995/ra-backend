from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from fastapi import BackgroundTasks
from openai import OpenAI
from sqlalchemy.orm import Session

from apps.backend.agent_runtime import (
    AgentOrchestrator,
    AgentRuntimePolicy,
    AgentTurnRequest,
    AgentTurnResponse,
    LocalToolProvider,
    MCPToolProvider,
)
from apps.backend.config import settings
from apps.backend.models import ChatSession, Message, User
from apps.backend.mcp import MCPClientManager, build_default_stdio_registry, load_registry_from_json
from apps.backend.schemas import Citation, MessageSchema, RefSchema, SessionSchema
from apps.backend.services import search_service
from apps.backend.services.web_search_service import ingest_web_pages, run_web_search
from apps.backend.web.need_detector import WebNeedDetector
from knowledge import KnowledgeStore
from memory import AgentMemory
from tools import ToolRegistry


_detector = WebNeedDetector()

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
        refs = [Citation(**item) for item in _load_json_list(message.refs_json, fallback=[])]
        runtime_meta = _load_runtime_meta(message.runtime_meta_json)
        result.append(
            MessageSchema(
                id=message.id,
                role=message.role,
                content=message.content,
                refs=refs,
                tool_traces=list(runtime_meta.get("tool_traces", [])),
                resource_refs=list(runtime_meta.get("resource_refs", [])),
                metadata=dict(runtime_meta.get("metadata", {})),
                created_at=message.created_at,
            )
        )
    return result


def create_user_message(
    db: Session,
    session_id: int,
    user: User,
    content: str,
    *,
    web_mode: str = "auto",
    knowledge_mode: str = "auto",
) -> Message:
    session = _get_session(db, session_id, user)
    message = Message(
        session_id=session.id,
        role="user",
        content=content,
        refs_json="[]",
        web_mode=web_mode,
        knowledge_mode=knowledge_mode,
    )
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
    *,
    tool_traces: list[dict[str, Any]] | None = None,
    resource_refs: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    web_mode: str = "auto",
    knowledge_mode: str = "auto",
    web_search_run_id: int | None = None,
) -> MessageSchema:
    session = _get_session(db, session_id, user)
    raw_refs = json.dumps(refs, ensure_ascii=False)
    runtime_meta = {
        "tool_traces": list(tool_traces or []),
        "resource_refs": list(resource_refs or []),
        "metadata": dict(metadata or {}),
    }
    message = Message(
        session_id=session.id,
        role="assistant",
        content=content,
        refs_json=raw_refs,
        runtime_meta_json=json.dumps(runtime_meta, ensure_ascii=False),
        web_mode=web_mode,
        knowledge_mode=knowledge_mode,
        web_search_run_id=web_search_run_id,
    )
    session.updated_at = datetime.utcnow()
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageSchema(
        id=message.id,
        role=message.role,
        content=message.content,
        refs=[Citation(**item) for item in refs],
        tool_traces=runtime_meta["tool_traces"],
        resource_refs=runtime_meta["resource_refs"],
        metadata=runtime_meta["metadata"],
        created_at=message.created_at,
    )


async def build_kimi_answer(
    db: Session,
    session_id: int,
    user: User,
    document_id: int | None = None,
    *,
    web_mode: str = "auto",
    knowledge_mode: str = "auto",
    user_message_id: int | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> AgentTurnResponse:
    _get_session(db, session_id, user)
    if not settings.kimi_api_key:
        raise RuntimeError("Kimi API key is not configured")
    query = _get_latest_user_query(db, session_id)
    local_refs = _build_retrieval_refs(db, session_id, user, document_id)

    # 1) 联网判断（规则，预算内）
    local_confidence = max((r.get("score", 0.0) for r in local_refs), default=None)
    explicit_override = True if web_mode == "always" else (False if web_mode == "off" else None)
    decision = _detector.decide(query, local_confidence=local_confidence, explicit_override=explicit_override)

    # 2) 联网检索（同步预算内完成，失败优雅降级）
    web_citations: list[dict] = []
    web_outcome = None
    mid = user_message_id if user_message_id is not None else _get_latest_user_message_id(db, session_id)
    if decision.need_web and mid is not None:
        try:
            web_outcome = await run_web_search(
                user=user,
                session_id=session_id,
                message_id=mid,
                query=query,
            )
            web_citations = web_outcome.citations
        except Exception:  # noqa: BLE001 - 联网异常不应拖垮回答
            web_outcome = None
            web_citations = []

    merged_refs = list(local_refs) + web_citations

    history = _build_history_messages(db, session_id)
    request = AgentTurnRequest(
        user_id=user.id,
        session_id=session_id,
        query=query,
        document_id=document_id,
        context={
            "history_messages": history,
            "initial_refs": merged_refs,
            "document_scope": "single" if document_id is not None else "user",
            "role_scope": "user",
        },
    )
    response = await run_in_threadpool(_get_orchestrator().run_chat_turn, request)
    if not response.refs:
        response.refs = merged_refs

    # 3) 知识沉淀（异步，不影响回答延迟）
    run_id = web_outcome.run_id if web_outcome else None
    if background_tasks is not None and web_outcome is not None and web_outcome.pages:
        background_tasks.add_task(
            ingest_web_pages,
            user=user,
            session_id=session_id,
            message_id=mid,
            run_id=run_id,
            pages=web_outcome.pages,
            knowledge_mode=knowledge_mode,
        )

    # 轻量 web 信息挂到 metadata（不含大正文，避免返回给客户端）
    response.metadata = {
        **(response.metadata or {}),
        "web_search": {
            "need_web": decision.need_web,
            "reason": decision.reason,
            "run_id": run_id,
            "status": web_outcome.status if web_outcome else None,
            "citation_count": len(web_citations),
            "provider": web_outcome.provider if web_outcome else None,
        },
    }
    return response


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


def _get_latest_user_message_id(db: Session, session_id: int) -> int | None:
    message = (
        db.query(Message.id)
        .filter(Message.session_id == session_id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    return message[0] if message else None


def _is_summary_request(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in SUMMARY_HINT_KEYWORDS)


def _load_json_list(raw_json: str | None, fallback: list[Any]) -> list[Any]:
    try:
        payload = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        return list(fallback)
    return payload if isinstance(payload, list) else list(fallback)


def _load_runtime_meta(raw_json: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "tool_traces": payload.get("tool_traces") if isinstance(payload.get("tool_traces"), list) else [],
        "resource_refs": payload.get("resource_refs") if isinstance(payload.get("resource_refs"), list) else [],
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
