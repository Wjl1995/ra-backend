from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MCPRequestContext:
    user_id: int | None = None
    session_id: int | None = None
    document_id: int | None = None
    request_id: str | None = None
    document_scope: str | None = None
    role_scope: str | None = None


def parse_request_context(raw: dict[str, Any] | None) -> MCPRequestContext:
    raw = raw or {}
    return MCPRequestContext(
        user_id=_to_int(raw.get("user_id")),
        session_id=_to_int(raw.get("session_id")),
        document_id=_to_int(raw.get("document_id")),
        request_id=_to_str(raw.get("request_id")),
        document_scope=_to_str(raw.get("document_scope")),
        role_scope=_to_str(raw.get("role_scope")),
    )


def require_user_id(context: MCPRequestContext) -> int:
    if context.user_id is None:
        raise ValueError("user_id is required in MCP request context")
    return context.user_id


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
