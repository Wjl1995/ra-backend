from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User, WebSearchRun

router = APIRouter(prefix="/web-search", tags=["web-search"])


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc or ""
    except Exception:
        return ""


def _parse_results(results_json: str) -> list[dict]:
    try:
        raw = json.loads(results_json) if isinstance(results_json, str) else results_json
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        out.append(
            {
                "title": item.get("title") or "",
                "url": url,
                "source_domain": item.get("source_domain") or _domain_of(url),
                "score": item.get("score"),
            }
        )
    return out


@router.get("/runs")
def list_web_search_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户发起过的对话联网检索记录，含检索结果与标题。

    用于前端「联网检索」入口浏览已入库的搜索结果（只看标题即可）。
    """
    runs = (
        db.query(WebSearchRun)
        .filter(WebSearchRun.user_id == current_user.id)
        .order_by(WebSearchRun.created_at.desc())
        .all()
    )
    return [
        {
            "id": run.id,
            "query": run.query,
            "provider": run.provider,
            "status": run.status,
            "created_at": run.created_at,
            "results": _parse_results(run.results_json),
        }
        for run in runs
    ]
