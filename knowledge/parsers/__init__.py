
"""
文档解析器模块
"""
from typing import Optional
from .base import BaseParser
from .docx_parser import DocxParser
from .pptx_parser import PptxParser
from .pdf_parser import PdfParser
from .xlsx_parser import XlsxParser

# 尝试导入 MarkItDown 解析器
try:
    from .markitdown_parser import MarkItDownParser, HybridParser
    HAS_MARKITDOWN = True
except ImportError:
    HAS_MARKITDOWN = False
    MarkItDownParser = None
    HybridParser = None

# 配置：是否使用 MarkItDown
USE_MARKITDOWN = True  # 已解决依赖冲突，启用！

_PARSER_REGISTRY: dict[str, BaseParser] = {}


def register_parser(parser: BaseParser):
    """注册解析器"""
    for ext in parser.supported_extensions():
        _PARSER_REGISTRY[ext.lower()] = parser


def get_parser(ext: str) -> Optional[BaseParser]:
    """获取对应扩展名的解析器"""
    return _PARSER_REGISTRY.get(ext.lower())


def get_supported_extensions() -> list[str]:
    """获取所有支持的扩展名"""
    return list(_PARSER_REGISTRY.keys())


# 注册解析器
if USE_MARKITDOWN and HAS_MARKITDOWN:
    # 使用混合模式：优先 MarkItDown，失败时回退到原生解析器
    print("[知识库] 使用 MarkItDown 混合解析器（推荐）")

    # 为每种格式创建混合解析器
    register_parser(HybridParser(PdfParser(), prefer_markitdown=True))
    register_parser(HybridParser(DocxParser(), prefer_markitdown=True))
    register_parser(HybridParser(PptxParser(), prefer_markitdown=True))
    register_parser(HybridParser(XlsxParser(), prefer_markitdown=True))

    # MarkItDown 额外支持的格式（图片、音视频等）
    markitdown_only = MarkItDownParser()
    for ext in [".jpg", ".jpeg", ".png", ".mp3", ".wav", ".mp4", ".zip", ".html", ".htm"]:
        if ext not in _PARSER_REGISTRY:
            register_parser(markitdown_only)
            break
else:
    # 使用原生解析器
    if not HAS_MARKITDOWN:
        print("[知识库] MarkItDown 未安装，使用原生解析器")
    else:
        print("[知识库] 使用原生解析器")

    register_parser(DocxParser())
    register_parser(PptxParser())
    register_parser(PdfParser())
    register_parser(XlsxParser())


