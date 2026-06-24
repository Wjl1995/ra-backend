from __future__ import annotations

import json

from knowledge.store import KnowledgeChunk, KnowledgeStore
from mcp_servers.shared import MCPPrompt, MCPResource, MCPTool, SimpleMCPServer


def build_server() -> SimpleMCPServer:
    store = KnowledgeStore()
    server = SimpleMCPServer(name="knowledge-mcp-server", version="0.1.0")

    def _format_results(results: list[dict], icon: str = "📄", limit: int = 300) -> str:
        if not results:
            return "未找到相关结果"
        lines = []
        for index, item in enumerate(results, start=1):
            meta = item["metadata"]
            lines.append(
                f"{icon} {index}. [{meta.get('title_path', meta.get('title', ''))}] "
                f"(来源: {meta.get('source', '未知')}, 相关度: {item['score']:.2f})\n"
                f"   {item['content'][:limit]}"
            )
        return "\n\n".join(lines)

    def search_knowledge(arguments: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        domain = str(arguments.get("domain") or "").strip() or None
        top_k = int(arguments.get("top_k") or 5)
        return _format_results(store.search_knowledge(query, domain=domain, top_k=top_k))

    def lookup_rule(arguments: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        domain = str(arguments.get("domain") or "").strip() or None
        top_k = int(arguments.get("top_k") or 5)
        return _format_results(store.search_rules(query, domain=domain, top_k=top_k), icon="📋")

    def retrieve_case(arguments: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        raw_tags = str(arguments.get("tags") or "").strip()
        tags = [item.strip() for item in raw_tags.split(",") if item.strip()] if raw_tags else None
        top_k = int(arguments.get("top_k") or 3)
        return _format_results(store.search_cases(query, tags=tags, top_k=top_k), icon="📌", limit=400)

    def save_experience(arguments: dict) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        scenario = str(arguments.get("scenario") or "").strip()
        outcome = str(arguments.get("outcome") or "").strip()
        raw_tags = str(arguments.get("tags") or "").strip()
        tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
        chunk = KnowledgeChunk(
            content=content,
            doc_type="case",
            domain="experience",
            tags=tags,
            title=f"经验: {scenario}" if scenario else "经验沉淀",
            title_path=f"经验库 > {scenario}" if scenario else "经验库",
            metadata={"scenario": scenario, "outcome": outcome},
        )
        chunk_id = store.add_chunk(chunk)
        return f"已保存到经验库 (id: {chunk_id})"

    def search_document_chunks(arguments: dict) -> str:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        domain = str(arguments.get("domain") or "").strip() or None
        top_k = int(arguments.get("top_k") or 5)
        doc_type = str(arguments.get("doc_type") or "knowledge").strip() or "knowledge"
        results = store.search(query, doc_type=doc_type, domain=domain, top_k=top_k)
        return _format_results(results, icon="🧩")

    def stats_resource() -> dict:
        return store.stats()

    def top_knowledge_resource() -> list[dict]:
        collection = store.collections["knowledge"]
        count = min(collection.count(), 10)
        if count <= 0:
            return []
        rows = collection.get(limit=count, include=["documents", "metadatas"])
        payload = []
        for chunk_id, document, metadata in zip(
            rows.get("ids", []),
            rows.get("documents", []),
            rows.get("metadatas", []),
        ):
            payload.append({"id": chunk_id, "content": document, "metadata": metadata})
        return payload

    def knowledge_summary_prompt(arguments: dict) -> dict:
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Knowledge summary helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请先检索知识库，再基于结果总结与下列问题相关的关键知识：{query}",
                    },
                }
            ],
        }

    server.register_tool(
        MCPTool(
            name="search_knowledge",
            description="搜索领域知识库，查找与问题相关的知识片段、FAQ、文档内容。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "domain": {"type": "string", "description": "限定领域"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
            handler=search_knowledge,
        )
    )
    server.register_tool(
        MCPTool(
            name="lookup_rule",
            description="查找业务规则、约束条件、审批流程、SOP规范。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "规则查询关键词"},
                    "domain": {"type": "string", "description": "限定领域"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
            handler=lookup_rule,
        )
    )
    server.register_tool(
        MCPTool(
            name="retrieve_case",
            description="检索历史案例和经验记录。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "案例场景描述"},
                    "tags": {"type": "string", "description": "标签，逗号分隔"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 3"},
                },
                "required": ["query"],
            },
            handler=retrieve_case,
        )
    )
    server.register_tool(
        MCPTool(
            name="save_experience",
            description="将任务执行经验沉淀到知识库。",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "经验内容"},
                    "scenario": {"type": "string", "description": "场景描述"},
                    "outcome": {"type": "string", "description": "结果 success/failure"},
                    "tags": {"type": "string", "description": "标签，逗号分隔"},
                },
                "required": ["content"],
            },
            handler=save_experience,
        )
    )
    server.register_tool(
        MCPTool(
            name="search_document_chunks",
            description="搜索知识片段，适合文档问答和知识定位。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "domain": {"type": "string", "description": "限定领域"},
                    "doc_type": {"type": "string", "description": "knowledge/rule/case"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
            handler=search_document_chunks,
        )
    )

    server.register_resource(
        MCPResource(
            uri="knowledge://stats",
            name="Knowledge Stats",
            description="知识库统计信息",
            mime_type="application/json",
            handler=stats_resource,
        )
    )
    server.register_resource(
        MCPResource(
            uri="knowledge://top-knowledge",
            name="Top Knowledge Chunks",
            description="知识库中的前若干条知识片段",
            mime_type="application/json",
            handler=top_knowledge_resource,
        )
    )

    server.register_prompt(
        MCPPrompt(
            name="knowledge_summary",
            description="让模型先检索知识库再总结的提示模板",
            arguments=[{"name": "query", "description": "待总结的问题", "required": True}],
            handler=knowledge_summary_prompt,
        )
    )

    return server


if __name__ == "__main__":
    build_server().serve_stdio()
