#!/usr/bin/env python3
"""
Knowledge Pipeline —— 知识库入库流水线

一条命令完成：文档 → 解析 → 分块 → 入库

使用方式：
  python -m knowledge.pipelines.ingest --dir knowledge/raw --domain marketing
  python -m knowledge.pipelines.ingest --file knowledge/raw/faq.md
  python -m knowledge.pipelines.ingest --stats
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")

from knowledge.store import KnowledgeStore
from knowledge.processor import DocumentProcessor


def ingest_file(
    file_path: str,
    domain: str = "general",
    doc_type: str = "knowledge",
    store: KnowledgeStore = None,
    processor: DocumentProcessor = None,
) -> int:
    """处理单个文件并入库，返回入库片段数"""
    store = store or KnowledgeStore()
    processor = processor or DocumentProcessor()

    chunks = processor.process_file(file_path, domain=domain, doc_type=doc_type)
    ids = store.add_chunks(chunks)
    print(f"✅ {file_path} → 入库 {len(ids)} 个知识片段")
    return len(ids)


def ingest_directory(
    dir_path: str,
    domain: str = "general",
    store: KnowledgeStore = None,
    processor: DocumentProcessor = None,
) -> int:
    """处理整个目录并入库，返回总入库片段数"""
    store = store or KnowledgeStore()
    processor = processor or DocumentProcessor()

    print(f"📂 扫描目录: {dir_path}")
    chunks = processor.process_directory(dir_path, domain=domain)

    if not chunks:
        print("⚠️ 未找到可处理的文档")
        return 0

    ids = store.add_chunks(chunks)
    print(f"\n✅ 共入库 {len(ids)} 个知识片段")
    return len(ids)


def show_stats(store: KnowledgeStore = None):
    """显示知识库统计"""
    store = store or KnowledgeStore()
    stats = store.stats()
    print("\n📊 知识库统计:")
    total = 0
    for name, info in stats.items():
        count = info["count"]
        total += count
        print(f"  {name}: {count} 条")
    print(f"  ──────────")
    print(f"  总计: {total} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知识库入库工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="入库单个文件")
    group.add_argument("--dir", help="入库整个目录")
    group.add_argument("--stats", action="store_true", help="查看知识库统计")
    parser.add_argument("--domain", default="general", help="领域标签")
    parser.add_argument("--doc-type", default="knowledge", help="文档类型 (knowledge/rule/case)")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.file:
        ingest_file(args.file, domain=args.domain, doc_type=args.doc_type)
    elif args.dir:
        ingest_directory(args.dir, domain=args.domain)
