from __future__ import annotations

from typing import Any

from datetime import datetime

from pydantic import BaseModel, Field


class QuotaSchema(BaseModel):
    used: int
    total: int


class UserSchema(BaseModel):
    id: int
    nickname: str
    avatar: str
    quota: QuotaSchema
    username: str = ""
    account_bound: bool = False


class LoginRequest(BaseModel):
    code: str = Field(min_length=1)


class PasswordAuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user: UserSchema


class UpdateProfileRequest(BaseModel):
    nickname: str = ""
    avatar: str = ""


class SessionCreateRequest(BaseModel):
    title: str = "New session"


class SessionSchema(BaseModel):
    id: int
    title: str
    last_msg_at: datetime
    message_count: int


class RefSchema(BaseModel):
    document_id: int
    title: str
    snippet: str
    score: float


class Citation(BaseModel):
    """统一引用格式（Phase 3）。兼容 RefSchema 字段，扩展 web 来源字段。"""

    citation_id: str = ""
    ref_type: str = "document"  # web | document | knowledge
    document_id: int | str | None = None
    document_version_id: int | None = None
    title: str = ""
    url: str = ""
    source_domain: str = ""
    snippet: str = ""
    quote: str = ""
    score: float = 0.0
    fetched_at: datetime | None = None
    language: str = "unknown"


class SearchOptions(BaseModel):
    """联网检索可调参数（可选，缺省走服务端默认）。"""

    max_results: int | None = None
    max_fetch_pages: int | None = None


class MessageSchema(BaseModel):
    id: int
    role: str
    content: str
    refs: list[Citation]
    tool_traces: list[dict[str, Any]] = Field(default_factory=list)
    resource_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    document_id: int | None = None
    web_mode: str = "auto"          # auto | off | always
    knowledge_mode: str = "auto"    # auto | off | ask | always
    search_options: SearchOptions | None = None


class ThinkingResponse(BaseModel):
    status: str
    thinking_id: str | None = None
    message: MessageSchema | None = None


class DocumentSchema(BaseModel):
    id: int
    title: str
    domain: str
    size: int
    chunk_count: int
    created_at: datetime
    summary: str = ""
    status: str
    is_published: bool


class SearchResultSchema(BaseModel):
    id: int
    title: str
    snippet: str
    score: float
    document_id: int
