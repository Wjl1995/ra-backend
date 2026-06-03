#!/usr/bin/env python3
"""
知识库调试脚本
用于查看、搜索、管理知识库中的知识片段
"""
import sys
sys.path.insert(0, ".")

import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from knowledge import KnowledgeStore

console = Console()


def print_all_knowledge(store):
    """打印所有知识库内容"""
    all_data = store.collections["knowledge"].get()
    all_rules = store.collections["rules"].get()
    all_cases = store.collections["cases"].get()
    
    total = 0
    
    # 打印知识
    if all_data['ids']:
        total += len(all_data['ids'])
        table = Table(title="📚 通用知识")
        table.add_column("ID", style="cyan")
        table.add_column("标题", style="green")
        table.add_column("领域", style="yellow")
        table.add_column("标签", style="magenta")
        table.add_column("内容预览", style="white")
        
        for idx, doc_id in enumerate(all_data['ids']):
            text = all_data['documents'][idx]
            meta = all_data['metadatas'][idx]
            title = meta.get('title_path', meta.get('title', 'N/A'))
            domain = meta.get('domain', 'N/A')
            tags = meta.get('tags', '[]')
            table.add_row(doc_id[:8] + "...", title[:30], domain, tags, text[:80])
        
        console.print(table)
    
    # 打印规则
    if all_rules['ids']:
        total += len(all_rules['ids'])
        table = Table(title="📋 规则库")
        table.add_column("ID", style="cyan")
        table.add_column("标题", style="green")
        table.add_column("领域", style="yellow")
        table.add_column("标签", style="magenta")
        table.add_column("内容预览", style="white")
        
        for idx, doc_id in enumerate(all_rules['ids']):
            text = all_rules['documents'][idx]
            meta = all_rules['metadatas'][idx]
            title = meta.get('title_path', meta.get('title', 'N/A'))
            domain = meta.get('domain', 'N/A')
            tags = meta.get('tags', '[]')
            table.add_row(doc_id[:8] + "...", title[:30], domain, tags, text[:80])
        
        console.print(table)
    
    # 打印案例
    if all_cases['ids']:
        total += len(all_cases['ids'])
        table = Table(title="📌 案例库")
        table.add_column("ID", style="cyan")
        table.add_column("标题", style="green")
        table.add_column("领域", style="yellow")
        table.add_column("标签", style="magenta")
        table.add_column("内容预览", style="white")
        
        for idx, doc_id in enumerate(all_cases['ids']):
            text = all_cases['documents'][idx]
            meta = all_cases['metadatas'][idx]
            title = meta.get('title_path', meta.get('title', 'N/A'))
            domain = meta.get('domain', 'N/A')
            tags = meta.get('tags', '[]')
            table.add_row(doc_id[:8] + "...", title[:30], domain, tags, text[:80])
        
        console.print(table)
    
    if total == 0:
        console.print("[yellow]知识库为空[/yellow]")


def search_knowledge(store, query, doc_type=None, domain=None, top_k=5):
    """搜索知识库"""
    results = store.search(query, doc_type=doc_type, domain=domain, top_k=top_k)
    
    if not results:
        console.print(f"[yellow]没有找到与 '{query}' 相关的知识[/yellow]")
        return
    
    table = Table(title=f"🔍 搜索结果: '{query}'")
    table.add_column("排名", style="cyan")
    table.add_column("类型", style="green")
    table.add_column("标题", style="yellow")
    table.add_column("相关度", style="magenta")
    table.add_column("内容预览", style="white")
    
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        doc_type = r["collection"]
        title = meta.get('title_path', meta.get('title', 'N/A'))
        table.add_row(str(i), doc_type, title[:30], f"{r['score']:.2%}", r['content'][:100])
    
    console.print(table)


def show_detail(store, collection_name, doc_id):
    """显示单个知识片段的详细信息"""
    try:
        col = store.collections[collection_name]
        result = col.get(ids=[doc_id])
        if not result['ids']:
            console.print("[red]未找到该ID的知识片段[/red]")
            return
        
        text = result['documents'][0]
        meta = result['metadatas'][0]
        
        console.print(Panel(
            Text(text, style="white"),
            title=f"📝 {meta.get('title_path', meta.get('title', 'N/A'))}",
            subtitle=f"ID: {doc_id} | 领域: {meta.get('domain', 'N/A')} | 标签: {meta.get('tags', '[]')}"
        ))
        console.print("\n[dim]完整元数据:[/dim]")
        console.print_json(json.dumps(meta, ensure_ascii=False, indent=2))
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")


