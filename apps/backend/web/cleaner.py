"""HTML 正文清洗工具。

使用 BeautifulSoup 从 HTML 中抽取正文内容，转换为 Markdown 格式。
去除导航、页脚、脚本、样式等非正文元素，保留标题、列表、表格、代码块。

输出同时包含:
  - title: 页面标题
  - markdown: 正文 Markdown
  - text: 纯文本（用于质量评分）
  - content_length: 正文字符数
  - html_length: 原始 HTML 字符数
  - content_ratio: 正文占比（content_length / html_length）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

# 需要移除的标签（非正文内容）
_REMOVE_TAGS = [
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "nav", "footer", "header", "aside", "form", "button",
]

# 需要移除的 class/id 关键词（常见的非正文容器）
_NOISE_PATTERNS = [
    re.compile(r"(?i)(nav|menu|sidebar|footer|header|banner|advert|"
               r"cookie|subscribe|newsletter|social|share|comment|"
               r"related|recommend|popup|modal|breadcrumb|pagination)"),
]

# 正文容器的优先查找顺序（常见 CMS / 博客框架）
_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".content",
    "#content",
    ".post-body",
    ".article-body",
]


@dataclass
class CleanedPage:
    """清洗后的页面内容。"""
    title: str
    markdown: str
    text: str
    content_length: int
    html_length: int
    content_ratio: float
    links: list[dict]  # [{"text": "...", "href": "..."}]


def clean_html(html: str, base_url: str = "") -> CleanedPage:
    """清洗 HTML，提取正文。

    Args:
        html: 原始 HTML 字符串
        base_url: 用于解析相对链接的基础 URL

    Returns:
        CleanedPage 对象
    """
    html_length = len(html)
    if html_length == 0:
        return CleanedPage(
            title="", markdown="", text="",
            content_length=0, html_length=0, content_ratio=0.0,
            links=[],
        )

    soup = BeautifulSoup(html, "lxml")

    # 提取标题
    title = _extract_title(soup)

    # 移除噪声标签
    _remove_noise(soup)

    # 定位正文容器
    content_soup = _find_content(soup)

    # 提取链接（在转换为 markdown 之前）
    links = _extract_links(content_soup, base_url)

    # 转换为 Markdown
    markdown = _to_markdown(content_soup)

    # 提取纯文本
    text = content_soup.get_text(separator=" ", strip=True)

    content_length = len(text)
    content_ratio = content_length / html_length if html_length > 0 else 0.0

    return CleanedPage(
        title=title,
        markdown=markdown,
        text=text,
        content_length=content_length,
        html_length=html_length,
        content_ratio=content_ratio,
        links=links,
    )


def _extract_title(soup: BeautifulSoup) -> str:
    """提取页面标题。"""
    # 优先 <title> 标签
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()

    # 其次 <h1>
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    # 最后 og:title meta
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    return ""


def _remove_noise(soup: BeautifulSoup) -> None:
    """移除噪声标签和噪声容器。"""
    # 移除指定标签
    for tag_name in _REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 移除 class/id 匹配噪声模式的元素
    for element in soup.find_all(True):
        # 防御：decompose 过程中可能残留非 Tag 节点（如 None），避免 .get 崩溃
        if not isinstance(element, Tag):
            continue
        class_list = element.get("class", [])
        if isinstance(class_list, str):
            class_list = class_list.split()
        element_id = element.get("id", "")

        class_str = " ".join(class_list)
        combined = f"{class_str} {element_id}"

        for pattern in _NOISE_PATTERNS:
            if pattern.search(combined):
                element.decompose()
                break

    # 移除 HTML 注释
    from bs4 import Comment
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()


def _find_content(soup: BeautifulSoup) -> BeautifulSoup:
    """定位正文容器，优先使用常见选择器。"""
    for selector in _CONTENT_SELECTORS:
        element = soup.select_one(selector)
        if element and len(element.get_text(strip=True)) > 200:
            return element
    # 回退到整个 body
    body = soup.find("body")
    return body if body else soup


def _extract_links(soup: Tag | BeautifulSoup, base_url: str) -> list[dict]:
    """提取正文中的链接。"""
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if base_url:
            href = urljoin(base_url, href)
        text = a_tag.get_text(strip=True)
        if text and href:
            links.append({"text": text[:200], "href": href})
    return links[:100]  # 限制数量


def _to_markdown(soup: Tag | BeautifulSoup) -> str:
    """将 BeautifulSoup 元素转换为 Markdown。"""
    lines: list[str] = []
    _walk_node(soup, lines)
    # 清理多余空行
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _walk_node(node: Tag | NavigableString, lines: list[str]) -> None:
    """递归遍历 DOM 节点，生成 Markdown 行。"""
    if isinstance(node, NavigableString):
        text = str(node).strip()
        if text:
            lines.append(text)
        return

    if not isinstance(node, Tag):
        return

    tag_name = node.name.lower()

    # 标题
    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag_name[1])
        text = node.get_text(strip=True)
        if text:
            lines.append(f"\n{'#' * level} {text}\n")
        return

    # 段落
    if tag_name == "p":
        text = node.get_text(strip=True)
        if text:
            lines.append(f"\n{text}\n")
        return

    # 列表
    if tag_name in ("ul", "ol"):
        lines.append("")
        for i, li in enumerate(node.find_all("li", recursive=False), 1):
            text = li.get_text(strip=True)
            if text:
                prefix = f"{i}. " if tag_name == "ol" else "- "
                lines.append(f"{prefix}{text}")
        lines.append("")
        return

    # 代码块
    if tag_name == "pre":
        code = node.get_text()
        lines.append(f"\n```\n{code.strip()}\n```\n")
        return

    if tag_name == "code":
        text = node.get_text()
        if text:
            lines.append(f"`{text}`")
        return

    # 引用
    if tag_name == "blockquote":
        text = node.get_text(strip=True)
        if text:
            for line in text.split("\n"):
                lines.append(f"> {line}")
            lines.append("")
        return

    # 表格
    if tag_name == "table":
        _table_to_markdown(node, lines)
        return

    # 图片
    if tag_name == "img":
        alt = node.get("alt", "")
        src = node.get("src", "")
        if src:
            lines.append(f"![{alt}]({src})")
        return

    # 链接
    if tag_name == "a":
        text = node.get_text(strip=True)
        href = node.get("href", "")
        if text and href:
            lines.append(f"[{text}]({href})")
        return

    # 换行
    if tag_name == "br":
        lines.append("")
        return

    # hr
    if tag_name == "hr":
        lines.append("\n---\n")
        return

    # 其他容器：递归处理子节点
    for child in node.children:
        _walk_node(child, lines)


def _table_to_markdown(table: Tag, lines: list[str]) -> None:
    """将 HTML 表格转换为 Markdown 表格。"""
    rows = table.find_all("tr")
    if not rows:
        return

    lines.append("")
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        cell_texts = [c.get_text(strip=True) for c in cells]
        if cell_texts:
            lines.append("| " + " | ".join(cell_texts) + " |")
            # 在第一行（表头）后添加分隔行
            if i == 0:
                lines.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")
    lines.append("")
