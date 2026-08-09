"""对话联网检索编排（Phase 3 快车道 / 3.2 + 3.3）。

把 Phase 2 的零件串成一条链路（在同步预算内完成，用于对话回答）：

    WebSearch → Fetch(Top N) → Normalize → Dedup → Organize → Citation
        │
        ├─ 同步阶段：返回 citations 注入 LLM 上下文 + 记录 WebSearchRun / ChatTurnSource
        └─ 异步阶段（BackgroundTasks）：把「合成回答 + 引用链接」沉淀到个人知识库
           （ingest_web_synthesis，不再存原始网页全文）

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
from apps.backend.services.personal_knowledge import PersonalKnowledgeService, SaveWebSynthesisInput
from apps.backend.web.citation import build_citation, domain_of
from apps.backend.web.dedup import DedupStore, content_hash
from apps.backend.web.fetch_http import get_fetch_adapter
from apps.backend.web.normalize import normalize_html
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
                # 按相关度排序，取前 max_results 条全部进入引用（满足「整合 N 条结果」需求）；
                # 其中仅前 max_fetch_pages 条抓正文，其余用搜索摘要兜底，控制抓取延迟
                top = sorted(results, key=lambda r: r.score, reverse=True)[:max_results]
                adapter = get_fetch_adapter()
                dedup = DedupStore()

                for rank, r in enumerate(top, start=1):
                    fetched_at = datetime.utcnow()
                    # 单条抓取/解析失败不应拖垮整次检索
                    page = None
                    cid = _cid(r.url)
                    src_url = r.url
                    src_title = r.title or r.url
                    src_domain = domain_of(r.url)

                    # 仅对前 max_fetch_pages 条抓正文，其余直接走搜索摘要兜底（控制延迟）
                    if rank <= max_fetch_pages:
                        try:
                            res = await adapter.fetch(r.url)
                            if not res.error:
                                try:
                                    html = res.content.decode("utf-8", errors="replace")
                                except Exception:
                                    html = ""
                                if html:
                                    np = normalize_html(html, base_url=res.final_url)
                                    if np.is_quality_pass():
                                        final_url = res.final_url or r.url
                                        dup = dedup.check_and_add(url=final_url, text=np.text)
                                        if not dup.is_duplicate:
                                            page = FetchedPage(
                                                citation_id=_cid(final_url),
                                                title=np.title or r.title,
                                                url=r.url,
                                                final_url=final_url,
                                                source_domain=domain_of(final_url),
                                                markdown=np.markdown,
                                                text=np.text,
                                                content_hash=content_hash(np.text),
                                                language=np.language,
                                                quality_score=np.quality_score,
                                                snippet=np.text[:2000],
                                                fetched_at=fetched_at,
                                            )
                                            outcome.pages.append(page)
                        except Exception:  # noqa: BLE001 - 单条失败不影响其余
                            page = None

                    if page is not None:
                        # 完整正文路径：用抓取并清洗后的内容
                        cid = page.citation_id
                        src_url = page.final_url
                        src_title = page.title
                        src_domain = page.source_domain
                        outcome.citations.append(
                            build_citation(
                                citation_id=page.citation_id,
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
                    else:
                        # 兜底引用：抓取失败 / 质量不过 / 反爬拦截时，
                        # 仍用搜索结果（Tavily 的 title/url/snippet）生成来源引用，
                        # 保证只要检索有结果，前端就能展示可点击的来源链接。
                        outcome.citations.append(
                            build_citation(
                                citation_id=cid,
                                ref_type="web",
                                title=src_title,
                                url=src_url,
                                source_domain=src_domain,
                                snippet=r.snippet or "",
                                score=r.score,
                                document_id=f"web:{rank}",
                                fetched_at=fetched_at,
                                language="unknown",
                            )
                        )

                    # 无论走哪条路径都落库 ChatTurnSource，保证来源可追溯
                    db.add(
                        models.ChatTurnSource(
                            user_id=user.id,
                            session_id=session_id,
                            message_id=message_id,
                            web_search_run_id=run.id,
                            citation_id=cid,
                            ref_type="web",
                            url=src_url,
                            title=src_title,
                            source_domain=src_domain,
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


async def ingest_web_synthesis(
    *,
    user: "models.User",
    session_id: int,
    message_id: int,
    run_id: int | None,
    answer: str,
    citations: list[dict],
    query: str,
    knowledge_mode: str = "auto",
) -> dict[str, int]:
    """把「联网合成回答 + 引用链接」沉淀到个人知识库（BackgroundTasks 中调用）。

    折中方案：不存原始网页全文，只存 LLM 整合后的回答 + 每条引用的
    标题/链接/摘要片段，既减少存储又保留一手可追溯性。

    knowledge_mode:
      - off / ask：不自动沉淀（ask 由前端后续触发保存）
      - auto / always：沉淀合成结果
    """
    if knowledge_mode in ("off", "ask"):
        return {"saved": 0, "skipped": len(citations)}
    if not answer or not citations:
        return {"saved": 0, "skipped": 0}

    svc = PersonalKnowledgeService()
    try:
        doc = svc.save_web_synthesis(
            SaveWebSynthesisInput(
                user_id=user.id,
                query=query,
                answer=answer,
                citations=citations,
                idempotency_key=str(message_id),
            )
        )
        if doc is not None:
            # 把 ChatTurnSource 关联到保存出的文档版本
            with Session(engine) as db:
                db.execute(
                    update(models.ChatTurnSource)
                    .where(models.ChatTurnSource.message_id == message_id)
                    .values(document_version_id=doc.current_version_id)
                )
                db.commit()
            return {"saved": 1, "skipped": 0}
    except Exception:  # noqa: BLE001 - 单条失败不阻塞回答链路
        pass
    return {"saved": 0, "skipped": len(citations)}
