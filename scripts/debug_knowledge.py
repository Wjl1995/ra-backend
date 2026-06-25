from __future__ import annotations

import argparse
import json
import sys
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

DOC_TYPE_TO_COLLECTION = {
    "knowledge": "knowledge",
    "rule": "rules",
    "rules": "rules",
    "case": "cases",
    "cases": "cases",
}

DOC_TYPE_ALIASES = {
    "knowledge": "knowledge",
    "rule": "rule",
    "rules": "rule",
    "case": "case",
    "cases": "case",
}


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
    print("-" * 100)
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


def load_knowledge_store(persist_dir: str | None = None):
    try:
        from knowledge import KnowledgeStore
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        raise RuntimeError(
            f"无法导入项目依赖 '{missing}'。请在后端项目环境中运行，或先执行 `pip install -r requirements.txt`。"
        ) from exc

    kwargs: dict[str, Any] = {}
    if persist_dir:
        kwargs["persist_dir"] = persist_dir
    return KnowledgeStore(**kwargs)


def normalize_collection_name(name: str) -> str:
    try:
        return DOC_TYPE_TO_COLLECTION[name]
    except KeyError as exc:
        valid = ", ".join(sorted(DOC_TYPE_TO_COLLECTION))
        raise ValueError(f"无效集合类型: {name}。可选值: {valid}") from exc


def normalize_doc_type(name: str | None) -> str | None:
    if name is None:
        return None
    try:
        return DOC_TYPE_ALIASES[name]
    except KeyError as exc:
        valid = ", ".join(sorted(DOC_TYPE_ALIASES))
        raise ValueError(f"无效文档类型: {name}。可选值: {valid}") from exc


def parse_json_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if not isinstance(value, str):
        return str(value or "")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed)
    return str(parsed)


def list_knowledge(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    collection_names = [normalize_collection_name(args.collection)] if args.collection else list(store.collections.keys())

    rows: list[list[str]] = []
    for collection_name in collection_names:
        result = store.collections[collection_name].get()
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        for index, doc_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) else {}
            if args.domain and metadata.get("domain") != args.domain:
                continue
            preview = str(documents[index]).replace("\n", " ")[:100]
            if index < len(documents) and len(str(documents[index])) > 100:
                preview += "..."
            rows.append(
                [
                    collection_name,
                    doc_id,
                    metadata.get("title_path") or metadata.get("title") or "-",
                    metadata.get("domain", "-"),
                    parse_json_list(metadata.get("tags", "")),
                    preview,
                ]
            )

    if not rows:
        print_message("[yellow]没有找到匹配的知识片段[/yellow]" if console else "没有找到匹配的知识片段")
        return 0

    rows.sort(key=lambda row: (row[0], row[2], row[1]))
    if args.limit:
        rows = rows[: args.limit]
    print_table("知识库列表", ["Collection", "ID", "Title", "Domain", "Tags", "Preview"], rows)
    return 0


