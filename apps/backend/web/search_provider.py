"""Web 搜索 Provider 抽象与实现。

定义 WebSearchProvider Protocol，并提供了 Tavily（默认）与 Serper 两种实现，
API key 来自 settings。后续可无缝接入更多 provider。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import httpx

from apps.backend.config import settings


@dataclass
class SearchResult:
    """单条搜索结果。"""
    title: str
    url: str
    snippet: str = ""
    score: float = 0.0
    raw: dict = field(default_factory=dict)


@runtime_checkable
class WebSearchProvider(Protocol):
    """搜索 Provider 接口。"""

    provider_name: str

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        search_depth: str = "basic",
    ) -> list[SearchResult]:
        """执行搜索，返回结果列表。"""
        ...


class TavilySearchProvider:
    """Tavily 搜索实现（默认）。"""

    provider_name = "tavily"
    _ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        search_depth: str = "basic",
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("Tavily API key 未配置（环境变量 WEB_SEARCH_API_KEY）")
        max_results = max_results or settings.web_search_max_results
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self._ENDPOINT, json=payload)
            resp.raise_for_status()
            data = resp.json()
        out: list[SearchResult] = []
        for item in data.get("results", []):
            out.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                score=float(item.get("score", 0.0)),
                raw=item,
            ))
        return out


class SerperSearchProvider:
    """Serper.dev (Google) 搜索实现，结构就绪，可由 settings 切换。"""

    provider_name = "serper"
    _ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        search_depth: str = "basic",
    ) -> list[SearchResult]:
        if not self._api_key:
            raise RuntimeError("Serper API key 未配置（环境变量 WEB_SEARCH_API_KEY）")
        max_results = max_results or settings.web_search_max_results
        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": max_results}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self._ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        out: list[SearchResult] = []
        for item in data.get("organic", []):
            out.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                raw=item,
            ))
        return out


_PROVIDERS: dict[str, type] = {
    "tavily": TavilySearchProvider,
    "serper": SerperSearchProvider,
}


def get_search_provider() -> WebSearchProvider:
    """按 settings.web_search_provider 构造 provider 实例（默认 tavily）。"""
    name = (settings.web_search_provider or "tavily").lower()
    cls = _PROVIDERS.get(name, TavilySearchProvider)
    return cls(api_key=settings.web_search_api_key)  # type: ignore[return-value]
