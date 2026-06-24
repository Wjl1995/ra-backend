from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolDescriptor:
    name: str
    description: str
    parameters: dict[str, Any]
    server_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallResult:
    tool_name: str
    content: str
    is_error: bool = False
    server_name: str | None = None
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResourceDescriptor:
    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None
    server_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResourceReadResult:
    uri: str
    content: Any
    mime_type: str | None = None
    server_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptDescriptor:
    name: str
    description: str = ""
    arguments_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptRenderResult:
    name: str
    content: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    server_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentTurnRequest:
    user_id: int
    session_id: int
    query: str
    document_id: int | None = None
    request_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentTurnResponse:
    answer: str
    refs: list[dict[str, Any]] = field(default_factory=list)
    tool_traces: list[dict[str, Any]] = field(default_factory=list)
    resource_refs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
