
"""
文档解析器基类
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseParser(ABC):
    """文档解析器基类"""
    
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """返回支持的扩展名列表"""
        pass
    
    @abstractmethod
    def to_markdown(self, file_path: str, output_path: Optional[str] = None) -> str:
        """
        解析文档为 Markdown
        
        Args:
            file_path: 输入文件路径
            output_path: 可选，保存 Markdown 到文件
            
        Returns:
            Markdown 字符串
        """
        pass
    
    def _save_markdown(self, markdown_text: str, output_path: str):
        """保存 Markdown 到文件"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown_text, encoding="utf-8")

