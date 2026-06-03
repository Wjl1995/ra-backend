"""
Knowledge Pipelines —— 知识库操作流水线集合

包含：
- ingest: 文档入库流水线
"""
from .ingest import ingest_file, ingest_directory, show_stats

__all__ = ["ingest_file", "ingest_directory", "show_stats"]
