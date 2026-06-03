#!/usr/bin/env python3
"""
快速启动脚本 —— 一键入库示例文档 + 启动 Agent

使用: python quickstart.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from knowledge.store import KnowledgeStore
from knowledge.processor import DocumentProcessor
from knowledge.pipelines import ingest_directory, show_stats
from agent import ReActAgent

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "knowledge", "raw")


def main():
    print("=" * 60)
    print("🚀 ReAct Agent + Knowledge 快速启动")
    print("=" * 60)

    # Step 1: 入库示例文档
    store = KnowledgeStore()
    stats_before = store.stats()
    total_before = sum(s["count"] for s in stats_before.values())

    if total_before == 0:
        print("\n📥 知识库为空，正在导入示例文档...")
        ingest_directory(SAMPLE_DIR, domain="marketing")
    else:
        print(f"\n📊 知识库已有 {total_before} 条知识，跳过导入")

    # Step 2: 显示统计
    show_stats(store)

    # Step 3: 启动 Agent
    print("\n" + "=" * 60)
    print("🤖 启动 Agent...")
    print("=" * 60)
    print()
    print("💡 试试这些问题：")
    print("  - 什么是GMV？和收入有什么区别？")
    print("  - 活动预算超50万需要谁审批？")
    print("  - 有没有裂变活动的案例可以参考？")
    print("  - 帮我把这次对话的经验保存下来")
    print()

    try:
        agent = ReActAgent(knowledge_store=store)
        agent.chat()
    except ValueError as e:
        print(f"\n❌ {e}")
        print("\n请先配置 API Key:")
        print("  1. cp .env.example .env")
        print("  2. 编辑 .env 填入 KIMI_API_KEY")


if __name__ == "__main__":
    main()
