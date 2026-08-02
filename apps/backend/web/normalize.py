"""正文规范化与质量门禁。

复用 web.cleaner 做 HTML→Markdown 抽取，并补充：
- 语言识别（基于 CJK 字符比例启发式）
- 软 404 检测（基于标题/正文关键词）
- 质量评分（正文长度 + 正文占比综合）
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from apps.backend.web.cleaner import clean_html

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SOFT_404_RE = re.compile(
    r"(?i)(404|not\s*found|page\s*not\s*found|页面不存在|找不到页面|"
    r"access\s*denied|禁止访问|该页面已删除|内容不存在)"
)


@dataclass
class NormalizedPage:
    """规范化后的页面。"""
    title: str
    markdown: str
    text: str
    content_length: int
    html_length: int
    content_ratio: float
    language: str          # "zh" | "en" | "mixed" | "unknown"
    is_soft_404: bool
    quality_score: float  # 0.0 ~ 1.0
    links: list[dict]

    def is_quality_pass(self, min_score: float = 0.3, min_length: int = 200) -> bool:
        """是否通过质量门禁（用于是否入库/整理）。"""
        return (
            not self.is_soft_404
            and self.quality_score >= min_score
            and self.content_length >= min_length
        )


def _detect_language(text: str) -> str:
    if not text:
        return "unknown"
    cjk = len(_CJK_RE.findall(text))
    ratio = cjk / max(len(text), 1)
    if ratio > 0.5:
        return "zh"
    if ratio > 0.2:
        return "mixed"
    return "en"


def _detect_soft_404(title: str, text: str) -> bool:
    return bool(_SOFT_404_RE.search(f"{title}\n{text[:500]}"))


def normalize_html(html: str, base_url: str = "") -> NormalizedPage:
    """将原始 HTML 规范化为结构化正文。"""
    cleaned = clean_html(html, base_url)
    language = _detect_language(cleaned.text)
    soft_404 = _detect_soft_404(cleaned.title, cleaned.text)
    # 质量评分：正文长度（饱和于 1500 字占 0.6）+ 正文占比（饱和于 15% 占 0.4）
    length_score = min(cleaned.content_length / 1500.0, 1.0)
    ratio_score = min(cleaned.content_ratio / 0.15, 1.0)
    quality = round(0.6 * length_score + 0.4 * ratio_score, 3)
    return NormalizedPage(
        title=cleaned.title,
        markdown=cleaned.markdown,
        text=cleaned.text,
        content_length=cleaned.content_length,
        html_length=cleaned.html_length,
        content_ratio=cleaned.content_ratio,
        language=language,
        is_soft_404=soft_404,
        quality_score=quality,
        links=cleaned.links,
    )
