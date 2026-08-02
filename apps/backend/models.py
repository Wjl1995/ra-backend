from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.backend.database import Base


# ════════════════════════════════════════════════════════════
#  现有模型（已扩展 Phase 1 字段）
# ════════════════════════════════════════════════════════════


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str] = mapped_column(String(64), default="")
    avatar: Mapped[str] = mapped_column(String(255), default="")
    daily_quota: Mapped[int] = mapped_column(Integer, default=50)
    daily_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New session")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    refs_json: Mapped[str] = mapped_column(Text, default="[]")
    runtime_meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── Phase 1: 联网与知识沉淀 ──
    web_mode: Mapped[str] = mapped_column(String(16), default="off")        # auto | off | always
    knowledge_mode: Mapped[str] = mapped_column(String(16), default="off")  # auto | off | ask | always
    web_search_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_search_runs.id"), nullable=True, index=True
    )
    knowledge_ingest_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_ingest_jobs.id"), nullable=True, index=True
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(64), default="general")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer, default=0)
    source_path: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── Phase 1: 来源与版本 ──
    source_type: Mapped[str] = mapped_column(String(32), default="upload")  # upload | web_search | crawl
    canonical_url: Mapped[str] = mapped_column(String(2048), default="", index=True)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True
    )
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    quality_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | accepted | review_required | rejected
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User | None] = relationship()
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        foreign_keys="DocumentVersion.document_id",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255), default="")

    # ── Phase 1: 版本关联与去重 ──
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    locator_json: Mapped[str] = mapped_column(Text, default="{}")

    document: Mapped[Document] = relationship(back_populates="chunks")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ════════════════════════════════════════════════════════════
#  Phase 1 新增 — 来源与抓取任务
# ════════════════════════════════════════════════════════════


class KnowledgeSource(Base):
    """可复用的抓取来源配置。

    一个 source 定义了种子 URL、允许域名和抓取策略，
    可以被多个 crawl_job 引用。
    """
    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    seed_type: Mapped[str] = mapped_column(String(32), nullable=False)  # url | sitemap | rss
    seed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    allowed_domains_json: Mapped[str] = mapped_column(Text, default="[]")
    policy_json: Mapped[str] = mapped_column(Text, default="{}")
    domain: Mapped[str] = mapped_column(String(64), default="general")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | paused | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    crawl_jobs: Mapped[list["CrawlJob"]] = relationship(back_populates="source")


class CrawlJob(Base):
    """一次抓取运行。

    origin 区分手动抓取、对话联网和定时刷新。
    状态机: queued → running → (succeeded | partially_succeeded | failed | cancelled)
    """
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_sources.id"), nullable=True, index=True
    )
    origin: Mapped[str] = mapped_column(String(32), default="manual_crawl")  # manual_crawl | chat_search | scheduled_refresh
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    # queued | running | cancelling | succeeded | partially_succeeded | failed | cancelled

    options_json: Mapped[str] = mapped_column(Text, default="{}")
    counters_json: Mapped[str] = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    source: Mapped[KnowledgeSource | None] = relationship(back_populates="crawl_jobs")
    pages: Mapped[list["CrawlPage"]] = relationship(back_populates="job")


class CrawlPage(Base):
    """frontier 中的单个页面及其抓取结果。

    状态: queued | fetching | fetched | normalized | organized | indexed | skipped | failed
    """
    __tablename__ = "crawl_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), default="", index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)

    adapter: Mapped[str | None] = mapped_column(String(32), nullable=True)  # http | crawl4ai | jina
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped[CrawlJob] = relationship(back_populates="pages")
    snapshots: Mapped[list["SourceSnapshot"]] = relationship(back_populates="page")


class SourceSnapshot(Base):
    """不可变的原始 HTTP/浏览器响应快照。

    存储键指向对象存储（过渡期为本地文件系统）。
    每个 crawl_page 可以有多个快照（重抓时追加版本）。
    """
    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    crawl_page_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_pages.id"), index=True, nullable=False
    )
    final_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="")
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    page: Mapped[CrawlPage] = relationship(back_populates="snapshots")


