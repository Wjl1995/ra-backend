
"""
Document Processor —— 文档处理流水线

将原始文档转换为结构化知识片段 (KnowledgeChunk)

支持输入格式：
- Markdown (.md)
- JSON (.json)  —— 预结构化文档
- 纯文本 (.txt)
- Word (.docx)
- PowerPoint (.pptx)
- PDF (.pdf)
- Excel (.xlsx, .xls)

处理流程：
  原始文档 → [解析器] → Markdown → 解析 → 清洗 → 分块 → 标签化 → 输出 KnowledgeChunk 列表
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Optional

from knowledge.store import KnowledgeChunk
from knowledge.parsers import get_parser, get_supported_extensions




# ─── Markdown 解析 ──────────────────────────────────────────

def parse_markdown(
    text: str,
    doc_id: str = "",
    domain: str = "general",
    source: str = "",
) -> list[dict]:
    """
    解析 Markdown 文档为结构化段落

    按标题层级拆分，保留标题路径
    """
    lines = text.split("\n")
    sections = []
    current_heading_path = []
    current_content_lines = []

    def _flush():
        content = "\n".join(current_content_lines).strip()
        if content:
            sections.append({
                "title_path": " > ".join(current_heading_path) if current_heading_path else "",
                "content": content,
            })
        current_content_lines.clear()

    for line in lines:
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            _flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            # 更新标题路径
            current_heading_path = current_heading_path[:level - 1] + [title]
        else:
            current_content_lines.append(line)

    _flush()
    return sections


def parse_json_doc(
    data: dict,
    doc_id: str = "",
) -> list[dict]:
    """
    解析预结构化的 JSON 文档

    期望格式：
    {
      "title": "文档标题",
      "domain": "领域",
      "doc_type": "knowledge/rule/case",
      "sections": [
        {"heading": "章节标题", "content": "内容", "tags": ["标签"]}
      ]
    }
    """
    sections = []
    base_path = data.get("title", "")
    for sec in data.get("sections", []):
        heading = sec.get("heading", "")
        content = sec.get("content", "")
        if not content:
            continue
        title_path = f"{base_path} > {heading}" if base_path and heading else heading or base_path
        sections.append({
            "title_path": title_path,
            "content": content,
            "tags": sec.get("tags", []),
            "domain": data.get("domain", "general"),
            "doc_type": data.get("doc_type", "knowledge"),
        })
    return sections


# ─── 文本分块 ──────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 80,
) -> list[str]:
    """
    将长文本按字数分块（中文场景）

    Args:
        text: 输入文本
        chunk_size: 每块最大字数
        overlap: 重叠字数
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        # 尝试在句号/换行处断开
        if end < len(text):
            for sep in ["\n\n", "\n", "。", "！", "？", "；"]:
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size * 0.5:
                    chunk = chunk[:last_sep + len(sep)]
                    end = start + last_sep + len(sep)
                    break
        chunks.append(chunk.strip())
        start = end - overlap
        if start >= len(text):
            break

    return [c for c in chunks if c]


# ─── 关键词提取（简单版） ────────────────────────────────────

def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """
    简单关键词提取：基于词频 + 停用词过滤

    生产环境建议替换为 LLM 提取或 KeyBERT
    """
    # 中文停用词
    stopwords = set(
        "的 了 是 在 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这 "
        "他 她 它 们 那 里 什么 怎么 可以 因为 所以 如果 但是 而且 或者 以及 对于 关于 通过 "
        "需要 进行 可以 根据 按照 应当 必须 可能 已经".split()
    )

    # 简单分词：按标点和空格切
    words = re.split(r'[\s,，。！？；：、""''（）()\[\]{}<>《》/\\|@#$%^&*+=~`]', text)
    words = [w for w in words if len(w) >= 2 and w not in stopwords]

    # 词频统计
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # 按频率排序取 top
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:max_keywords]]


# ─── 文档处理流水线 ─────────────────────────────────────────

