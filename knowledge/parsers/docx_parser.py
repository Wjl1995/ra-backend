
"""
Word 文档解析器
"""
from pathlib import Path
from typing import Optional
from .base import BaseParser

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    Table = None
    Paragraph = None


class DocxParser(BaseParser):
    """Word (.docx) 文档解析器"""
    
    def supported_extensions(self) -> list[str]:
        return [".docx"]
    
    def to_markdown(self, file_path: str, output_path: Optional[str] = None) -> str:
        if not HAS_DOCX:
            raise ImportError("python-docx not installed. Run: pip install python-docx")
        
        doc = Document(file_path)
        markdown_parts = []
        
        for block in doc.element.body:
            if block.tag.endswith('p'):
                # 处理段落
                para = Paragraph(block, doc._parent)
                md_line = self._parse_paragraph(para)
                if md_line:
                    markdown_parts.append(md_line)
            elif block.tag.endswith('tbl'):
                # 处理表格
                table = Table(block, doc._parent)
                md_table = self._parse_table(table)
                if md_table:
                    markdown_parts.append(md_table)
        
        markdown_text = "\n\n".join(markdown_parts)
        
        if output_path:
            self._save_markdown(markdown_text, output_path)
        
        return markdown_text
    
    def _parse_paragraph(self, para) -> str:
        """解析段落为 Markdown"""
        style = para.style.name.lower()
        
        # 处理标题
        if style.startswith('heading'):
            try:
                level = int(style.split()[-1])
                return f"{'#' * level} {para.text.strip()}"
            except (IndexError, ValueError):
                pass
        
        # 处理列表
        if para.style.name.startswith('List'):
            return f"- {para.text.strip()}"
        
        # 普通段落
        text = para.text.strip()
        if text:
            return text
        return ""
    
    def _parse_table(self, table) -> str:
        """解析表格为 Markdown"""
        rows = []
        for i, row in enumerate(table.rows):
            cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
            rows.append(f"| {' | '.join(cells)} |")
        
        if not rows:
            return ""
        
        # 添加分隔线
        separator = f"| {' | '.join(['---'] * len(table.rows[0].cells))} |"
        rows.insert(1, separator)
        
        return "\n".join(rows)