# ════════════════════════════════════════════════════════════
#  Phase 1 新增 — 文档版本与知识卡片
# ════════════════════════════════════════════════════════════


class DocumentVersion(Base):
    """文档内容的版本。

    每次重新抓取同一 URL 产生新版本，保留历史。
    normalized_storage_key 指向清洗后的 Markdown。
    """
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    normalized_storage_key: Mapped[str] = mapped_column(String(512), default="")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    language: Mapped[str] = mapped_column(String(16), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    quality_signals_json: Mapped[str] = mapped_column(Text, default="{}")
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )
    knowledge_cards: Mapped[list["KnowledgeCard"]] = relationship(back_populates="document_version")


class KnowledgeCard(Base):
    """LLM 整理后的结构化知识卡片。

    payload_json 包含摘要/主题/关键词/实体/事实/FAQ。
    status: pending | ready | failed | review_required
    """
    __tablename__ = "knowledge_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document_version: Mapped[DocumentVersion] = relationship(back_populates="knowledge_cards")
    evidence: Mapped[list["KnowledgeEvidence"]] = relationship(back_populates="card")


class KnowledgeEvidence(Base):
    """知识事实的证据绑定。

    每条证据关联到具体的文档版本和 chunk，
    包含原文引用和可选的位置区间。
    """
    __tablename__ = "knowledge_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    knowledge_card_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_cards.id"), index=True, nullable=False
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id"), index=True, nullable=False
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id"), nullable=True
    )
    quote: Mapped[str] = mapped_column(Text, default="")
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    card: Mapped[KnowledgeCard] = relationship(back_populates="evidence")


# ════════════════════════════════════════════════════════════
#  Phase 1 新增 — 对话联网与事件
# ════════════════════════════════════════════════════════════


class WebSearchRun(Base):
    """一次对话联网搜索的记录。

    记录搜索查询、provider、候选结果和实际使用情况。
    """
    __tablename__ = "web_search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id"), index=True, nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), index=True, nullable=False
    )
    query: Mapped[str] = mapped_column(String(512), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | completed | failed
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    chat_turn_sources: Mapped[list["ChatTurnSource"]] = relationship(back_populates="web_search_run")


class ChatTurnSource(Base):
    """回答与网页来源的绑定。

    每条记录对应回答中引用的一个来源，
    关联到 web_search_run 和/或 document_version。
    """
    __tablename__ = "chat_turn_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id"), index=True, nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), index=True, nullable=False
    )
    web_search_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_search_runs.id"), nullable=True, index=True
    )
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True, index=True
    )
    citation_id: Mapped[str] = mapped_column(String(64), default="")
    ref_type: Mapped[str] = mapped_column(String(32), default="web")  # web | document | knowledge
    url: Mapped[str] = mapped_column(String(2048), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    quote: Mapped[str] = mapped_column(Text, default="")
    source_domain: Mapped[str] = mapped_column(String(255), default="")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    web_search_run: Mapped[WebSearchRun | None] = relationship(back_populates="chat_turn_sources")


class KnowledgeIngestJob(Base):
    """对话来源转个人知识的异步任务。

    origin: chat_search | manual_save
    status: queued | running | succeeded | partially_succeeded | failed | cancelled
    document_ids_json 存储已创建的文档 ID 列表。
    """
    __tablename__ = "knowledge_ingest_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="chat_search")
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True, index=True
    )
    web_search_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("web_search_runs.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    counters_json: Mapped[str] = mapped_column(Text, default="{}")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobEvent(Base):
    """统一的任务事件表。

    供前端轮询进度、诊断和 SSE 推送使用。
    job_type 区分事件归属: crawl_job | ingest_job | chat_turn
    seq 为同一 job 内的递增序号，用于增量拉取。
    """
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), default="crawl_job")
    seq: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("job_id", "job_type", "seq", name="uq_job_events_job_type_seq"),
    )