class DocumentProcessor:
    """
    文档处理流水线

    将原始文件 → KnowledgeChunk 列表
    """

    def __init__(
        self,
        default_domain: str = "general",
        default_doc_type: str = "knowledge",
        chunk_size: int = 500,
        chunk_overlap: int = 80,
    ):
        self.default_domain = default_domain
        self.default_doc_type = default_doc_type
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_file(
        self,
        file_path: str,
        doc_id: Optional[str] = None,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        source: Optional[str] = None,
        output_markdown: bool = False,
        markdown_output_dir: Optional[str] = None,
    ) -> list[KnowledgeChunk]:
        """
        处理单个文件，返回 KnowledgeChunk 列表
        
        Args:
            output_markdown: 是否输出 Markdown 文件
            markdown_output_dir: Markdown 输出目录
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        doc_id = doc_id or path.stem
        domain = domain or self.default_domain
        doc_type = doc_type or self.default_doc_type
        source = source or str(path)
        
        suffix = path.suffix.lower()
        
        # 检查是否有对应解析器
        parser = get_parser(suffix)
        if parser:
            # 生成 Markdown 输出路径
            md_output_path = None
            if output_markdown:
                md_dir = Path(markdown_output_dir) if markdown_output_dir else path.parent.parent / "parsed"
                md_output_path = str(md_dir / f"{path.stem}.md")
            
            # 解析为 Markdown
            markdown_text = parser.to_markdown(str(path), md_output_path)
            
            # 复用 Markdown 处理逻辑
            return self._process_markdown(markdown_text, doc_id, domain, doc_type, source)
        
        # 原有逻辑保持不变
        text = path.read_text(encoding="utf-8")
        if suffix == ".md":
            return self._process_markdown(text, doc_id, domain, doc_type, source)
        elif suffix == ".json":
            return self._process_json(text, doc_id, domain, doc_type, source)
        elif suffix == ".txt":
            return self._process_plain_text(text, doc_id, domain, doc_type, source)
        else:
            # 尝试当纯文本处理
            return self._process_plain_text(text, doc_id, domain, doc_type, source)

    def _process_markdown(
        self, text: str, doc_id: str, domain: str, doc_type: str, source: str
    ) -> list[KnowledgeChunk]:
        sections = parse_markdown(text, doc_id, domain, source)
        return self._sections_to_chunks(sections, doc_id, domain, doc_type, source)

    def _process_json(
        self, text: str, doc_id: str, domain: str, doc_type: str, source: str
    ) -> list[KnowledgeChunk]:
        data = json.loads(text)
        sections = parse_json_doc(data, doc_id)
        # JSON 文档可能自带 domain 和 doc_type
        domain = data.get("domain", domain)
        doc_type = data.get("doc_type", doc_type)
        return self._sections_to_chunks(sections, doc_id, domain, doc_type, source)

    def _process_plain_text(
        self, text: str, doc_id: str, domain: str, doc_type: str, source: str
    ) -> list[KnowledgeChunk]:
        chunks = chunk_text(text, self.chunk_size, self.chunk_overlap)
        result = []
        for i, chunk_content in enumerate(chunks):
            keywords = extract_keywords(chunk_content)
            result.append(KnowledgeChunk(
                content=chunk_content,
                doc_id=doc_id,
                title=f"{doc_id} - 片段 {i+1}",
                title_path=doc_id,
                domain=domain,
                doc_type=doc_type,
                source=source,
                keywords=keywords,
            ))
        return result

    def _sections_to_chunks(
        self,
        sections: list[dict],
        doc_id: str,
        domain: str,
        doc_type: str,
        source: str,
    ) -> list[KnowledgeChunk]:
        chunks = []
        for sec in sections:
            content = sec["content"]
            # 如果单节内容过长，进一步分块
            sub_chunks = chunk_text(content, self.chunk_size, self.chunk_overlap)
            for j, sub_content in enumerate(sub_chunks):
                keywords = extract_keywords(sub_content)
                tags = sec.get("tags", [])
                chunk_domain = sec.get("domain", domain)
                chunk_doc_type = sec.get("doc_type", doc_type)
                chunks.append(KnowledgeChunk(
                    content=sub_content,
                    doc_id=doc_id,
                    title=sec.get("title_path", doc_id),
                    title_path=sec.get("title_path", ""),
                    domain=chunk_domain,
                    doc_type=chunk_doc_type,
                    source=source,
                    keywords=keywords,
                    tags=tags,
                ))
        return chunks

    def process_directory(
        self,
        dir_path: str,
        domain: Optional[str] = None,
        recursive: bool = True,
        output_markdown: bool = False,
        markdown_output_dir: Optional[str] = None,
    ) -> list[KnowledgeChunk]:
        """处理目录下所有文档"""
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")

        all_chunks = []
        # 支持的扩展名：原有格式 + 新格式
        extensions = {".md", ".json", ".txt"}.union(get_supported_extensions())
        glob_method = path.rglob if recursive else path.glob
        for file in glob_method("*"):
            if file.suffix.lower() in extensions:
                chunks = self.process_file(
                    str(file),
                    domain=domain,
                    source=str(file),
                    output_markdown=output_markdown,
                    markdown_output_dir=markdown_output_dir,
                )
                all_chunks.extend(chunks)
                print(f"  📄 {file.name} → {len(chunks)} 个知识片段")

        return all_chunks
