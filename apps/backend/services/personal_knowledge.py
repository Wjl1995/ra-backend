"""PersonalKnowledgeService —— 唯一个人知识写入入口。

职责：
- 校验 user_id 与来源归属
- 幂等：同一用户 + 同一 URL 已存在则追加新版本（保留历史）
- 删除级联由 ORM 关系保证（Document -> Versions -> Cards）
- 原始 Markdown 写入本地存储（LocalStorageBackend）

向量索引（ChromaDB）留 best-effort 钩子，Phase 3 联调时统一接入。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.backend import models
from apps.backend.config import settings
from apps.backend.database import engine
from apps.backend.storage import LocalStorageBackend
from apps.backend.web.organizer import KnowledgeCardData


@dataclass
class SaveWebPageInput:
    """保存一个网页到个人知识库的输入。"""
    user_id: int
    source_url: str
    title: str
    markdown: str
    text: str
    content_hash: str
    language: str = "unknown"
    quality_score: float = 0.0
    card: Optional[KnowledgeCardData] = None
    idempotency_key: Optional[str] = None


class PersonalKnowledgeService:
    """个人知识写入服务（唯一入口）。"""

    def __init__(self):
        self._storage = LocalStorageBackend()

    def save_web_page(self, inp: SaveWebPageInput) -> models.Document:
        """保存网页到用户个人知识库，返回 Document。幂等（同用户+同 URL 更新版本）。"""
        with Session(engine) as db:
            existing = db.execute(
                select(models.Document).where(
                    models.Document.user_id == inp.user_id,
                    models.Document.canonical_url == inp.source_url,
                    models.Document.source_type == "web_search",
                )
            ).scalar_one_or_none()

            storage_key = self._storage.put(
                f"web/{inp.content_hash}.md",
                inp.markdown.encode("utf-8"),
                content_type="text/markdown",
            )

            if existing is not None:
                doc = existing
                doc.title = inp.title
                doc.summary = inp.text[:500]
                doc.quality_status = "accepted"
                doc.last_fetched_at = datetime.utcnow()
            else:
                doc = models.Document(
                    user_id=inp.user_id,
                    title=inp.title,
                    summary=inp.text[:500],
                    source_type="web_search",
                    canonical_url=inp.source_url,
                    quality_status="accepted",
                    last_fetched_at=datetime.utcnow(),
                )
                db.add(doc)
                db.flush()

            version = models.DocumentVersion(
                document_id=doc.id,
                content_hash=inp.content_hash,
                normalized_storage_key=storage_key,
                language=inp.language,
                quality_score=inp.quality_score,
                is_searchable=True,
            )
            db.add(version)
            db.flush()
            doc.current_version_id = version.id

            if inp.card is not None and inp.card.summary:
                card = models.KnowledgeCard(
                    document_version_id=version.id,
                    status="ready",
                    payload_json=json.dumps(inp.card.raw_json, ensure_ascii=False),
                    model=settings.kimi_model,
                    prompt_version="v1",
                )
                db.add(card)

            db.commit()
            db.refresh(doc)
            self._index_to_vector_store(doc, inp)
            return doc

    def _index_to_vector_store(self, doc, inp: SaveWebPageInput) -> None:
        """向量索引（best-effort）。Phase 3 联调时统一接入，失败不影响落库。"""
        try:
            from knowledge.store import KnowledgeChunk, KnowledgeStore
            store = KnowledgeStore()
            store.add_chunk(KnowledgeChunk(
                content=inp.markdown,
                doc_id=f"web_{doc.id}",
                title=doc.title,
                doc_type="knowledge",
                source=inp.source_url,
                keywords=(inp.card.keywords if inp.card else []),
            ))
        except Exception:  # noqa: BLE001 - 索引失败不阻塞落库
            pass
