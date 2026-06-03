#!/usr/bin/env python3
"""
记忆系统调试脚本
用于查看、搜索、添加、删除长期记忆
"""
import sys
sys.path.insert(0, ".")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from memory import AgentMemory, LongTermMemory

console = Console()


def print_all_memories(ltm):
    """打印所有长期记忆"""
    all_data = ltm.collection.get()
    
    if not all_data['ids']:
        console.print("[yellow]没有找到任何记忆[/yellow]")
        return
    
    table = Table(title="📚 所有长期记忆")
    table.add_column("ID", style="cyan")
    table.add_column("内容", style="white")
    table.add_column("标签", style="green")
    table.add_column("时间", style="dim")
    
    for idx, doc_id in enumerate(all_data['ids']):
        text = all_data['documents'][idx]
        meta = all_data['metadatas'][idx]
        tag = meta.get('tag', 'N/A')
        timestamp = meta.get('timestamp', 'N/A')
        # 显示完整ID，文本截断到200字符
        display_text = text[:200] + "..." if len(text) > 200 else text
        table.add_row(doc_id, display_text, tag, timestamp[:19] if timestamp else 'N/A')
    
    console.print(table)


def search_memories(ltm, query, top_k=5):
    """搜索记忆"""
    results = ltm.search(query, top_k=top_k)
    
    if not results:
        console.print(f"[yellow]没有找到与 '{query}' 相关的记忆[/yellow]")
        return
    
    table = Table(title=f"🔍 搜索结果: '{query}'")
    table.add_column("排名", style="cyan")
    table.add_column("内容", style="white")
    table.add_column("标签", style="green")
    table.add_column("相似度", style="magenta")
    
    for i, r in enumerate(results, 1):
        similarity = 1 - r['distance']
        tag = r['metadata'].get('tag', 'N/A')
        table.add_row(str(i), r['text'], tag, f"{similarity:.2%}")
    
    console.print(table)


def add_memory(ltm, content, tag="general"):
    """添加记忆"""
    doc_id = ltm.add(content, metadata={"tag": tag})
    console.print(f"[green]✅ 记忆已添加[/green] (ID: {doc_id})")


def delete_memory(ltm, doc_id):
    """删除记忆"""
    try:
        ltm.delete(doc_id)
        console.print(f"[green]✅ 记忆已删除[/green] (ID: {doc_id})")
    except Exception as e:
        console.print(f"[red]❌ 删除失败: {e}[/red]")


def clear_all_memories(ltm):
    """清空所有记忆"""
    confirm = console.input("[red]确定要清空所有记忆吗？输入 YES 确认: [/red]")
    if confirm == "YES":
        all_ids = ltm.collection.get()['ids']
        if all_ids:
            ltm.collection.delete(ids=all_ids)
            console.print(f"[green]✅ 已清空 {len(all_ids)} 条记忆[/green]")
        else:
            console.print("[yellow]没有记忆需要清空[/yellow]")
    else:
        console.print("[yellow]已取消[/yellow]")


def delete_by_type(ltm, msg_type):
    """按类型删除记忆：user_message 或 assistant_message"""
    all_data = ltm.collection.get()
    ids_to_delete = []
    
    for idx, doc_id in enumerate(all_data['ids']):
        meta = all_data['metadatas'][idx]
        if meta.get('type') == msg_type:
            ids_to_delete.append(doc_id)
    
    if not ids_to_delete:
        console.print(f"[yellow]没有找到类型为 '{msg_type}' 的记忆[/yellow]")
        return
    
    confirm = console.input(f"[red]确定要删除 {len(ids_to_delete)} 条类型为 '{msg_type}' 的记忆吗？输入 YES 确认: [/red]")
    if confirm == "YES":
        ltm.collection.delete(ids=ids_to_delete)
        console.print(f"[green]✅ 已删除 {len(ids_to_delete)} 条记忆[/green]")
    else:
        console.print("[yellow]已取消[/yellow]")


def show_stats(ltm):
    """显示统计信息"""
    count = ltm.count()
    console.print(Panel(f"📊 记忆统计\n\n总数: {count} 条", title="统计信息"))


def print_help():
    """打印帮助信息"""
    help_text = """
[bold]记忆调试脚本[/bold]

[cyan]用法:[/cyan]
  python debug_memory.py [命令] [参数...]

[cyan]命令:[/cyan]
  list                    列出所有记忆
  search <query>          搜索相关记忆
  add <content> [tag]     添加新记忆
  delete <id>             删除指定ID的记忆
  delete-type <type>      按类型删除：user_message 或 assistant_message
  clear                   清空所有记忆
  stats                   显示统计信息
  help                    显示帮助

[cyan]示例:[/cyan]
  python debug_memory.py list
  python debug_memory.py search "圆的面积"
  python debug_memory.py add "今天学习了Python" "learning"
  python debug_memory.py delete abc123...
  python debug_memory.py stats
"""
    console.print(help_text)


def main():
    if len(sys.argv) < 2:
        print_help()
        return
    
    cmd = sys.argv[1].lower()
    
    # 初始化记忆
    ltm = LongTermMemory()
    
    if cmd == "list":
        print_all_memories(ltm)
    elif cmd == "search":
        if len(sys.argv) < 3:
            console.print("[red]请输入搜索词[/red]")
            return
        query = " ".join(sys.argv[2:])
        search_memories(ltm, query)
    elif cmd == "add":
        if len(sys.argv) < 3:
            console.print("[red]请输入记忆内容[/red]")
            return
        content = sys.argv[2]
        tag = sys.argv[3] if len(sys.argv) > 3 else "general"
        add_memory(ltm, content, tag)
    elif cmd == "delete":
        if len(sys.argv) < 3:
            console.print("[red]请输入记忆ID[/red]")
            return
        delete_memory(ltm, sys.argv[2])
    elif cmd == "delete-type":
        if len(sys.argv) < 3:
            console.print("[red]请输入类型：user_message 或 assistant_message[/red]")
            return
        delete_by_type(ltm, sys.argv[2])
    elif cmd == "clear":
        clear_all_memories(ltm)
    elif cmd == "stats":
        show_stats(ltm)
    elif cmd == "help":
        print_help()
    else:
        console.print(f"[red]未知命令: {cmd}[/red]")
        print_help()


if __name__ == "__main__":
    main()