def delete_knowledge(store, collection_name, doc_id):
    """删除知识片段"""
    try:
        col = store.collections[collection_name]
        col.delete(ids=[doc_id])
        console.print(f"[green]✅ 已删除[/green] (ID: {doc_id}, Collection: {collection_name})")
    except Exception as e:
        console.print(f"[red]❌ 删除失败: {e}[/red]")


def clear_collection(store, collection_name):
    """清空指定集合"""
    confirm = console.input(f"[red]确定要清空 {collection_name} 吗？输入 YES 确认: [/red]")
    if confirm == "YES":
        col = store.collections[collection_name]
        all_ids = col.get()['ids']
        if all_ids:
            col.delete(ids=all_ids)
            console.print(f"[green]✅ 已清空 {len(all_ids)} 条知识[/green]")
        else:
            console.print("[yellow]该集合为空[/yellow]")
    else:
        console.print("[yellow]已取消[/yellow]")


def show_stats(store):
    """显示统计信息"""
    stats = store.stats()
    lines = []
    total = 0
    for name, info in stats.items():
        count = info["count"]
        total += count
        lines.append(f"  {name}: {count} 条")
    lines.append(f"  ──────────")
    lines.append(f"  总计: {total} 条")
    
    console.print(Panel("\n".join(lines), title="📊 知识库统计"))


def print_help():
    """打印帮助信息"""
    help_text = """
[bold]知识库调试脚本[/bold]

[cyan]用法:[/cyan]
  python debug_knowledge.py [命令] [参数...]

[cyan]命令:[/cyan]
  list                              列出所有知识
  search <query> [--type <t>]       搜索知识 (--type: knowledge/rules/cases)
  detail <collection> <id>          查看详细信息
  delete <collection> <id>          删除指定知识
  clear <collection>                清空指定集合 (knowledge/rules/cases)
  stats                             显示统计信息
  help                              显示帮助

[cyan]示例:[/cyan]
  python debug_knowledge.py list
  python debug_knowledge.py search "GMV"
  python debug_knowledge.py search "GMV" --type knowledge
  python debug_knowledge.py detail knowledge abc123...
  python debug_knowledge.py delete cases abc123...
  python debug_knowledge.py clear rules
  python debug_knowledge.py stats
"""
    console.print(help_text)


def main():
    if len(sys.argv) < 2:
        print_help()
        return
    
    cmd = sys.argv[1].lower()
    
    # 初始化知识库
    store = KnowledgeStore()
    
    if cmd == "list":
        print_all_knowledge(store)
    elif cmd == "search":
        if len(sys.argv) < 3:
            console.print("[red]请输入搜索词[/red]")
            return
        
        query = sys.argv[2]
        doc_type = None
        
        # 解析 --type 参数
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            if idx + 1 < len(sys.argv):
                t = sys.argv[idx + 1]
                if t in ["knowledge", "rules", "cases"]:
                    doc_type = t
        
        search_knowledge(store, query, doc_type=doc_type)
    elif cmd == "detail":
        if len(sys.argv) < 4:
            console.print("[red]请输入集合名和ID[/red]")
            return
        show_detail(store, sys.argv[2], sys.argv[3])
    elif cmd == "delete":
        if len(sys.argv) < 4:
            console.print("[red]请输入集合名和ID[/red]")
            return
        delete_knowledge(store, sys.argv[2], sys.argv[3])
    elif cmd == "clear":
        if len(sys.argv) < 3:
            console.print("[red]请输入集合名 (knowledge/rules/cases)[/red]")
            return
        if sys.argv[2] not in ["knowledge", "rules", "cases"]:
            console.print("[red]集合名必须是 knowledge/rules/cases[/red]")
            return
        clear_collection(store, sys.argv[2])
    elif cmd == "stats":
        show_stats(store)
    elif cmd == "help":
        print_help()
    else:
        console.print(f"[red]未知命令: {cmd}[/red]")
        print_help()


if __name__ == "__main__":
    main()
