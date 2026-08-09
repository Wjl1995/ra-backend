"""联网检索结果 → 结构化、引用原文的整合回答（Phase 3.x 新增）。

把 run_web_search 返回的若干条联网结果（标题 / 链接 / 正文或摘要）与用户 query
一起交给 LLM，要求：

    1. 理解用户真正想问什么（意图、隐含需求）；
    2. 综合多条结果，输出一条「有结构、条理清晰」的回答，而非逐条罗列原始结果；
    3. 在文中以 [n] 标注对应来源（n 与传入结果序号一致），原始结果不再原样抛给用户；
    4. 只基于所给结果作答，不足时明确说明局限。

来源链接通过 chat_service 把对应的 N 条 citation 作为 refs 回传前端展示。
"""
from __future__ import annotations

from typing import Any

from openai import OpenAI

WEB_SYNTHESIS_SYSTEM_PROMPT = """你是专业的联网检索问答助手。用户会给你一个问题，以及若干条联网检索到的结果（每条含序号、标题、来源链接、内容摘要/正文）。

请严格按以下要求回答：
1. 先真正理解用户想问的是什么（意图、隐含需求），不要只做关键词匹配。
2. 综合多条检索结果，给出一条「有结构、条理清晰」的回答：可先给一句话结论，再用要点或分段展开；严禁逐条罗列原始结果。
3. 在回答中自然引用对应来源，使用 [n] 标记（n 为结果序号，如 [1]、[2]），序号必须与下方检索结果序号一致。
4. 只基于所给结果作答，不得编造；若结果不足以回答，明确说明已知信息的局限。
5. 默认用中文，语言简洁、专业、可读。

只输出最终回答本身，不要加「根据检索结果」之类前缀套话，也不要输出额外的解释说明。"""


def build_web_synthesis_user_prompt(
    query: str,
    items: list[dict[str, Any]],
    *,
    local_context: str | None = None,
) -> str:
    """构造合成请求的用户消息：query + 编号的检索结果（每条含链接与内容）。"""
    lines: list[str] = [f"用户问题：{query}", "", "检索到的联网结果："]
    for i, it in enumerate(items, start=1):
        title = (it.get("title") or "").strip() or "(无标题)"
        url = (it.get("url") or "").strip()
        text = (it.get("text") or it.get("snippet") or "").strip()
        if len(text) > 1500:
            text = text[:1500] + "…"
        lines.append(f"[{i}] 标题：{title}")
        if url:
            lines.append(f"    链接：{url}")
        lines.append(f"    内容：{text}")
        lines.append("")
    if local_context:
        lines.append("另外，用户自有文档中检索到的相关片段（供参考、可结合使用）：")
        lines.append(local_context)
        lines.append("")
    lines.append("请基于以上结果，给出整合后的结构化回答，并在文中用 [n] 标注来源。")
    return "\n".join(lines)


def synthesize_web_answer(
    *,
    llm_client: OpenAI,
    model: str,
    query: str,
    items: list[dict[str, Any]],
    local_context: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """把用户 query + 多条联网结果整合成一条带引用 [n] 的结构化回答。

    同步函数（底层用同步 OpenAI 客户端），调用方应通过 run_in_threadpool 包裹，
    避免阻塞事件循环。items 的顺序即 [1]..[n] 的引用序号。
    合成失败返回空串，调用方据此回退到原链路。
    """
    if not items:
        return ""
    user_prompt = build_web_synthesis_user_prompt(query, items, local_context=local_context)
    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": WEB_SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = resp.choices[0].message
        content = getattr(message, "content", "") or ""
        return content.strip()
    except Exception:  # noqa: BLE001 - 合成失败不应阻断回答，交由调用方回退
        return ""
