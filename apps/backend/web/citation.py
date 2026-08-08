"""引用构建 —— 统一 Citation 格式（Phase 3.6）。

引用是「回答 → 来源」的绑定，既用于注入 LLM 上下文（document_id/title/snippet），
也用于回答落库（url / source_domain / quote / fetched_at 等）。

格式字段兼容 Phase 0/1 的 RefSchema，并扩展 web 来源所需字段。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


def citation_id_for(url: str) -> str:
    """由 URL 生成稳定的引用 id（同 URL 同 id，便于去重与关联）。"""
    return "cit_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def build_citation(
    *,
    citation_id: str,
    ref_type: str,
    title: str,
    url: str = "",
    source_domain: str = "",
    snippet: str = "",
    quote: str = "",
    score: float = 0.0,
    document_id: Any = None,
    document_version_id: int | None = None,
    fetched_at: Any = None,
    language: str = "unknown",
) -> dict[str, Any]:
    """构造一条 Citation 字典（同时适配 LLM 上下文与落库）。

    ref_type: "web" | "document" | "knowledge"
    """
    return {
        "citation_id": citation_id,
        "ref_type": ref_type,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "title": title,
        "url": url,
        "source_domain": source_domain or domain_of(url),
        "snippet": snippet,
        "quote": quote,
        "score": round(float(score), 4),
        "fetched_at": fetched_at.isoformat() if isinstance(fetched_at, datetime) else fetched_at,
        "language": language,
    }
