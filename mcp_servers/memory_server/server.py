from __future__ import annotations

from memory import AgentMemory
from mcp_servers.shared import MCPPrompt, MCPResource, MCPTool, SimpleMCPServer


def build_server() -> SimpleMCPServer:
    memory = AgentMemory()
    server = SimpleMCPServer(name="memory-mcp-server", version="0.1.0")

    def save_memory(arguments: dict) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        tag = str(arguments.get("tag") or "general")
        doc_id = memory.save_to_long_term(content, {"tag": tag})
        return f"已保存到长期记忆 (id: {doc_id})"

    def search_memory(arguments: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        top_k = int(arguments.get("top_k") or 5)
        return memory.recall(query, top_k=top_k)

    def stats_resource() -> dict:
        return {"count": memory.long_term.count()}

    def recent_resource() -> list[dict]:
        collection = memory.long_term.collection
        limit = min(collection.count(), 10)
        if limit <= 0:
            return []
        rows = collection.get(limit=limit, include=["documents", "metadatas"])
        documents = rows.get("documents", [])
        metadatas = rows.get("metadatas", [])
        ids = rows.get("ids", [])
        items = []
        for item_id, document, metadata in zip(ids, documents, metadatas):
            items.append({"id": item_id, "text": document, "metadata": metadata})
        items.sort(key=lambda item: item["metadata"].get("timestamp", ""), reverse=True)
        return items

    def memory_search_prompt(arguments: dict) -> dict:
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Memory recall helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请回忆与以下问题相关的长期记忆，并基于结果总结：{query}",
                    },
                }
            ],
        }

    server.register_tool(
        MCPTool(
            name="save_memory",
            description="将重要信息保存到长期记忆中，以便将来回忆",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要保存的记忆内容"},
                    "tag": {"type": "string", "description": "记忆标签"},
                },
                "required": ["content"],
            },
            handler=save_memory,
        )
    )
    server.register_tool(
        MCPTool(
            name="search_memory",
            description="从长期记忆中搜索相关信息",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
            handler=search_memory,
        )
    )

    server.register_resource(
        MCPResource(
            uri="memory://stats",
            name="Memory Stats",
            description="长期记忆统计信息",
            mime_type="application/json",
            handler=stats_resource,
        )
    )
    server.register_resource(
        MCPResource(
            uri="memory://recent",
            name="Recent Memories",
            description="最近写入的长期记忆",
            mime_type="application/json",
            handler=recent_resource,
        )
    )

    server.register_prompt(
        MCPPrompt(
            name="memory_recall",
            description="帮助模型回忆长期记忆的提示模板",
            arguments=[{"name": "query", "description": "需要回忆的查询", "required": True}],
            handler=memory_search_prompt,
        )
    )

    return server


if __name__ == "__main__":
    build_server().serve_stdio()
