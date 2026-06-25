from __future__ import annotations

import json

from sqlalchemy.orm import Session

from apps.backend.database import SessionLocal
from apps.backend.models import Document, DocumentChunk, User
from apps.backend.services import document_service, search_service
from knowledge.store import KnowledgeChunk, KnowledgeStore
from mcp_servers.shared import (
    MCPPrompt,
    MCPResource,
    MCPTool,
    SimpleMCPServer,
    parse_request_context,
    require_user_id,
)


def build_server() -> SimpleMCPServer:
    store = KnowledgeStore()
    server = SimpleMCPServer(name="knowledge-mcp-server", version="0.2.0")

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

    def _format_document_matches(matches: list[search_service.ChunkMatch]) -> tuple[str, list[dict]]:
        if not matches:
            return "未找到相关文档片段", []
        refs = []
        lines = []
        for index, match in enumerate(matches, start=1):
            lines.append(
                f"📄 {index}. [{match.chunk_title or match.document_title}] "
                f"(文档ID: {match.document_id}, 相关度: {match.score:.2f})\n"
                f"   {match.snippet}"
            )
            refs.append(
                {
                    "document_id": match.document_id,
                    "title": match.chunk_title or match.document_title,
                    "snippet": match.snippet,
                    "score": round(match.score, 4),
                }
            )
        return "\n\n".join(lines), refs

    def _build_tool_payload(text: str, refs: list[dict] | None = None) -> dict:
        refs = refs or []
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {"refs": refs},
            "refs": refs,
            "resourceRefs": [
                {
                    "uri": f"knowledge://document/{ref['document_id']}",
                    "title": ref["title"],
                    "document_id": ref["document_id"],
                }
                for ref in refs
            ],
            "metadata": {"refs_count": len(refs)},
            "isError": False,
        }

    def _get_user(db: Session, user_id: int) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError("User not found")
        return user

    def _get_document(db: Session, document_id: int, user_id: int) -> Document:
        document = (
            db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user_id)
            .first()
        )
        if document is None:
            raise ValueError("Document not found")
        return document

    def _resolve_document_id(arguments: dict, raw_context: dict) -> int | None:
        context = parse_request_context(raw_context)
        if context.document_id is not None:
            return context.document_id
        explicit = arguments.get("document_id")
        return int(explicit) if explicit not in (None, "") else None

    def search_knowledge(arguments: dict, raw_context: dict) -> str:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        domain = str(arguments.get("domain") or "").strip() or None
        top_k = int(arguments.get("top_k") or 5)
        return _format_results(store.search_knowledge(query, domain=domain, top_k=top_k))

    def lookup_rule(arguments: dict, raw_context: dict) -> str:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        domain = str(arguments.get("domain") or "").strip() or None
        top_k = int(arguments.get("top_k") or 5)
        return _format_results(store.search_rules(query, domain=domain, top_k=top_k), icon="📋")

    def retrieve_case(arguments: dict, raw_context: dict) -> str:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        raw_tags = str(arguments.get("tags") or "").strip()
        tags = [item.strip() for item in raw_tags.split(",") if item.strip()] if raw_tags else None
        top_k = int(arguments.get("top_k") or 3)
        return _format_results(store.search_cases(query, tags=tags, top_k=top_k), icon="📌", limit=400)

    def save_experience(arguments: dict, raw_context: dict) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")
        context = parse_request_context(raw_context)
        scenario = str(arguments.get("scenario") or "").strip()
        outcome = str(arguments.get("outcome") or "").strip()
        raw_tags = str(arguments.get("tags") or "").strip()
        tags = [item.strip() for item in raw_tags.split(",") if item.strip()]
        metadata = {
            "scenario": scenario,
            "outcome": outcome,
            "user_id": context.user_id,
            "session_id": context.session_id,
        }
        chunk = KnowledgeChunk(
            content=content,
            doc_type="case",
            domain="experience",
            tags=tags,
            title=f"经验: {scenario}" if scenario else "经验沉淀",
            title_path=f"经验库 > {scenario}" if scenario else "经验库",
            metadata={key: value for key, value in metadata.items() if value not in (None, "")},
        )
        chunk_id = store.add_chunk(chunk)
        return f"已保存到经验库 (id: {chunk_id})"

    def search_document_chunks(arguments: dict, raw_context: dict) -> dict:
        query = str(arguments.get("query") or "").strip()
        top_k = int(arguments.get("top_k") or 5)
        document_id = _resolve_document_id(arguments, raw_context)
        user_id = require_user_id(parse_request_context(raw_context))

        with SessionLocal() as db:
            user = _get_user(db, user_id)
            matches = search_service.retrieve_relevant_chunks(
                db,
                user=user,
                query=query,
                top_k=top_k,
                document_id=document_id,
                published_only=False,
            )
        text, refs = _format_document_matches(matches)
        return _build_tool_payload(text, refs)

    def search_documents(arguments: dict, raw_context: dict) -> dict:
        query = str(arguments.get("query") or "").strip()
        top_k = int(arguments.get("top_k") or 5)
        domain = str(arguments.get("domain") or "").strip() or None
        user_id = require_user_id(parse_request_context(raw_context))
        with SessionLocal() as db:
            user = _get_user(db, user_id)
            results = search_service.search_documents(
                db,
                user=user,
                query=query,
                top_k=top_k,
                domain=domain,
                published_only=False,
            )
        refs = [
            {
                "document_id": item.document_id,
                "title": item.title,
                "snippet": item.snippet,
                "score": round(item.score, 4),
            }
            for item in results
        ]
        if not refs:
            return _build_tool_payload("未找到相关文档")
        lines = []
        for index, item in enumerate(refs, start=1):
            lines.append(
                f"📚 {index}. [{item['title']}] (文档ID: {item['document_id']}, 相关度: {item['score']:.2f})\n"
                f"   {item['snippet']}"
            )
        return _build_tool_payload("\n\n".join(lines), refs)

    def get_document_summary(arguments: dict, raw_context: dict) -> dict:
        document_id = _resolve_document_id(arguments, raw_context)
        if document_id is None:
            raise ValueError("document_id is required")
        user_id = require_user_id(parse_request_context(raw_context))
        with SessionLocal() as db:
            _get_user(db, user_id)
            document = _get_document(db, document_id, user_id)
        summary = document.summary or "该文档暂无摘要。"
        refs = [
            {
                "document_id": document.id,
                "title": document.title,
                "snippet": summary[:160],
                "score": 1.0,
            }
        ]
        text = f"文档《{document.title}》摘要：\n{summary}"
        return _build_tool_payload(text, refs)

    def list_user_documents(arguments: dict, raw_context: dict) -> dict:
        top_k = int(arguments.get("top_k") or 10)
        domain = str(arguments.get("domain") or "").strip() or None
        user_id = require_user_id(parse_request_context(raw_context))
        with SessionLocal() as db:
            user = _get_user(db, user_id)
            docs = document_service.list_documents(db, user, domain=domain, published_only=False)
        if not docs:
            return _build_tool_payload("当前用户暂无可用文档")
        refs = [
            {
                "document_id": item.id,
                "title": item.title,
                "snippet": item.summary[:160] or "暂无摘要",
                "score": 1.0,
            }
            for item in docs[:top_k]
        ]
        lines = []
        for index, item in enumerate(docs[:top_k], start=1):
            lines.append(
                f"📁 {index}. [{item.title}] (文档ID: {item.id}, 状态: {item.status}, chunk数: {item.chunk_count})\n"
                f"   {item.summary[:160] or '暂无摘要'}"
            )
        return _build_tool_payload("\n\n".join(lines), refs)

    def stats_resource(arguments: dict, raw_context: dict) -> dict:
        del arguments
        context = parse_request_context(raw_context)
        stats = {"knowledge_store": store.stats()}
        if context.user_id is None:
            return stats
        with SessionLocal() as db:
            user = _get_user(db, context.user_id)
            docs = document_service.list_documents(db, user, published_only=False)
        stats["user_documents"] = {
            "count": len(docs),
            "ready_count": sum(1 for item in docs if item.status == "ready"),
        }
        return stats

    def document_resource(arguments: dict, raw_context: dict) -> dict:
        document_id = _resolve_document_id(arguments, raw_context)
        if document_id is None:
            raise ValueError("document_id is required")
        user_id = require_user_id(parse_request_context(raw_context))
        with SessionLocal() as db:
            _get_user(db, user_id)
            document = _get_document(db, document_id, user_id)
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.id.asc())
                .all()
            )
        return {
            "document": {
                "id": document.id,
                "title": document.title,
                "domain": document.domain,
                "summary": document.summary,
                "status": document.status,
                "is_published": document.is_published,
                "chunk_count": len(chunks),
                "created_at": document.created_at.isoformat() if document.created_at else None,
                "tags": json.loads(document.tags_json or "[]"),
            },
            "chunks": [
                {
                    "id": chunk.id,
                    "title": chunk.title,
                    "content": chunk.content,
                }
                for chunk in chunks
            ],
        }

    def document_outline_resource(arguments: dict, raw_context: dict) -> dict:
        document_id = _resolve_document_id(arguments, raw_context)
        if document_id is None:
            raise ValueError("document_id is required")
        user_id = require_user_id(parse_request_context(raw_context))
        with SessionLocal() as db:
            _get_user(db, user_id)
            document = _get_document(db, document_id, user_id)
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.id.asc())
                .all()
            )
        outline = [
            {
                "title": chunk.title or f"Section {index}",
                "summary": chunk.content[:160],
            }
            for index, chunk in enumerate(chunks, start=1)
            if chunk.content.strip()
        ]
        return {
            "document_id": document.id,
            "title": document.title,
            "outline": outline,
        }

    def knowledge_summary_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Knowledge summary helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请先检索知识库或相关文档，再基于结果总结与下列问题相关的关键信息：{query}",
                    },
                }
            ],
        }

    def document_summary_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
        document_id = arguments.get("document_id")
        return {
            "description": "Document summary helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请总结文档 document_id={document_id} 的核心内容，并重点关注标题、结构和结论。",
                    },
                }
            ],
        }

    def knowledge_qa_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Knowledge Q&A helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请先调用知识检索工具，再回答：{query}",
                    },
                }
            ],
        }

    def rule_audit_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Rule audit helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请先查规则与约束，再判断以下内容是否允许：{query}",
                    },
                }
            ],
        }

    def case_reference_prompt(arguments: dict, raw_context: dict) -> dict:
        del raw_context
        query = str(arguments.get("query") or "").strip()
        return {
            "description": "Case reference helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请检索历史案例，并总结与以下问题相似的处理经验：{query}",
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
            description="搜索当前用户可访问文档中的相关片段，适合文档问答与总结。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询，可为空以返回文档前几个片段"},
                    "document_id": {"type": "integer", "description": "限定单篇文档，可选"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
            },
            handler=search_document_chunks,
        )
    )
    server.register_tool(
        MCPTool(
            name="search_documents",
            description="搜索当前用户自己的文档列表，适合先定位文档再继续问答。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "domain": {"type": "string", "description": "限定领域"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
            handler=search_documents,
        )
    )
    server.register_tool(
        MCPTool(
            name="get_document_summary",
            description="获取当前用户某个文档的摘要，适合单文档总结和快速概览。",
            input_schema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer", "description": "文档 ID，可为空时使用上下文 document_id"},
                },
            },
            handler=get_document_summary,
        )
    )
    server.register_tool(
        MCPTool(
            name="list_user_documents",
            description="列出当前用户上传过的文档，帮助模型了解可访问资料范围。",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "限定领域"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 10"},
                },
            },
            handler=list_user_documents,
        )
    )

    server.register_resource(
        MCPResource(
            uri="knowledge://stats",
            name="Knowledge Stats",
            description="知识库与当前用户文档统计信息",
            mime_type="application/json",
            handler=stats_resource,
        )
    )
    server.register_resource(
        MCPResource(
            uri="knowledge://document/{document_id}",
            name="Knowledge Document",
            description="当前用户可访问的单篇文档详情",
            mime_type="application/json",
            handler=document_resource,
            templates=[
                {"name": "document", "description": "按 document_id 获取文档详情", "uriTemplate": "knowledge://document/{document_id}"}
            ],
        )
    )
    server.register_resource(
        MCPResource(
            uri="knowledge://document/{document_id}/outline",
            name="Knowledge Document Outline",
            description="当前用户可访问的单篇文档 outline",
            mime_type="application/json",
            handler=document_outline_resource,
            templates=[
                {"name": "outline", "description": "按 document_id 获取文档 outline", "uriTemplate": "knowledge://document/{document_id}/outline"}
            ],
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
    server.register_prompt(
        MCPPrompt(
            name="document_summary",
            description="单文档总结提示模板",
            arguments=[{"name": "document_id", "description": "文档 ID", "required": True}],
            handler=document_summary_prompt,
        )
    )
    server.register_prompt(
        MCPPrompt(
            name="knowledge_qa",
            description="知识问答提示模板",
            arguments=[{"name": "query", "description": "待回答的问题", "required": True}],
            handler=knowledge_qa_prompt,
        )
    )
    server.register_prompt(
        MCPPrompt(
            name="rule_audit",
            description="规则审查提示模板",
            arguments=[{"name": "query", "description": "待审查的问题", "required": True}],
            handler=rule_audit_prompt,
        )
    )
    server.register_prompt(
        MCPPrompt(
            name="case_reference",
            description="案例参考提示模板",
            arguments=[{"name": "query", "description": "待参考的问题", "required": True}],
            handler=case_reference_prompt,
        )
    )

    return server


if __name__ == "__main__":
    build_server().serve_stdio()
