
"""
文档解析器模块
"""
from typing import Optional
from .base import BaseParser
from .docx_parser import DocxParser
from .pptx_parser import PptxParser
from .pdf_parser import PdfParser
from .xlsx_parser import XlsxParser

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


# 自动注册所有解析器
register_parser(DocxParser())
register_parser(PptxParser())
register_parser(PdfParser())
register_parser(XlsxParser())