def search_knowledge(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    doc_type = normalize_doc_type(args.doc_type)
    tags = [item.strip() for item in args.tags.split(",")] if args.tags else None
    results = store.search(
        args.query,
        doc_type=doc_type,
        domain=args.domain,
        tags=tags,
        top_k=args.top_k,
    )
    if not results:
        print_message("[yellow]没有找到相关知识片段[/yellow]" if console else "没有找到相关知识片段")
        return 0

    rows: list[list[str]] = []
    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata", {})
        preview = str(item.get("content", "")).replace("\n", " ")[:120]
        if len(str(item.get("content", ""))) > 120:
            preview += "..."
        rows.append(
            [
                str(index),
                item.get("collection", "-"),
                f"{float(item.get('score', 0)):.2%}",
                metadata.get("title_path") or metadata.get("title") or "-",
                metadata.get("domain", "-"),
                preview,
            ]
        )

    print_table("知识库搜索结果", ["#", "Collection", "Score", "Title", "Domain", "Preview"], rows)
    return 0


def show_detail(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    collection_name = normalize_collection_name(args.collection)
    result = store.collections[collection_name].get(ids=[args.id])
    ids = result.get("ids") or []
    if not ids:
        return abort(f"未找到 ID 为 {args.id} 的知识片段。")

    text = result["documents"][0]
    metadata = result["metadatas"][0]
    body = f"{text}\n\nMetadata:\n{json.dumps(metadata, ensure_ascii=False, indent=2)}"
    title = metadata.get("title_path") or metadata.get("title") or args.id
    print_panel(f"{collection_name}: {title}", body)
    return 0


def delete_knowledge(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    collection_name = normalize_collection_name(args.collection)
    store.collections[collection_name].delete(ids=[args.id])
    print_message(
        f"[green]已删除知识片段[/green] collection={collection_name} id={args.id}"
        if console
        else f"已删除知识片段 collection={collection_name} id={args.id}"
    )
    return 0


def clear_collection(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    collection_name = normalize_collection_name(args.collection)
    all_ids = store.collections[collection_name].get().get("ids") or []
    if not all_ids:
        print_message("[yellow]该集合当前为空[/yellow]" if console else "该集合当前为空")
        return 0

    if not args.yes:
        return abort("清空集合需要显式传入 --yes。")

    store.collections[collection_name].delete(ids=all_ids)
    print_message(
        f"[green]已清空 {len(all_ids)} 条知识片段[/green]" if console else f"已清空 {len(all_ids)} 条知识片段"
    )
    return 0


def show_stats(args: argparse.Namespace) -> int:
    store = load_knowledge_store(args.persist_dir)
    stats = store.stats()
    lines = []
    total = 0
    for name, info in stats.items():
        count = int(info.get("count", 0))
        total += count
        lines.append(f"{name}: {count}")
    lines.append(f"total: {total}")
    print_panel("知识库统计", "\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识库调试脚本")
    parser.add_argument(
        "--persist-dir",
        help="覆盖默认 Chroma 持久化目录；不传则使用 config.py 中的 CHROMA_PERSIST_DIR。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出知识片段")
    list_parser.add_argument("--collection", help="限定集合：knowledge/rules/cases")
    list_parser.add_argument("--domain", help="限定领域")
    list_parser.add_argument("--limit", type=int, default=20, help="最多显示多少条")
    list_parser.set_defaults(func=list_knowledge)

    search_parser = subparsers.add_parser("search", help="搜索知识片段")
    search_parser.add_argument("query", help="搜索词")
    search_parser.add_argument("--type", dest="doc_type", help="限定类型：knowledge/rule/rules/case/cases")
    search_parser.add_argument("--domain", help="限定领域")
    search_parser.add_argument("--tags", help="按标签过滤，多个标签用逗号分隔")
    search_parser.add_argument("--top-k", type=int, default=5, help="返回多少条结果")
    search_parser.set_defaults(func=search_knowledge)

    detail_parser = subparsers.add_parser("detail", help="查看单条知识片段")
    detail_parser.add_argument("collection", help="集合名：knowledge/rules/cases")
    detail_parser.add_argument("id", help="知识片段 ID")
    detail_parser.set_defaults(func=show_detail)

    delete_parser = subparsers.add_parser("delete", help="删除单条知识片段")
    delete_parser.add_argument("collection", help="集合名：knowledge/rules/cases")
    delete_parser.add_argument("id", help="知识片段 ID")
    delete_parser.set_defaults(func=delete_knowledge)

    clear_parser = subparsers.add_parser("clear", help="清空指定集合")
    clear_parser.add_argument("collection", help="集合名：knowledge/rules/cases")
    clear_parser.add_argument("--yes", action="store_true", help="确认执行清空")
    clear_parser.set_defaults(func=clear_collection)

    stats_parser = subparsers.add_parser("stats", help="查看知识库统计")
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
