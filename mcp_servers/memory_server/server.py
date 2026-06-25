from __future__ import annotations

import json

from memory import AgentMemory
from mcp_servers.shared import (
    MCPPrompt,
    MCPResource,
    MCPTool,
    SimpleMCPServer,
    parse_request_context,
)


def build_server() -> SimpleMCPServer:
    memory = AgentMemory()
    server = SimpleMCPServer(name="memory-mcp-server", version="0.1.0")

    def save_memory(arguments: dict, raw_context: dict) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        tag = str(arguments.get("tag") or "general")
        context = parse_request_context(raw_context)
        metadata = {"tag": tag}
        if context.user_id is not None:
            metadata["user_id"] = context.user_id
        if context.session_id is not None:
            metadata["session_id"] = context.session_id
        if context.request_id is not None:
            metadata["request_id"] = context.request_id
        doc_id = memory.save_to_long_term(content, metadata)
        return f"已保存到长期记忆 (id: {doc_id})"

    def search_memory(arguments: dict, raw_context: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        top_k = int(arguments.get("top_k") or 5)
        context = parse_request_context(raw_context)
        results = memory.long_term.search(query, top_k=max(top_k * 3, top_k))
        if context.user_id is not None:
            results = [
                item for item in results
                if str(item["metadata"].get("user_id", "")) == str(context.user_id)
            ]
        if not results:
            return "（无相关长期记忆）"
        lines = []
        for index, item in enumerate(results[:top_k], start=1):
            ts = item["metadata"].get("timestamp", "unknown")
            lines.append(
                f"  {index}. [{ts}] {item['text']} (相似度: {1 - item['distance']:.2f})"
            )
        return "\n".join(lines)

    def stats_resource(arguments: dict, raw_context: dict) -> dict:
        del arguments
        context = parse_request_context(raw_context)
        if context.user_id is None:
            return {"count": memory.long_term.count()}
        results = memory.long_term.collection.get(include=["metadatas"])
        count = 0
        for metadata in results.get("metadatas", []):
            if str(metadata.get("user_id", "")) == str(context.user_id):
                count += 1
        return {"count": count, "user_id": context.user_id}

    def recent_resource(arguments: dict, raw_context: dict) -> list[dict]:
        context = parse_request_context(raw_context)
        collection = memory.long_term.collection
        limit = min(int(arguments.get("limit") or 10), 20, collection.count())
        if limit <= 0:
            return []
        rows = collection.get(limit=limit, include=["documents", "metadatas"])
        documents = rows.get("documents", [])
        metadatas = rows.get("metadatas", [])
        ids = rows.get("ids", [])
        items = []
        for item_id, document, metadata in zip(ids, documents, metadatas):
            if context.user_id is not None and str(metadata.get("user_id", "")) != str(context.user_id):
                continue
            items.append({"id": item_id, "text": document, "metadata": metadata})
        items.sort(key=lambda item: item["metadata"].get("timestamp", ""), reverse=True)
        return items

    def user_recent_resource(arguments: dict, raw_context: dict) -> list[dict]:
        context = parse_request_context(raw_context)
        if context.user_id is None:
            return []
        limit = min(int(arguments.get("limit") or 5), 10)
        rows = memory.long_term.collection.get(include=["documents", "metadatas"])
        documents = rows.get("documents", [])
        metadatas = rows.get("metadatas", [])
        ids = rows.get("ids", [])
        items = []
        for item_id, document, metadata in zip(ids, documents, metadatas):
            if str(metadata.get("user_id", "")) != str(context.user_id):
                continue
            items.append({"id": item_id, "text": document, "metadata": metadata})
        items.sort(key=lambda item: item["metadata"].get("timestamp", ""), reverse=True)
        return items[:limit]

    def memory_recall_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
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
    server.register_resource(
        MCPResource(
            uri="memory://user/{user_id}/recent",
            name="User Recent Memories",
            description="当前用户最近写入的长期记忆",
            mime_type="application/json",
            handler=user_recent_resource,
            templates=[
                {
                    "name": "recent",
                    "description": "当前用户最近写入的长期记忆",
                    "uriTemplate": "memory://user/{user_id}/recent",
                }
            ],
        )
    )

    server.register_prompt(
        MCPPrompt(
            name="memory_recall",
            description="帮助模型回忆长期记忆的提示模板",
            arguments=[{"name": "query", "description": "需要回忆的查询", "required": True}],
            handler=memory_recall_prompt,
        )
    )

    return server


if __name__ == "__main__":
    build_server().serve_stdio()
