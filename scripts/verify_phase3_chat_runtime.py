from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
temp_root = Path(tempfile.mkdtemp(prefix="phase3-chat-", dir=str(workspace)))
db_path = temp_root / "phase3.sqlite3"
chroma_dir = temp_root / "chroma"
upload_dir = temp_root / "uploads"

os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)
os.environ["UPLOAD_DIR"] = str(upload_dir)
os.environ["AGENT_TOOL_MODE"] = "mcp"
os.environ["AGENT_MAX_TOOL_CALLS"] = "3"
os.environ["KIMI_API_KEY"] = "phase3-verify"
os.environ["KIMI_MODEL"] = "fake-kimi"

sys.path.insert(0, str(workspace))

from apps.backend.agent_runtime import MCPToolProvider
from apps.backend.database import Base, SessionLocal, engine
from apps.backend.models import ChatSession, Document, DocumentChunk, User
from apps.backend.services import chat_service
from knowledge.store import KnowledgeChunk, KnowledgeStore


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    content: str
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


class FakeCompletions:
    def create(self, *, messages, tools=None, **kwargs):  # noqa: ANN001
        del kwargs
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        if tool_messages:
            tool_text = tool_messages[-1]["content"]
            answer = f"根据检索结果，我的结论是：\n{tool_text}"
            return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=answer, tool_calls=None))])

        query = ""
        for item in reversed(messages):
            if item.get("role") == "user":
                query = str(item.get("content", ""))
                break

        if "规则" in query:
            tool_name = "lookup_rule"
            arguments = {"query": query, "top_k": 3}
        elif "知识" in query or "是什么" in query:
            tool_name = "search_knowledge"
            arguments = {"query": query, "top_k": 3}
        else:
            tool_name = "search_document_chunks"
            arguments = {"query": query, "top_k": 3}

        return FakeResponse(
            choices=[
                FakeChoice(
                    message=FakeMessage(
                        content="",
                        tool_calls=[
                            FakeToolCall(
                                id="call-1",
                                function=FakeFunction(
                                    name=tool_name,
                                    arguments=json.dumps(arguments, ensure_ascii=False),
                                ),
                            )
                        ],
                    )
                )
            ]
        )


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeOpenAIClient:
    def __init__(self):
        self.chat = FakeChat()


def seed_knowledge_store() -> None:
    store = KnowledgeStore(persist_dir=str(chroma_dir))
    store.add_chunk(
        KnowledgeChunk(
            content="退款规则：客户在 7 天内可申请退款，超过 7 天需人工审批。",
            doc_type="rule",
            domain="support",
            title="退款规则",
            title_path="规则库 > 退款规则",
            source="phase3-verify",
        )
    )
    store.add_chunk(
        KnowledgeChunk(
            content="产品知识：ReActAgent 是面向微信小程序的智能问答助手。",
            doc_type="knowledge",
            domain="product",
            title="产品介绍",
            title_path="知识库 > 产品介绍",
            source="phase3-verify",
        )
    )


def prepare_database() -> dict[str, int]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_knowledge_store()

    with SessionLocal() as db:
        user1 = User(openid="verify-user-1", nickname="u1", avatar="", daily_quota=50, daily_used=0)
        user2 = User(openid="verify-user-2", nickname="u2", avatar="", daily_quota=50, daily_used=0)
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        session_doc = ChatSession(user_id=user1.id, title="doc")
        session_rule = ChatSession(user_id=user1.id, title="rule")
        session_knowledge = ChatSession(user_id=user1.id, title="knowledge")
        db.add_all([session_doc, session_rule, session_knowledge])
        db.commit()
        db.refresh(session_doc)
        db.refresh(session_rule)
        db.refresh(session_knowledge)

        doc1 = Document(
            user_id=user1.id,
            title="用户一文档",
            domain="general",
            tags_json="[]",
            summary="这是一份只属于用户一的文档摘要，介绍 MCP Phase 3 接入。",
            status="ready",
            is_published=True,
            size=100,
            source_path="",
        )
        doc2 = Document(
            user_id=user2.id,
            title="用户二文档",
            domain="general",
            tags_json="[]",
            summary="这是一份属于用户二的敏感文档，不应该泄露。",
            status="ready",
            is_published=True,
            size=100,
            source_path="",
        )
        db.add_all([doc1, doc2])
        db.commit()
        db.refresh(doc1)
        db.refresh(doc2)

        db.add_all(
            [
                DocumentChunk(document_id=doc1.id, title="Phase3 摘要", content="Phase 3 将 chat_service 切换到 AgentOrchestrator，并保留 refs。"),
                DocumentChunk(document_id=doc1.id, title="用户隔离", content="只有当前用户自己的文档能被检索到。"),
                DocumentChunk(document_id=doc2.id, title="敏感信息", content="用户二的文档内容不应出现在用户一的回答中。"),
            ]
        )
        db.commit()

        return {
            "user1_id": user1.id,
            "session_doc_id": session_doc.id,
            "session_rule_id": session_rule.id,
            "session_knowledge_id": session_knowledge.id,
            "doc1_id": doc1.id,
        }


def run_chat_case(session_id: int, user_id: int, content: str, document_id: int | None = None) -> tuple[str, list[dict]]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise RuntimeError("verification user not found")
        chat_service.create_user_message(db, session_id, user, content)
        return chat_service.build_kimi_answer(db, session_id, user, document_id=document_id)


def main() -> int:
    try:
        ids = prepare_database()
        chat_service._client = FakeOpenAIClient()
        chat_service._orchestrator = None

        doc_answer, doc_refs = run_chat_case(
            session_id=ids["session_doc_id"],
            user_id=ids["user1_id"],
            content="请总结这份文档的主要内容",
            document_id=ids["doc1_id"],
        )
        rule_answer, rule_refs = run_chat_case(
            session_id=ids["session_rule_id"],
            user_id=ids["user1_id"],
            content="退款规则是什么？",
        )
        knowledge_answer, knowledge_refs = run_chat_case(
            session_id=ids["session_knowledge_id"],
            user_id=ids["user1_id"],
            content="ReActAgent 是什么知识产品？",
        )

        if "用户二" in doc_answer:
            raise RuntimeError("document answer leaked another user's content")
        if not doc_refs or any(item["document_id"] != ids["doc1_id"] for item in doc_refs):
            raise RuntimeError("document refs are missing or not scoped to the requested document")
        if "7 天" not in rule_answer and "退款" not in rule_answer:
            raise RuntimeError("rule question did not go through lookup_rule as expected")
        if "ReActAgent" not in knowledge_answer:
            raise RuntimeError("knowledge question did not go through search_knowledge as expected")

        payload = {
            "status": "ok",
            "temp_root": str(temp_root),
            "document_case": {"answer": doc_answer, "refs": doc_refs},
            "rule_case": {"answer": rule_answer, "refs": rule_refs},
            "knowledge_case": {"answer": knowledge_answer, "refs": knowledge_refs},
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    finally:
        orchestrator = chat_service._orchestrator
        if orchestrator is not None and isinstance(orchestrator.tool_provider, MCPToolProvider):
            asyncio.run(orchestrator.tool_provider.client_manager.stop())
        if hasattr(engine, "dispose"):
            engine.dispose()
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
