"""robots.txt 检查。

轻量 robots.txt 解析器（支持 Allow/Disallow + * 通配 + 结尾 $），
带进程内缓存。不依赖第三方库。

策略（MVP）：robots.txt 获取或解析失败时默认「允许」（fail-open），
以保证抓取可用性；Phase 7 安全加固时可改为 fail-closed。
"""
from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from apps.backend.config import settings

_RULE = tuple[str, str]  # (allow|deny, pattern)


@dataclass
class _CachedRobots:
    rules: dict[str, list[_RULE]]
    fetched_at: float


class RobotsChecker:
    """robots.txt 合规检查器（带缓存）。"""

    def __init__(self, *, cache_ttl: int | None = None, user_agent: str | None = None):
        self._cache: dict[str, _CachedRobots] = {}
        self._cache_ttl = (
            cache_ttl if cache_ttl is not None else settings.robots_cache_ttl_seconds
        )
        ua = (user_agent or settings.crawl_user_agent).split("/", 1)[0].strip()
        self._user_agent = ua or "*"

    async def is_allowed(self, url: str) -> bool:
        """判断给定 URL 是否被目标站点的 robots.txt 允许抓取。"""
        parts = urlsplit(url)
        base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        robots_url = base + "/robots.txt"

        cached = self._cache.get(base)
        if cached and (time.time() - cached.fetched_at) < self._cache_ttl:
            rules = cached.rules
        else:
            rules = await self._fetch_and_parse(robots_url)
            self._cache[base] = _CachedRobots(rules=rules, fetched_at=time.time())

        group = self._group_for_agent(rules, self._user_agent)
        path = parts.path or "/"

        # 匹配规则：记录最后命中（根规则 "/" 视为匹配所有路径）
        matched: str | None = None
        for kind, pat in group:
            if pat in ("/", ""):
                matched = kind
            elif fnmatch.fnmatch(path, pat):
                matched = kind
        return matched != "deny"

    async def _fetch_and_parse(self, robots_url: str) -> dict[str, list[_RULE]]:
        rules: dict[str, list[_RULE]] = {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(robots_url)
                if resp.status_code != 200:
                    return rules
                text = resp.text
        except Exception:  # noqa: BLE001 - 获取失败按 fail-open 处理
            return rules

        current_agent = "*"
        rules.setdefault(current_agent, [])
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("user-agent:"):
                current_agent = line.split(":", 1)[1].strip().lower()
                rules.setdefault(current_agent, [])
            elif low.startswith("allow:"):
                pat = line.split(":", 1)[1].strip()
                rules[current_agent].append(("allow", self._to_glob(pat)))
            elif low.startswith("disallow:"):
                pat = line.split(":", 1)[1].strip()
                rules[current_agent].append(("deny", self._to_glob(pat)))
        return rules

    @staticmethod
    def _to_glob(pat: str) -> str:
        # robots 通配 * 与 glob 兼容；结尾 $ 表示精确结尾（glob 不原生支持，去掉）
        if pat.endswith("$"):
            pat = pat[:-1]
        return pat

    @staticmethod
    def _group_for_agent(rules: dict[str, list[_RULE]], agent: str) -> list[_RULE]:
        if agent in rules:
            return rules[agent]
        return rules.get("*", [])
