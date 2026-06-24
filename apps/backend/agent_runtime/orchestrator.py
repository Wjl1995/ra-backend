from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.backend.agent_runtime.models import AgentTurnRequest, AgentTurnResponse
from apps.backend.agent_runtime.policy import AgentRuntimePolicy
from apps.backend.agent_runtime.tool_provider import ToolProvider
from apps.backend.agent_runtime.trace import AgentTrace


class AgentOrchestrator:
    """
    Phase 0 runtime skeleton.

    该类当前只负责统一运行时上下文、工具过滤和 legacy runner 包装，
    暂不接管线上 chat 主链路。
    """

    def __init__(
        self,
        tool_provider: ToolProvider,
        policy: AgentRuntimePolicy | None = None,
        legacy_runner: Callable[[AgentTurnRequest], AgentTurnResponse | dict[str, Any]] | None = None,
    ):
        self.tool_provider = tool_provider
        self.policy = policy or AgentRuntimePolicy()
        self.legacy_runner = legacy_runner

    def build_context(self, request: AgentTurnRequest) -> dict[str, Any]:
        context = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "document_id": request.document_id,
            "request_id": request.request_id,
        }
        context.update(request.context)
        return context

    def list_available_tools(self, request: AgentTurnRequest) -> list[dict[str, Any]]:
        tools = self.tool_provider.list_tools(context=self.build_context(request))
        filtered = self.policy.filter_tools(tools)
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "server_name": tool.server_name,
                "metadata": tool.metadata,
            }
            for tool in filtered
        ]

    def run_chat_turn(self, request: AgentTurnRequest) -> AgentTurnResponse:
        if self.legacy_runner is not None:
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

        trace = AgentTrace()
        available_tools = self.list_available_tools(request)
        raise NotImplementedError(
            "AgentOrchestrator Phase 0 skeleton is initialized, but no runtime execution path is wired yet. "
            f"Available tools: {[item['name'] for item in available_tools]}. "
            f"Trace seed: {trace.to_dict()}"
        )
