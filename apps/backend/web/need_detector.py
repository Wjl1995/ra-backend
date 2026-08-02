"""WebNeedDetector —— 判断对话是否需要联网搜索。

纯规则，不依赖 LLM，用于对话链路在预算内快速决策：
1. 用户显式要求联网（"联网/搜索/查一下最新"等）
2. 强时效性关键词（"最新/今天/股价/天气/新闻"等，单独命中即判定需要）
3. 时效性关键词 + 本地召回置信度低（组合信号）
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 显式联网意图
_EXPLICIT_RE = re.compile(r"(联网|上网|搜索|搜一下|搜一搜|查一下最新|查最新|帮我搜|在线查|实时|网上找|上网查)")
# 一般时效性关键词
_FRESHNESS_RE = re.compile(
    r"(最新|今天|今日|昨天|本周|本月|202[0-9]年?|新闻|股价|价格|汇率|天气|发布会|财报|实时|刚发布|最近|进展|动态)"
)
# 强时效信号（单独命中即判定需要联网）
_STRONG_FRESH_RE = re.compile(
    r"(最新|今天|今日|实时|刚发布|202[0-9]年?财报|股价|汇率|天气|新闻|发布会)"
)


@dataclass
class NeedDecision:
    """联网决策结果。"""
    need_web: bool
    reason: str
    signals: list[str]


class WebNeedDetector:
    """联网需求检测器。"""

    def __init__(self, *, local_confidence_floor: float = 0.35):
        # 本地召回置信度低于此值且命中时效性关键词时才判定需要联网
        self.local_confidence_floor = local_confidence_floor

    def decide(
        self,
        query: str,
        *,
        local_confidence: float | None = None,
        explicit_override: bool | None = None,
    ) -> NeedDecision:
        """判断是否需要联网。

        Args:
            query: 用户问题
            local_confidence: 本地知识库召回的置信度（0~1），None 表示未做本地检索
            explicit_override: 显式强制覆盖（True=强制联网, False=强制不联网）
        """
        signals: list[str] = []

        if explicit_override is False:
            return NeedDecision(need_web=False, reason="显式关闭联网", signals=signals)
        if explicit_override is True or _EXPLICIT_RE.search(query):
            signals.append("explicit_web_request")
            return NeedDecision(need_web=True, reason="用户显式要求联网", signals=signals)

        if _STRONG_FRESH_RE.search(query):
            signals.append("strong_freshness")
            return NeedDecision(need_web=True, reason="命中强时效性关键词", signals=signals)

        if _FRESHNESS_RE.search(query):
            signals.append("freshness_keyword")
        if local_confidence is not None and local_confidence < self.local_confidence_floor:
            signals.append("low_local_confidence")

        if "freshness_keyword" in signals and "low_local_confidence" in signals:
            return NeedDecision(
                need_web=True,
                reason="时效性关键词且本地召回置信度不足",
                signals=signals,
            )
        return NeedDecision(
            need_web=False,
            reason="无需联网" if not signals else "信号不足（仅有弱时效性或置信度尚可）",
            signals=signals,
        )
