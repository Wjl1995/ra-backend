"""
Knowledge Store —— 知识库存储层

基于 ChromaDB 的多 Collection 知识管理：
- knowledge: 通用领域知识（FAQ、文档片段、术语解释）
- rules: 规则与约束（SOP、审批边界、禁止事项）
- cases: 案例与经验（历史案例、复盘、决策记录）

每个 Collection 独立管理，支持：
- 语义检索 + 元数据过滤
- 按领域 / 文档类型 / 来源筛选
- 混合召回
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb

from memory.memory import HashEmbeddingFunction, create_embedding_function
from config import CHROMA_PERSIST_DIR, LONG_TERM_MEMORY_TOP_K


# ─── 知识条目数据类 ──────────────────────────────────────────

class KnowledgeChunk:
    """一条知识片段"""

    def __init__(
        self,
        content: str,
        chunk_id: Optional[str] = None,
        doc_id: Optional[str] = None,
        title: str = "",
        title_path: str = "",
        domain: str = "general",
        doc_type: str = "knowledge",  # knowledge / rule / case
        source: str = "",
        keywords: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        priority: int = 5,
        metadata: Optional[dict] = None,
    ):
        self.chunk_id = chunk_id or str(uuid.uuid4())
        self.content = content
        self.doc_id = doc_id or ""
        self.title = title
        self.title_path = title_path
        self.domain = domain
        self.doc_type = doc_type
        self.source = source
        self.keywords = keywords or []
        self.tags = tags or []
        self.priority = priority
        self._extra_meta = metadata or {}

    def to_chroma_meta(self) -> dict:
        meta = {
            "doc_id": self.doc_id,
            "title": self.title,
            "title_path": self.title_path,
            "domain": self.domain,
            "doc_type": self.doc_type,
            "source": self.source,
            "keywords": json.dumps(self.keywords, ensure_ascii=False),
            "tags": json.dumps(self.tags, ensure_ascii=False),
            "priority": self.priority,
            "ingested_at": datetime.now().isoformat(),
        }
        meta.update(self._extra_meta)
        return meta


# ─── 知识库存储 ──────────────────────────────────────────────

class KnowledgeStore:
    """
    知识库存储管理器

    三个独立 Collection：
      - knowledge: 通用知识片段
      - rules: 规则与约束
      - cases: 案例与经验
    """

    COLLECTION_NAMES = ["knowledge", "rules", "cases"]

    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        embedding_mode: str = "hash",
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_fn = create_embedding_function(embedding_mode)
        self.collections = {}
        for name in self.COLLECTION_NAMES:
            self.collections[name] = self.client.get_or_create_collection(
                name=f"kb_{name}",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )

    def _get_collection(self, doc_type: str) -> chromadb.Collection:
        """根据 doc_type 获取对应 collection"""
        mapping = {
            "knowledge": "knowledge",
            "rule": "rules",
            "case": "cases",
        }
        col_name = mapping.get(doc_type, "knowledge")
        return self.collections[col_name]

    # ─── 写入 ────────────────────────────────────────────

    def add_chunk(self, chunk: KnowledgeChunk) -> str:
        """写入一条知识片段"""
        collection = self._get_collection(chunk.doc_type)
        collection.upsert(
            ids=[chunk.chunk_id],
            documents=[chunk.content],
            metadatas=[chunk.to_chroma_meta()],
        )
        return chunk.chunk_id

    def add_chunks(self, chunks: list[KnowledgeChunk]) -> list[str]:
        """批量写入"""
        if not chunks:
            return []
        # 按 doc_type 分组写入
        ids = []
        for chunk in chunks:
            ids.append(self.add_chunk(chunk))
        return ids

    # ─── 检索 ────────────────────────────────────────────

    def search(
        self,
        query: str,
        doc_type: Optional[str] = None,
        domain: Optional[str] = None,
        tags: Optional[list[str]] = None,
        top_k: int = LONG_TERM_MEMORY_TOP_K,
    ) -> list[dict]:
        """
        语义检索知识

        Args:
            query: 查询文本
            doc_type: 限定文档类型 (knowledge/rule/case)，None 则搜索全部
            domain: 限定领域
            tags: 限定标签
            top_k: 返回条数
        """
        results = []

        # 确定搜索哪些 collection
        if doc_type:
            collections_to_search = {
                doc_type: self._get_collection(doc_type)
            }
        else:
            collections_to_search = self.collections

        for col_type, collection in collections_to_search.items():
            count = collection.count()
            if count == 0:
                continue

            # 构建 where 过滤条件
            where = None
            conditions = []
            if domain:
                conditions.append({"domain": domain})
            if tags:
                conditions.append({"tags": {"$contains": json.dumps(tags, ensure_ascii=False)}})
            # ChromaDB 支持的过滤方式有限，简化处理
            # 对于 tags 的精确匹配，我们在结果中做后过滤

            if len(conditions) == 1:
                where = conditions[0]
            elif len(conditions) > 1:
                where = {"$and": conditions}

            try:
                query_result = collection.query(
                    query_texts=[query],
                    n_results=min(top_k, count),
                    where=where,
                )
            except Exception:
                # where 条件可能不兼容，降级为无过滤
                query_result = collection.query(
                    query_texts=[query],
                    n_results=min(top_k, count),
                )

            if query_result and query_result["documents"]:
                for doc, meta, dist in zip(
                    query_result["documents"][0],
                    query_result["metadatas"][0],
                    query_result["distances"][0],
                ):
                    # 后过滤 tags
                    if tags:
                        chunk_tags = json.loads(meta.get("tags", "[]"))
                        if not any(t in chunk_tags for t in tags):
                            continue

                    results.append({
                        "content": doc,
                        "metadata": meta,
                        "score": 1 - dist,
                        "collection": col_type,
                    })

        # 按相似度排序，取 top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_knowledge(self, query: str, domain: str = None, top_k: int = 5) -> list[dict]:
        """搜索通用知识"""
        return self.search(query, doc_type="knowledge", domain=domain, top_k=top_k)

    def search_rules(self, query: str, domain: str = None, top_k: int = 5) -> list[dict]:
        """搜索规则"""
        return self.search(query, doc_type="rule", domain=domain, top_k=top_k)

    def search_cases(self, query: str, tags: list[str] = None, top_k: int = 5) -> list[dict]:
        """搜索案例"""
        return self.search(query, doc_type="case", tags=tags, top_k=top_k)

    # ─── 统计 ────────────────────────────────────────────

    def stats(self) -> dict:
        """返回各 collection 的统计信息"""
        stats = {}
        for name, col in self.collections.items():
            stats[name] = {
                "count": col.count(),
            }
        return stats
