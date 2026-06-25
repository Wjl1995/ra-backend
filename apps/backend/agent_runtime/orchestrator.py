from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from apps.backend.agent_runtime.models import AgentTurnRequest, AgentTurnResponse, ToolDescriptor
from apps.backend.agent_runtime.policy import AgentRuntimePolicy
from apps.backend.agent_runtime.tool_provider import ToolProvider
from apps.backend.agent_runtime.trace import AgentTrace, ToolTrace


DEFAULT_SYSTEM_PROMPT = """你是 ReActAgent，服务于微信小程序用户。

请优先使用可用工具来回答问题，尤其是：
1. 文档总结、文档问答、引用原文时，优先调用文档/知识检索工具。
2. 规则、流程、是否允许等问题，优先调用规则或知识检索工具。
3. 当上下文里带有单文档 document_id 时，只能围绕该文档或当前用户可访问文档回答。

回答要求：
1. 默认用中文，简洁清晰。
2. 如果工具结果不足，请明确说明不确定性。
3. 尽量引用检索到的文档片段，不要编造不存在的内容。
"""


class AgentOrchestrator:
    """
    Phase 3 online runtime.

    负责把 chat_service 的主链路切到统一 ToolProvider / MCP Runtime，
    并保留 legacy runner 作为显式回退模式。
    """

    def __init__(
        self,
        tool_provider: ToolProvider,
        *,
        llm_client: OpenAI | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 1.0,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        policy: AgentRuntimePolicy | None = None,
        legacy_runner: Callable[[AgentTurnRequest], AgentTurnResponse | dict[str, Any]] | None = None,
    ):
        self.tool_provider = tool_provider
        self.llm_client = llm_client
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.policy = policy or AgentRuntimePolicy()
        self.legacy_runner = legacy_runner

    def build_context(self, request: AgentTurnRequest) -> dict[str, Any]:
        context = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "document_id": request.document_id,
            "request_id": request.request_id or f"agent-turn-{uuid.uuid4().hex[:10]}",
        }
        context.update(request.context)
        return context

    def list_available_tools(self, request: AgentTurnRequest) -> list[ToolDescriptor]:
        tools = self.tool_provider.list_tools(context=self.build_context(request))
        return self.policy.filter_tools(tools)

    def run_chat_turn(self, request: AgentTurnRequest) -> AgentTurnResponse:
        if self.llm_client is None or self.model is None:
            if self.legacy_runner is None:
                raise RuntimeError("AgentOrchestrator is missing llm_client/model and no legacy_runner is configured")
            return self._run_legacy(request)

        context = self.build_context(request)
        trace = AgentTrace()
        available_tools = self.list_available_tools(request)
        available_resources = self.tool_provider.list_resources(context=context)
        available_prompts = self.tool_provider.list_prompts(context=context)
        messages = self._build_messages(
            request=request,
            context=context,
            tools=available_tools,
            resources=available_resources,
            prompts=available_prompts,
        )

        openai_tools = [self._tool_to_openai_schema(item) for item in available_tools]
        collected_refs = list(context.get("initial_refs", []))

        for _ in range(max(self.policy.max_tool_calls, 1) + 1):
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools or None,
                tool_choice="auto" if openai_tools else None,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            assistant_content = self._message_text(message)

            if not tool_calls:
                answer = assistant_content.strip()
                if not answer and self.legacy_runner is not None:
                    return self._run_legacy(request)
                if not answer:
                    raise RuntimeError("Agent runtime returned an empty response")
                return AgentTurnResponse(
                    answer=answer,
                    refs=collected_refs,
                    tool_traces=[item.to_dict() for item in trace.tool_traces],
                    resource_refs=list(trace.resource_refs),
                    metadata={
                        "runtime_mode": "agent",
                        "tool_count": len(available_tools),
                    },
                )

            messages.append(self._assistant_tool_call_message(message, assistant_content))
            for tool_call in tool_calls[: self.policy.max_tool_calls]:
                tool_trace = ToolTrace(
                    tool=tool_call.function.name,
                    arguments=self._parse_tool_arguments(tool_call.function.arguments),
                    status="pending",
                )
                started = time.perf_counter()
                result = self.tool_provider.call_tool(
                    tool_call.function.name,
                    tool_trace.arguments,
                    context=context,
                )
                tool_trace.server = result.server_name
                tool_trace.duration_ms = int((time.perf_counter() - started) * 1000)
                tool_trace.status = "error" if result.is_error else "ok"
                tool_trace.error = result.content if result.is_error else None
                tool_trace.metadata = dict(result.metadata)
                trace.add_tool_trace(tool_trace)

                refs = list(result.metadata.get("refs", []))
                if refs:
                    collected_refs = self._merge_refs(collected_refs, refs)
                for item in result.metadata.get("resource_refs", []):
                    trace.resource_refs.append(item)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content,
                    }
                )

        raise RuntimeError("Agent runtime exceeded max tool-call iterations")

    def _run_legacy(self, request: AgentTurnRequest) -> AgentTurnResponse:
        if self.legacy_runner is None:
            raise RuntimeError("legacy_runner is not configured")
        payload = self.legacy_runner(request)
        if isinstance(payload, AgentTurnResponse):
            return payload
        return AgentTurnResponse(
            answer=str(payload.get("answer", "")),
            refs=list(payload.get("refs", [])),
            tool_traces=list(payload.get("tool_traces", [])),
            resource_refs=list(payload.get("resource_refs", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def _build_messages(
        self,
        *,
        request: AgentTurnRequest,
        context: dict[str, Any],
        tools: list[ToolDescriptor],
        resources: list[Any],
        prompts: list[Any],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._build_system_prompt(context, tools, resources, prompts)}]

        document_context = self._build_document_context(list(context.get("initial_refs", [])))
        if document_context:
            messages.append({"role": "system", "content": document_context})

        history = list(context.get("history_messages", []))
        if history:
            messages.extend(history)
        else:
            messages.append({"role": "user", "content": request.query})
        return messages

    def _build_system_prompt(
        self,
        context: dict[str, Any],
        tools: list[ToolDescriptor],
        resources: list[Any],
        prompts: list[Any],
    ) -> str:
        lines = [self.system_prompt]
        if context.get("document_id") is not None:
            lines.append(
                f"当前对话绑定单文档 document_id={context['document_id']}，请优先围绕该文档回答。"
            )
        if tools:
            lines.append("可用工具：" + ", ".join(tool.name for tool in tools))
        if resources:
            lines.append("可用资源：" + ", ".join(item.uri for item in resources))
        if prompts:
            lines.append("可用提示模板：" + ", ".join(item.name for item in prompts))
        return "\n".join(lines)

    @staticmethod
    def _tool_to_openai_schema(tool: ToolDescriptor) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _build_document_context(refs: list[dict[str, Any]]) -> str:
        if not refs:
            return ""
        lines = [
            "以下是当前检索到的文档片段，请优先参考它们并在不充分时说明不确定：",
        ]
        for index, ref in enumerate(refs, start=1):
            lines.append(
                f"[Snippet {index}] Document {ref['document_id']} - {ref['title']}\n{ref['snippet']}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _assistant_tool_call_message(message: Any, content: str) -> dict[str, Any]:
        tool_calls = []
        for item in list(getattr(message, "tool_calls", None) or []):
            tool_calls.append(
                {
                    "id": item.id,
                    "type": "function",
                    "function": {
                        "name": item.function.name,
                        "arguments": item.function.arguments,
                    },
                }
            )
        return {
            "role": "assistant",
            "content": content or "",
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _parse_tool_arguments(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Tool arguments are not valid JSON: {raw}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Tool arguments must be a JSON object")
        return payload

    @staticmethod
    def _message_text(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    text_value = getattr(item, "text", None)
                    if text_value:
                        parts.append(str(text_value))
            return "".join(parts)
        return str(content or "")

    @staticmethod
    def _merge_refs(existing: list[dict], incoming: list[dict]) -> list[dict]:
        merged: dict[tuple[int, str, str], dict] = {}
        for item in existing + incoming:
            key = (
                int(item.get("document_id", 0)),
                str(item.get("title", "")),
                str(item.get("snippet", "")),
            )
            previous = merged.get(key)
            if previous is None or float(item.get("score", 0)) > float(previous.get("score", 0)):
                merged[key] = item
        return list(merged.values())
