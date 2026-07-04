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


class LoginRequest(BaseModel):
    code: str = Field(min_length=1)


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


class MessageSchema(BaseModel):
    id: int
    role: str
    content: str
    refs: list[RefSchema]
    tool_traces: list[dict[str, Any]] = Field(default_factory=list)
    resource_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    document_id: int | None = None


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
