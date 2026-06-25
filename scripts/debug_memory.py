from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - fallback for lightweight envs
    Console = None
    Panel = None
    Table = None


console = Console() if Console else None


def print_message(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    if console and Table:
        table = Table(title=title)
        for column in columns:
            table.add_column(column)
        for row in rows:
            table.add_row(*row)
        console.print(table)
        return

    print(title)
    print(" | ".join(columns))
    print("-" * 80)
    for row in rows:
        print(" | ".join(row))


def print_panel(title: str, body: str) -> None:
    if console and Panel:
        console.print(Panel(body, title=title))
        return
    print(f"[{title}]")
    print(body)


def abort(message: str, exit_code: int = 1) -> int:
    prefix = "[red]错误:[/red] " if console else "错误: "
    print_message(f"{prefix}{message}")
    return exit_code


def load_long_term_memory(persist_dir: str | None = None):
    try:
        from memory import LongTermMemory
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        raise RuntimeError(
            f"无法导入项目依赖 '{missing}'。请在后端项目环境中运行，或先执行 `pip install -r requirements.txt`。"
        ) from exc

    kwargs: dict[str, Any] = {}
    if persist_dir:
        kwargs["persist_dir"] = persist_dir
    return LongTermMemory(**kwargs)


def normalize_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    rows: list[dict[str, Any]] = []
    for index, doc_id in enumerate(ids):
        rows.append(
            {
                "id": doc_id,
                "text": documents[index] if index < len(documents) else "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
        )
    return rows


def filter_rows(rows: list[dict[str, Any]], tag: str | None, memory_type: str | None) -> list[dict[str, Any]]:
    filtered = rows
    if tag:
        filtered = [row for row in filtered if row["metadata"].get("tag") == tag]
    if memory_type:
        filtered = [row for row in filtered if row["metadata"].get("type") == memory_type]
    return filtered


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: row["metadata"].get("timestamp", ""), reverse=True)


def list_memories(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    rows = normalize_rows(ltm.collection.get())
    rows = filter_rows(rows, args.tag, args.memory_type)
    rows = sort_rows(rows)
    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        print_message("[yellow]没有找到匹配的长期记忆[/yellow]" if console else "没有找到匹配的长期记忆")
        return 0

    table_rows = []
    for row in rows:
        metadata = row["metadata"]
        content = row["text"].replace("\n", " ")
        preview = content[:120] + ("..." if len(content) > 120 else "")
        table_rows.append(
            [
                row["id"],
                metadata.get("tag", "-"),
                metadata.get("type", "-"),
                metadata.get("timestamp", "-")[:19],
                preview,
            ]
        )

    print_table("长期记忆列表", ["ID", "Tag", "Type", "Timestamp", "Preview"], table_rows)
    return 0


def search_memories(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    results = ltm.search(args.query, top_k=args.top_k)
    if not results:
        print_message("[yellow]没有找到相关记忆[/yellow]" if console else "没有找到相关记忆")
        return 0

    table_rows = []
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata", {})
        similarity = 1 - float(item.get("distance", 1))
        content = str(item.get("text", "")).replace("\n", " ")
        preview = content[:120] + ("..." if len(content) > 120 else "")
        table_rows.append(
            [
                str(index),
                f"{similarity:.2%}",
                metadata.get("tag", "-"),
                metadata.get("type", "-"),
                preview,
            ]
        )

    print_table("长期记忆搜索结果", ["#", "Similarity", "Tag", "Type", "Preview"], table_rows)
    return 0


def add_memory(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    metadata: dict[str, Any] = {"tag": args.tag}
    if args.memory_type:
        metadata["type"] = args.memory_type
    for item in args.metadata:
        key, value = item.split("=", 1)
        metadata[key] = value
    doc_id = ltm.add(args.content, metadata=metadata)
    print_message(f"[green]已添加长期记忆[/green] ID={doc_id}" if console else f"已添加长期记忆 ID={doc_id}")
    return 0


def delete_memory(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    ltm.delete(args.id)
    print_message(f"[green]已删除长期记忆[/green] ID={args.id}" if console else f"已删除长期记忆 ID={args.id}")
    return 0


def delete_by_type(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    rows = normalize_rows(ltm.collection.get())
    matched_ids = [row["id"] for row in rows if row["metadata"].get("type") == args.memory_type]
    if not matched_ids:
        print_message(
            "[yellow]没有找到匹配类型的长期记忆[/yellow]" if console else "没有找到匹配类型的长期记忆"
        )
        return 0

    if not args.yes:
        return abort("删除按类型批量操作需要显式传入 --yes。")

    ltm.collection.delete(ids=matched_ids)
    print_message(
        f"[green]已删除 {len(matched_ids)} 条长期记忆[/green]" if console else f"已删除 {len(matched_ids)} 条长期记忆"
    )
    return 0


def clear_memories(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    all_ids = ltm.collection.get().get("ids") or []
    if not all_ids:
        print_message("[yellow]当前没有可清空的长期记忆[/yellow]" if console else "当前没有可清空的长期记忆")
        return 0

    if not args.yes:
        return abort("清空操作需要显式传入 --yes。")

    ltm.collection.delete(ids=all_ids)
    print_message(
        f"[green]已清空 {len(all_ids)} 条长期记忆[/green]" if console else f"已清空 {len(all_ids)} 条长期记忆"
    )
    return 0


def show_stats(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    rows = normalize_rows(ltm.collection.get())
    type_counter = Counter(row["metadata"].get("type", "(none)") for row in rows)
    tag_counter = Counter(row["metadata"].get("tag", "(none)") for row in rows)

    lines = [f"总数: {ltm.count()}"]
    if type_counter:
        lines.append("类型分布:")
        for name, count in type_counter.most_common():
            lines.append(f"  - {name}: {count}")
    if tag_counter:
        lines.append("标签分布:")
        for name, count in tag_counter.most_common(10):
            lines.append(f"  - {name}: {count}")
    print_panel("长期记忆统计", "\n".join(lines))
    return 0


def show_detail(args: argparse.Namespace) -> int:
    ltm = load_long_term_memory(args.persist_dir)
    result = ltm.collection.get(ids=[args.id])
    rows = normalize_rows(result)
    if not rows:
        return abort(f"未找到 ID 为 {args.id} 的长期记忆。")

    row = rows[0]
    metadata = json.dumps(row["metadata"], ensure_ascii=False, indent=2)
    body = f"{row['text']}\n\nMetadata:\n{metadata}"
    print_panel(f"长期记忆详情: {args.id}", body)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="长期记忆调试脚本")
    parser.add_argument(
        "--persist-dir",
        help="覆盖默认 Chroma 持久化目录；不传则使用 config.py 中的 CHROMA_PERSIST_DIR。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出长期记忆")
    list_parser.add_argument("--tag", help="只显示指定 tag")
    list_parser.add_argument("--type", dest="memory_type", help="只显示指定 metadata.type")
    list_parser.add_argument("--limit", type=int, default=20, help="最多显示多少条")
    list_parser.set_defaults(func=list_memories)

    search_parser = subparsers.add_parser("search", help="搜索长期记忆")
    search_parser.add_argument("query", help="搜索词")
    search_parser.add_argument("--top-k", type=int, default=5, help="返回多少条结果")
    search_parser.set_defaults(func=search_memories)

    add_parser = subparsers.add_parser("add", help="添加长期记忆")
    add_parser.add_argument("content", help="记忆内容")
    add_parser.add_argument("--tag", default="general", help="metadata.tag")
    add_parser.add_argument("--type", dest="memory_type", help="metadata.type，例如 conversation_round")
    add_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="追加自定义 metadata，可重复传入",
    )
    add_parser.set_defaults(func=add_memory)

    detail_parser = subparsers.add_parser("detail", help="查看单条长期记忆")
    detail_parser.add_argument("id", help="长期记忆 ID")
    detail_parser.set_defaults(func=show_detail)

    delete_parser = subparsers.add_parser("delete", help="删除单条长期记忆")
    delete_parser.add_argument("id", help="长期记忆 ID")
    delete_parser.set_defaults(func=delete_memory)

    delete_type_parser = subparsers.add_parser("delete-type", help="按 metadata.type 批量删除")
    delete_type_parser.add_argument("memory_type", help="metadata.type，例如 conversation_round")
    delete_type_parser.add_argument("--yes", action="store_true", help="确认执行删除")
    delete_type_parser.set_defaults(func=delete_by_type)

    clear_parser = subparsers.add_parser("clear", help="清空全部长期记忆")
    clear_parser.add_argument("--yes", action="store_true", help="确认执行清空")
    clear_parser.set_defaults(func=clear_memories)

    stats_parser = subparsers.add_parser("stats", help="查看长期记忆统计")
    stats_parser.set_defaults(func=show_stats)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        return abort(str(exc))
    except ValueError as exc:
        return abort(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
