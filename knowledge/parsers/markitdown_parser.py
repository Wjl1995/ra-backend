"""
MarkItDown Parser Adapter
使用 Microsoft MarkItDown 作为文档解析引擎
"""
from pathlib import Path
from typing import Optional
from .base import BaseParser

try:
    from markitdown import MarkItDown
    HAS_MARKITDOWN = True
except ImportError:
    HAS_MARKITDOWN = False
    MarkItDown = None


class MarkItDownParser(BaseParser):
    """
    Microsoft MarkItDown 统一解析器

    支持格式：
    - Office: .docx, .xlsx, .pptx
    - PDF: .pdf
    - 图片: .jpg, .jpeg, .png (需要 OCR)
    - 音视频: .mp3, .wav, .mp4 (提取元数据)
    - 压缩包: .zip
    - 网页: .html, .htm
    """

    def __init__(self, enable_ocr: bool = False):
        """
        Args:
            enable_ocr: 是否启用 OCR 功能（需要安装额外依赖）
        """
        super().__init__()
        self.enable_ocr = enable_ocr
        self._converter = None

    def supported_extensions(self) -> list[str]:
        return [
            ".pdf", ".docx", ".xlsx", ".pptx",
            ".jpg", ".jpeg", ".png",
            ".mp3", ".wav", ".mp4",
            ".zip", ".html", ".htm"
        ]

    def to_markdown(self, file_path: str, output_path: Optional[str] = None) -> str:
        if not HAS_MARKITDOWN:
            raise ImportError(
                "MarkItDown not installed. Run: pip install markitdown"
            )

        if self._converter is None:
            self._converter = MarkItDown()

        # 转换为 Markdown
        result = self._converter.convert(file_path)
        markdown_text = result.text_content

        if output_path:
            self._save_markdown(markdown_text, output_path)

        return markdown_text


class HybridParser(BaseParser):
    """
    混合解析器：优先使用 MarkItDown，失败时回退到原生解析器

    这种方式可以：
    1. 利用 MarkItDown 的高级功能（OCR、更好的格式保留）
    2. 保留原有解析器作为备份，确保稳定性
    3. 根据文件类型选择最佳解析器
    """

    def __init__(self, fallback_parser: BaseParser, prefer_markitdown: bool = True):
        """
        Args:
            fallback_parser: 回退解析器（原生解析器）
            prefer_markitdown: 是否优先使用 MarkItDown
        """
        super().__init__()
        self.fallback_parser = fallback_parser
        self.prefer_markitdown = prefer_markitdown and HAS_MARKITDOWN

        if self.prefer_markitdown:
            self.markitdown_parser = MarkItDownParser()

    def supported_extensions(self) -> list[str]:
        # 仅声明原生回退解析器负责的扩展名，避免不同格式相互覆盖
        return list(self.fallback_parser.supported_extensions())

    def to_markdown(self, file_path: str, output_path: Optional[str] = None) -> str:
        file_ext = Path(file_path).suffix.lower()

        # 策略1：优先使用 MarkItDown
        if self.prefer_markitdown:
            try:
                return self.markitdown_parser.to_markdown(file_path, output_path)
            except Exception as e:
                print(f"[警告] MarkItDown 解析失败，回退到原生解析器: {e}")
                return self.fallback_parser.to_markdown(file_path, output_path)

        # 策略2：使用原生解析器
        return self.fallback_parser.to_markdown(file_path, output_path)
