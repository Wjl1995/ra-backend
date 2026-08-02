"""对话联网检索编排（Phase 3 快车道 / 3.2 + 3.3）。

把 Phase 2 的零件串成一条链路（在同步预算内完成，用于对话回答）：

    WebSearch → Fetch(Top N) → Normalize → Dedup → Organize → Citation
        │
        ├─ 同步阶段：返回 citations 注入 LLM 上下文 + 记录 WebSearchRun / ChatTurnSource
        └─ 异步阶段（BackgroundTasks）：把引用网页沉淀到个人知识库（save_web_page）

设计要点：
- 联网判断（WebNeedDetector）在 chat_service 中做，本模块只负责「已经决定联网」后的执行。
- 搜索/抓取全部异步（httpx），用 asyncio.wait_for 卡住同步预算，超时返回已拿到的部分结果。
- DB 写入使用独立 Session(engine)，不占用请求主 Session，避免跨 await 复用连接的坑。
- 没有配置搜索 API key 时优雅降级：记录 WebSearchRun(skipped)，返回空 citations，不影响原链路。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from apps.backend import models
from apps.backend.config import settings
from apps.backend.database import engine
from apps.backend.services.personal_knowledge import PersonalKnowledgeService, SaveWebPageInput
from apps.backend.web.citation import build_citation, domain_of
from apps.backend.web.dedup import DedupStore, content_hash
from apps.backend.web.fetch_http import get_fetch_adapter
from apps.backend.web.normalize import normalize_html
from apps.backend.web.organizer import KnowledgeOrganizer
from apps.backend.web.search_provider import get_search_provider


@dataclass
class FetchedPage:
    """一次抓取后用于异步沉淀的网页（含完整正文）。"""

    citation_id: str
    title: str
    url: str
    final_url: str
    source_domain: str
    markdown: str
    text: str
    content_hash: str
    language: str
    quality_score: float
    snippet: str
    fetched_at: datetime


@dataclass
class WebSearchOutcome:
    run_id: int | None
    provider: str
    status: str  # completed | failed | skipped
    citations: list[dict[str, Any]] = field(default_factory=list)  # 注入 LLM + 落库
    pages: list[FetchedPage] = field(default_factory=list)  # 异步沉淀
    error: str = ""


async def run_web_search(
    *,
    user: "models.User",
    session_id: int,
    message_id: int,
    query: str,
    max_results: int | None = None,
    max_fetch_pages: int | None = None,
    budget_seconds: float | None = None,
) -> WebSearchOutcome:
    """执行一次对话联网搜索（同步预算内完成）。"""
    max_results = max_results or settings.web_search_max_results
    max_fetch_pages = max_fetch_pages or settings.web_max_fetch_pages
    budget_seconds = budget_seconds or settings.web_sync_budget_seconds
    provider = get_search_provider()

    outcome = WebSearchOutcome(run_id=None, provider=provider.provider_name, status="pending")

    # 优雅降级：未配置搜索 key
    if not settings.web_search_api_key:
        with Session(engine) as db:
            run = models.WebSearchRun(
                user_id=user.id,
                session_id=session_id,
                message_id=message_id,
                query=query,
                provider=provider.provider_name,
                status="skipped",
                error_code="no_api_key",
            )
            db.add(run)
            db.commit()
            outcome.run_id = run.id
        outcome.status = "skipped"
        outcome.error = "未配置搜索 API key（WEB_SEARCH_API_KEY）"
        return outcome

    with Session(engine) as db:
        run = models.WebSearchRun(
            user_id=user.id,
            session_id=session_id,
            message_id=message_id,
            query=query,
            provider=provider.provider_name,
            status="pending",
        )
        db.add(run)
        db.flush()
        outcome.run_id = run.id

        try:

            async def _do() -> None:
                results = await provider.search(query, max_results=max_results)
                run.results_json = json.dumps(
                    [
                        {"title": r.title, "url": r.url, "snippet": r.snippet, "score": r.score}
                        for r in results
                    ],
                    ensure_ascii=False,
                )
                # 按相关度取前 N 抓正文
                top = sorted(results, key=lambda r: r.score, reverse=True)[:max_fetch_pages]
                adapter = get_fetch_adapter()
                dedup = DedupStore()

                for rank, r in enumerate(top, start=1):
                    res = await adapter.fetch(r.url)
                    if res.error:
                        continue
                    try:
                        html = res.content.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    np = normalize_html(html, base_url=res.final_url)
                    if not np.is_quality_pass():
                        continue
                    dup = dedup.check_and_add(url=res.final_url, text=np.text)
                    if dup.is_duplicate:
                        continue

                    cid = _cid(res.final_url)
                    fetched_at = datetime.utcnow()
                    page = FetchedPage(
                        citation_id=cid,
                        title=np.title or r.title,
                        url=r.url,
                        final_url=res.final_url,
                        source_domain=domain_of(res.final_url),
                        markdown=np.markdown,
                        text=np.text,
                        content_hash=content_hash(np.text),
                        language=np.language,
                        quality_score=np.quality_score,
                        snippet=np.text[:2000],
                        fetched_at=fetched_at,
                    )
                    outcome.pages.append(page)

                    outcome.citations.append(
                        build_citation(
                            citation_id=cid,
                            ref_type="web",
                            title=page.title,
                            url=page.final_url,
                            source_domain=page.source_domain,
                            snippet=page.snippet,
                            score=r.score,
                            document_id=f"web:{rank}",
                            fetched_at=fetched_at,
                            language=page.language,
                        )
                    )
                    db.add(
                        models.ChatTurnSource(
                            user_id=user.id,
                            session_id=session_id,
                            message_id=message_id,
                            web_search_run_id=run.id,
                            citation_id=cid,
                            ref_type="web",
                            url=page.final_url,
                            title=page.title,
                            source_domain=page.source_domain,
                            fetched_at=fetched_at,
                        )
                    )
                db.flush()

            try:
                await asyncio.wait_for(_do(), timeout=budget_seconds)
            except asyncio.TimeoutError:
                outcome.error = "预算超时，已返回部分结果"

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            db.commit()
            outcome.status = "completed"
            return outcome

        except Exception as exc:  # noqa: BLE001 - 联网失败不应拖垮回答
            db.rollback()
            run.status = "failed"
            run.error_code = type(exc).__name__
            try:
                db.commit()
            except Exception:
                db.rollback()
            outcome.status = "failed"
            outcome.error = str(exc)
            return outcome


def _cid(url: str) -> str:
    from apps.backend.web.citation import citation_id_for

    return citation_id_for(url)


def ingest_web_pages(
    *,
    user: "models.User",
    session_id: int,
    message_id: int,
    run_id: int | None,
    pages: list[FetchedPage],
    knowledge_mode: str = "auto",
) -> dict[str, int]:
    """把引用网页沉淀到个人知识库（在 BackgroundTasks 中调用，同步函数）。

    知识沉淀始终异步，不影响回答延迟。knowledge_mode:
      - off / ask：不自动沉淀（ask 由前端后续触发保存）
      - auto / always：沉淀实际抓到的质量合格网页
    """
    if knowledge_mode in ("off", "ask"):
        return {"saved": 0, "skipped": len(pages)}
    if not pages:
        return {"saved": 0, "skipped": 0}

    svc = PersonalKnowledgeService()
    organizer = KnowledgeOrganizer()
    saved = 0
    for page in pages:
        try:
            # 异步阶段才调用 LLM 整理，避免占用对话同步预算
            card = asyncio.run(organizer.organize(page.markdown, source_url=page.final_url))
            doc = svc.save_web_page(
                SaveWebPageInput(
                    user_id=user.id,
                    source_url=page.final_url,
                    title=page.title,
                    markdown=page.markdown,
                    text=page.text,
                    content_hash=page.content_hash,
                    language=page.language,
                    quality_score=page.quality_score,
                    card=card,
                )
            )
            # 把 ChatTurnSource 关联到保存出的文档版本
            with Session(engine) as db:
                db.execute(
                    update(models.ChatTurnSource)
                    .where(
                        models.ChatTurnSource.message_id == message_id,
                        models.ChatTurnSource.citation_id == page.citation_id,
                    )
                    .values(document_version_id=doc.current_version_id)
                )
                db.commit()
            saved += 1
        except Exception:  # noqa: BLE001 - 单条失败不阻塞其余
            continue
    return {"saved": saved, "skipped": len(pages) - saved}
