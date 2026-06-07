#!/usr/bin/env python3
"""
ReAct Agent + Knowledge 启动入口

使用方式：
1. 交互模式:       python main.py
2. 单次查询:       python main.py "你的问题"
3. 静默模式:       python main.py --quiet "你的问题"
4. 入库文档:       python main.py --ingest knowledge/raw --domain marketing
5. 查看知识库统计:  python main.py --stats
"""
import sys
import argparse

# 将项目根目录加入 sys.path
sys.path.insert(0, ".")

from agent import ReActAgent
from memory import AgentMemory
from knowledge import KnowledgeStore, DocumentProcessor


def main():
    parser = argparse.ArgumentParser(description="ReAct Agent + Knowledge - 推理+行动+知识框架")
    parser.add_argument("query", nargs="?", help="单次查询内容（留空则进入交互模式）")
    parser.add_argument("--quiet", action="store_true", help="静默模式，减少输出")
    parser.add_argument("--model", default=None, help="覆盖默认模型名称")
    parser.add_argument("--max-iter", type=int, default=None, help="最大推理轮次")
    parser.add_argument("--ingest", metavar="DIR", help="入库指定目录下的文档")
    parser.add_argument("--ingest-domain", default="general", help="入库文档的领域标签")
    parser.add_argument("--output-markdown", action="store_true", help="是否输出 Markdown 文件")
    parser.add_argument("--markdown-output-dir", help="Markdown 输出目录")
    parser.add_argument("--stats", action="store_true", help="查看知识库统计")
    args = parser.parse_args()

    # ── 知识库管理命令 ──
    if args.stats:
        store = KnowledgeStore()
        stats = store.stats()
        print("\n[知识库统计]")
        total = 0
        for name, info in stats.items():
            count = info["count"]
            total += count
            print(f"  {name}: {count} 条")
        print(f"  ──────────")
        print(f"  总计: {total} 条\n")
        return

    if args.ingest:
        from knowledge.pipelines import ingest_directory
        ingest_directory(
            args.ingest, 
            domain=args.ingest_domain,
            output_markdown=args.output_markdown,
            markdown_output_dir=args.markdown_output_dir,
        )
        return

    # ── Agent 对话 ──
    memory = AgentMemory()
    knowledge_store = KnowledgeStore()
    agent_kwargs = {
        "memory": memory,
        "knowledge_store": knowledge_store,
    }
    if args.model:
        agent_kwargs["model"] = args.model
    if args.max_iter:
        agent_kwargs["max_iterations"] = args.max_iter

    try:
        agent = ReActAgent(**agent_kwargs)
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    if args.query:
        # 单次查询模式
        result = agent.run(args.query, verbose=not args.quiet)
        if args.quiet:
            print(result)
    else:
        # 交互模式
        agent.chat(verbose=not args.quiet)


if __name__ == "__main__":
    main()
