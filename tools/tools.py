"""
Tools 模块 —— Agent 可调用的工具集

每个工具需提供：
- name: 工具名称
- description: 功能描述（供 LLM 理解何时调用）
- parameters: 参数 JSON Schema
- run: 执行函数
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable


class Tool:
    """工具基类"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters  # JSON Schema
        self.func = func

    def run(self, **kwargs) -> str:
        try:
            result = self.func(**kwargs)
            return str(result)
        except Exception as e:
            return f"[工具执行错误] {type(e).__name__}: {e}"

    def to_schema(self) -> dict:
        """返回 OpenAI function calling 格式的工具描述"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ─── 内置工具 ────────────────────────────────────────────────

def _calculator(expression: str) -> str:
    """安全计算数学表达式"""
    # 仅允许数学相关函数和运算符
    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "pow": pow, "log": math.log,
        "pi": math.pi, "e": math.e,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"{result}"
    except Exception as e:
        return f"计算错误: {e}"


def _get_current_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_format(text: str) -> str:
    """尝试格式化 JSON 文本"""
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError as e:
        return f"JSON 解析失败: {e}"


def _save_memory(content: str, tag: str = "general") -> str:
    """保存信息到长期记忆（运行时注入实例）"""
    # 这个函数会在注册时被替换为实际实现
    return "记忆功能尚未初始化"


def _search_memory(query: str) -> str:
    """搜索长期记忆（运行时注入实例）"""
    return "记忆功能尚未初始化"


# ─── 工具定义 ────────────────────────────────────────────────

TOOL_DEFINITIONS = {
    "calculator": Tool(
        name="calculator",
        description="计算数学表达式，支持加减乘除、三角函数、对数等。例如: '2+3*4', 'sqrt(16)', 'pi*5**2'",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式",
                },
            },
            "required": ["expression"],
        },
        func=_calculator,
    ),
    "get_current_time": Tool(
        name="get_current_time",
        description="获取当前日期和时间",
        parameters={
            "type": "object",
            "properties": {},
        },
        func=lambda: _get_current_time(),
    ),
    "json_format": Tool(
        name="json_format",
        description="格式化或验证 JSON 文本",
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "需要格式化的 JSON 字符串",
                },
            },
            "required": ["text"],
        },
        func=_json_format,
    ),
    "save_memory": Tool(
        name="save_memory",
        description="将重要信息保存到长期记忆中，以便将来回忆",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要保存的记忆内容",
                },
                "tag": {
                    "type": "string",
                    "description": "记忆分类标签，如 'fact', 'preference', 'task'",
                },
            },
            "required": ["content"],
        },
        func=_save_memory,
    ),
    "search_memory": Tool(
        name="search_memory",
        description="从长期记忆中搜索相关信息",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                },
            },
            "required": ["query"],
        },
        func=_search_memory,
    ),
    # ─── 知识库工具 ────────────────────────────────────────
    "search_knowledge": Tool(
        name="search_knowledge",
        description="搜索领域知识库，查找与问题相关的知识片段、FAQ、文档内容。当用户的问题涉及特定领域知识时使用。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询，描述你想查找的知识",
                },
                "domain": {
                    "type": "string",
                    "description": "限定领域，如 'marketing', 'product', 'tech'，留空搜索全部",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认5",
                },
            },
            "required": ["query"],
        },
        func=lambda query, domain="", top_k=5: "知识库尚未初始化",
    ),
    "lookup_rule": Tool(
        name="lookup_rule",
        description="查找业务规则、约束条件、审批流程、SOP规范。当需要确认某操作是否合规、某流程如何执行时使用。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "规则查询关键词或描述",
                },
                "domain": {
                    "type": "string",
                    "description": "限定领域，留空搜索全部",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认5",
                },
            },
            "required": ["query"],
        },
        func=lambda query, domain="", top_k=5: "规则库尚未初始化",
    ),
    "retrieve_case": Tool(
        name="retrieve_case",
        description="检索历史案例和经验记录，查找类似场景的处理方式。当面临开放性决策或需要参考过往做法时使用。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "案例场景描述或关键词",
                },
                "tags": {
                    "type": "string",
                    "description": "标签过滤，多个标签用逗号分隔，如 '营销,复盘'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认3",
                },
            },
            "required": ["query"],
        },
        func=lambda query, tags="", top_k=3: "案例库尚未初始化",
    ),
    "save_experience": Tool(
        name="save_experience",
        description="将任务执行经验沉淀到知识库，供将来参考。当完成了有价值的任务或发现了重要经验教训时使用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "经验内容描述",
                },
                "scenario": {
                    "type": "string",
                    "description": "场景描述，如 '活动策划', '用户投诉处理'",
                },
                "outcome": {
                    "type": "string",
                    "description": "结果：'success' 或 'failure'",
                },
                "tags": {
                    "type": "string",
                    "description": "标签，逗号分隔，如 '营销,复盘,教训'",
                },
            },
            "required": ["content"],
        },
        func=lambda content, scenario="", outcome="", tags="": "经验库尚未初始化",
    ),
}


class ToolRegistry:
    """工具注册中心 —— 支持动态注册和查找"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        return [t.to_schema() for t in self._tools.values()]

    def inject_memory(self, memory) -> None:
        """注入 AgentMemory 实例，使记忆工具可用"""
        def save(content: str, tag: str = "general") -> str:
            doc_id = memory.save_to_long_term(content, {"tag": tag})
            return f"已保存到长期记忆 (id: {doc_id})"

        def search(query: str) -> str:
            return memory.recall(query)

        self._tools["save_memory"].func = save
        self._tools["search_memory"].func = search

    def inject_knowledge(self, knowledge_store) -> None:
        """注入 KnowledgeStore 实例，使知识库工具可用"""

        def search_knowledge(query: str, domain: str = "", top_k: int = 5) -> str:
            results = knowledge_store.search_knowledge(
                query, domain=domain or None, top_k=top_k
            )
            if not results:
                return "未找到相关知识"
            lines = []
            for i, r in enumerate(results, 1):
                meta = r["metadata"]
                lines.append(
                    f"{i}. [{meta.get('title_path', meta.get('title', ''))}] "
                    f"(来源: {meta.get('source', '未知')}, 相关度: {r['score']:.2f})\n"
                    f"   {r['content'][:300]}"
                )
            return "\n\n".join(lines)

        def lookup_rule(query: str, domain: str = "", top_k: int = 5) -> str:
            results = knowledge_store.search_rules(
                query, domain=domain or None, top_k=top_k
            )
            if not results:
                return "未找到相关规则"
            lines = []
            for i, r in enumerate(results, 1):
                meta = r["metadata"]
                lines.append(
                    f"📋 规则 {i}: [{meta.get('title_path', '')}] "
                    f"(来源: {meta.get('source', '未知')}, 相关度: {r['score']:.2f})\n"
                    f"   {r['content'][:300]}"
                )
            return "\n\n".join(lines)

        def retrieve_case(query: str, tags: str = "", top_k: int = 3) -> str:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
            results = knowledge_store.search_cases(query, tags=tag_list, top_k=top_k)
            if not results:
                return "未找到相关案例"
            lines = []
            for i, r in enumerate(results, 1):
                meta = r["metadata"]
                lines.append(
                    f"📌 案例 {i}: [{meta.get('title_path', '')}] "
                    f"(标签: {meta.get('tags', '[]')}, 相关度: {r['score']:.2f})\n"
                    f"   {r['content'][:400]}"
                )
            return "\n\n".join(lines)

        def save_experience(
            content: str,
            scenario: str = "",
            outcome: str = "",
            tags: str = "",
        ) -> str:
            from knowledge.store import KnowledgeChunk
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
            chunk = KnowledgeChunk(
                content=content,
                doc_type="case",
                domain="experience",
                tags=tag_list,
                title=f"经验: {scenario}" if scenario else "经验沉淀",
                title_path=f"经验库 > {scenario}" if scenario else "经验库",
                metadata={"scenario": scenario, "outcome": outcome},
            )
            chunk_id = knowledge_store.add_chunk(chunk)
            return f"已保存到经验库 (id: {chunk_id})"

        self._tools["search_knowledge"].func = search_knowledge
        self._tools["lookup_rule"].func = lookup_rule
        self._tools["retrieve_case"].func = retrieve_case
        self._tools["save_experience"].func = save_experience

    @classmethod
    def create_default(cls, memory=None, knowledge_store=None) -> "ToolRegistry":
        """创建默认工具集"""
        registry = cls()
        for tool in TOOL_DEFINITIONS.values():
            registry.register(tool)
        if memory:
            registry.inject_memory(memory)
        if knowledge_store:
            registry.inject_knowledge(knowledge_store)
        return registry
