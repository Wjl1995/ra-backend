"""PersonalKnowledgeService —— 唯一个人知识写入入口。

职责：
- 校验 user_id 与来源归属
- 幂等：同一用户 + 同一 URL 已存在则追加新版本（保留历史）
- 删除级联由 ORM 关系保证（Document -> Versions -> Cards）
- 原始 Markdown 写入本地存储（LocalStorageBackend）

向量索引（ChromaDB）留 best-effort 钩子，Phase 3 联调时统一接入。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.backend import models
from apps.backend.config import settings
from apps.backend.database import engine
from apps.backend.storage import LocalStorageBackend


@dataclass
class SaveWebSynthesisInput:
    """把一次联网检索「合成回答 + 引用链接」沉淀到个人知识库的输入。

    折中方案：不存原始网页全文，只存「经 LLM 整合后的回答（主）+
    每条引用的标题/链接/摘要片段（辅）」，既瘦身又保留一手可追溯性。
    """

    user_id: int
    query: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    idempotency_key: Optional[str] = None  # 通常取 message_id，保证幂等


class PersonalKnowledgeService:
    """个人知识写入服务（唯一入口）。"""

    def __init__(self):
        self._storage = LocalStorageBackend()

    def save_web_synthesis(self, inp: SaveWebSynthesisInput) -> Optional[models.Document]:
        """把联网合成结果（回答+引用）沉淀到用户个人知识库，返回 Document。

        幂等：同 user_id + 同 idempotency_key（message_id）更新版本。
        存库内容 = 合成回答 + 来源摘要（含链接），不再存整页原文。
        """
        if not inp.answer or not inp.citations:
            return None
        content = self._build_synthesis_markdown(inp.query, inp.answer, inp.citations)
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        canonical = f"web_synthesis:{inp.idempotency_key or content_hash}"

        with Session(engine) as db:
            existing = db.execute(
                select(models.Document).where(
                    models.Document.user_id == inp.user_id,
                    models.Document.canonical_url == canonical,
                    models.Document.source_type == "web_synthesis",
                )
            ).scalar_one_or_none()

            storage_key = self._storage.put(
                f"web_syn/{content_hash}.md",
                content.encode("utf-8"),
                content_type="text/markdown",
            )

            if existing is not None:
                doc = existing
                doc.title = inp.query[:200]
                doc.summary = inp.answer[:500]
                doc.last_fetched_at = datetime.utcnow()
            else:
                doc = models.Document(
                    user_id=inp.user_id,
                    title=inp.query[:200],
                    summary=inp.answer[:500],
                    source_type="web_synthesis",
                    canonical_url=canonical,
                    quality_status="accepted",
                    last_fetched_at=datetime.utcnow(),
                )
                db.add(doc)
                db.flush()

            version = models.DocumentVersion(
                document_id=doc.id,
                content_hash=content_hash,
                normalized_storage_key=storage_key,
                language="zh",
                quality_score=1.0,
                is_searchable=True,
            )
            db.add(version)
            db.flush()
            doc.current_version_id = version.id

            db.commit()
            db.refresh(doc)
            self._index_to_vector_store(
                doc,
                content=content,
                user_id=inp.user_id,
                title=inp.query[:200],
                source="web_synthesis",
            )
            return doc

    @staticmethod
    def _build_synthesis_markdown(query: str, answer: str, citations: list[dict]) -> str:
        """把「回答 + 引用来源」拼成可检索的 Markdown（折中：主回答 + 辅摘要）。"""
        lines = [f"# {query}", "", answer.strip(), "", "## 引用来源"]
        for index, ref in enumerate(citations, start=1):
            title = ref.get("title") or ref.get("url") or f"来源{index}"
            url = ref.get("url") or ""
            snippet = (ref.get("snippet") or "").strip().replace("\n", " ")
            snippet = snippet[:400]
            lines.append(f"[{index}] {title} — {url}")
            if snippet:
                lines.append(f"    {snippet}")
        return "\n".join(lines)

    def _index_to_vector_store(
        self,
        doc,
        *,
        content: str,
        user_id: int,
        title: str = "",
        source: str = "",
    ) -> None:
        """向量索引（best-effort，按 user_id 隔离）。失败不影响落库。"""
        try:
            from knowledge.store import KnowledgeChunk, KnowledgeStore
            store = KnowledgeStore()
            store.add_chunk(KnowledgeChunk(
                content=content,
                doc_id=f"websyn_{doc.id}",
                title=title or doc.title,
                doc_type="knowledge",
                source=source,
                user_id=user_id,
            ))
        except Exception:  # noqa: BLE001 - 索引失败不阻塞落库
            pass
