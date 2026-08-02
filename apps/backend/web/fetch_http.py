"""FetchAdapter L0 —— 基于 httpx 的 HTTP 抓取。

职责：
- 重定向控制（每次跳转都重新做 SSRF 校验，防止重定向绕过）
- 超时控制
- 响应大小限制（防止超大响应撑爆内存）
- content-type 记录（供上层判断是否文本资源）

浏览器渲染（L2，Crawl4AI）属于后续 Phase，本适配器仅做静态 HTTP 抓取。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urljoin

import httpx

from apps.backend.config import settings
from apps.backend.web.url_guard import UrlUnsafeError, validate_url_for_fetch

_REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass
class FetchResult:
    """单次抓取结果。error 非空表示抓取失败。"""
    url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    error: str = ""


@runtime_checkable
class FetchAdapter(Protocol):
    """抓取适配器接口。"""

    async def fetch(self, url: str) -> FetchResult:
        ...


class HttpFetchAdapter:
    """L0 抓取适配器：纯 HTTP 抓取，无 JS 渲染。"""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_content_length: int | None = None,
        user_agent: str | None = None,
        max_redirects: int = 5,
    ):
        self._timeout = timeout or settings.crawl_timeout_seconds
        self._max_content_length = max_content_length or settings.crawl_max_content_length
        self._user_agent = user_agent or settings.crawl_user_agent
        self._max_redirects = max_redirects

    async def fetch(self, url: str) -> FetchResult:
        # 1) SSRF 防护 + 规范化（初始 URL）
        canonical, err = validate_url_for_fetch(url)
        if err:
            return FetchResult(url=url, final_url=url, status_code=0,
                               content_type="", content=b"", error=err)

        headers = {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        target = canonical
        try:
            async with httpx.AsyncClient(timeout=self._timeout,
                                         follow_redirects=False,
                                         headers=headers) as client:
                for _ in range(self._max_redirects + 1):
                    resp = await client.get(target)
                    if resp.status_code in _REDIRECT_CODES:
                        loc = resp.headers.get("location")
                        if not loc:
                            return FetchResult(
                                url=url, final_url=str(resp.url),
                                status_code=resp.status_code,
                                content_type=resp.headers.get("content-type", ""),
                                content=b"", error="重定向缺少 Location 头",
                            )
                        target = urljoin(target, loc)
                        # 2) 重定向目标也要重新 SSRF 校验
                        nxt, nerr = validate_url_for_fetch(target)
                        if nerr:
                            return FetchResult(
                                url=url, final_url=target, status_code=0,
                                content_type="", content=b"",
                                error=f"重定向到不安全地址: {nerr}",
                            )
                        target = nxt
                        continue
                    # 3) 非重定向：读取 body（带大小限制）
                    ctype = resp.headers.get("content-type", "")
                    body = b""
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        body += chunk
                        if len(body) > self._max_content_length:
                            return FetchResult(
                                url=url, final_url=str(resp.url),
                                status_code=resp.status_code, content_type=ctype,
                                content=body,
                                error=f"响应超过大小限制 {self._max_content_length} 字节",
                            )
                    return FetchResult(
                        url=url, final_url=str(resp.url), status_code=resp.status_code,
                        content_type=ctype, content=body,
                    )
                return FetchResult(
                    url=url, final_url=target, status_code=0,
                    content_type="", content=b"", error="超过最大重定向次数",
                )
        except UrlUnsafeError as e:
            return FetchResult(url=url, final_url=url, status_code=0,
                               content_type="", content=b"", error=f"安全拦截: {e}")
        except httpx.HTTPError as e:
            return FetchResult(url=url, final_url=canonical, status_code=0,
                               content_type="", content=b"", error=f"HTTP 错误: {e}")


def get_fetch_adapter() -> FetchAdapter:
    """获取默认 L0 抓取适配器。"""
    return HttpFetchAdapter()
