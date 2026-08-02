"""去重服务。

三层去重：
1. URL 规范化去重（canonicalize_url）
2. content hash 精确去重（sha256）
3. SimHash 近似去重（用于同义改写/小幅修改的重复页）
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from simhash import Simhash

from apps.backend.web.url_guard import canonicalize_url

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def content_hash(text: str) -> str:
    """计算文本 sha256。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_simhash(text: str, f: int = 64) -> int:
    """基于词元计算 SimHash 指纹。"""
    features = _TOKEN_RE.findall(text.lower())
    if not features:
        return 0
    return Simhash(features, f=f).value


def hamming_distance(a: int, b: int) -> int:
    """两个指纹的汉明距离。"""
    return (a ^ b).bit_count()


@dataclass
class DedupResult:
    """去重判定结果。"""
    is_duplicate: bool
    reason: str
    by: str  # "url" | "hash" | "simhash" | ""


class DedupStore:
    """进程内去重集合。生产期可替换为 Redis 实现。

    注意：进程重启会丢失，仅用于单次会话/单进程内的近似去重；
    持久化去重应结合 DB 中的 content_hash 字段。
    """

    def __init__(self, simhash_threshold: int = 3):
        self._urls: set[str] = set()
        self._hashes: set[str] = set()
        self._simhashes: list[int] = []
        self.simhash_threshold = simhash_threshold

    def check_and_add(self, *, url: str = "", text: str = "") -> DedupResult:
        """检查是否重复；若非重复则登记。返回判定结果。"""
        if url:
            canon = canonicalize_url(url)
            if canon in self._urls:
                return DedupResult(is_duplicate=True, reason="URL 已存在", by="url")
            self._urls.add(canon)

        h = content_hash(text) if text else None
        if h:
            if h in self._hashes:
                return DedupResult(is_duplicate=True, reason="内容哈希重复", by="hash")
            self._hashes.add(h)

        if text:
            sh = compute_simhash(text)
            for existing in self._simhashes:
                if hamming_distance(sh, existing) <= self.simhash_threshold:
                    return DedupResult(is_duplicate=True, reason="SimHash 近似重复", by="simhash")
            self._simhashes.append(sh)

        return DedupResult(is_duplicate=False, reason="", by="")
