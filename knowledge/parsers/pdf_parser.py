
"""
PDF 文档解析器（双库支持）
优先使用 pdfplumber（MIT 许可证），备选 PyMuPDF
"""
from pathlib import Path
from typing import Optional
from .base import BaseParser

# 检查可用库
HAS_PDFPLUMBER = False
HAS_PYMUPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    pass

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    pass


class PdfParser(BaseParser):
    """PDF 文档解析器"""
    
    def supported_extensions(self) -> list[str]:
        return [".pdf"]
    
    def to_markdown(self, file_path: str, output_path: Optional[str] = None) -> str:
        if HAS_PDFPLUMBER:
            return self._parse_with_pdfplumber(file_path, output_path)
        elif HAS_PYMUPDF:
            return self._parse_with_pymupdf(file_path, output_path)
        else:
            raise ImportError(
                "No PDF library available. Install either:\n"
                "  - pdfplumber (recommended): pip install pdfplumber\n"
                "  - PyMuPDF: pip install pymupdf"
            )
    
    def _parse_with_pdfplumber(self, file_path: str, output_path: Optional[str] = None) -> str:
        """使用 pdfplumber 解析 PDF"""
        markdown_parts = []
        
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_parts = [f"---\n\n## 第 {page_num} 页\n"]
                
                # 提取文本
                text = page.extract_text()
                if text:
                    page_parts.append(text)
                
                # 提取表格
                tables = page.extract_tables()
                for table in tables:
                    md_table = self._table_to_markdown(table)
                    if md_table:
                        page_parts.append(f"\n{md_table}")
                
                if len(page_parts) > 2:
                    markdown_parts.append("\n".join(page_parts))
        
        markdown_text = "\n\n".join(markdown_parts)
        
        if output_path:
            self._save_markdown(markdown_text, output_path)
        
        return markdown_text
    
    def _parse_with_pymupdf(self, file_path: str, output_path: Optional[str] = None) -> str:
        """使用 PyMuPDF 解析 PDF（备选）"""
        markdown_parts = []
        
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            page_parts = [f"---\n\n## 第 {page_num} 页\n"]
            
            # 提取文本
            text = page.get_text()
            if text:
                page_parts.append(text)
            
            if len(page_parts) > 2:
                markdown_parts.append("\n".join(page_parts))
        
        markdown_text = "\n\n".join(markdown_parts)
        
        if output_path:
            self._save_markdown(markdown_text, output_path)
        
        return markdown_text
    
    def _table_to_markdown(self, table: list[list]) -> str:
        """将表格数据转换为 Markdown"""
        if not table or not table[0]:
            return ""
        
        rows = []
        for row in table:
            cells = [str(cell).strip().replace('\n', ' ') if cell else '' for cell in row]
            rows.append(f"| {' | '.join(cells)} |")
        
        # 添加分隔线
        separator = f"| {' | '.join(['---'] * len(table[0]))} |"
        rows.insert(1, separator)
        
        return "\n".join(rows)

