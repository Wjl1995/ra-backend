"""
orchestrator 冒烟测试（无 LLM / 无 DB 依赖）。

用一个假的 OpenAI client 驱动 AgentOrchestrator.run_chat_turn 走完
「首轮返回工具调用 → 执行工具 → 次轮返回最终回答」的完整链路，
验证清理 legacy_runner 之后核心运行时仍然可用。

用法: python scripts/smoke_orchestrator.py
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from apps.backend.agent_runtime import (
    AgentOrchestrator,
    AgentRuntimePolicy,
    AgentTurnRequest,
    LocalToolProvider,
)
from tools import ToolRegistry
from tools.tools import Tool


class _FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments: str) -> None:
        self.id = "call_1"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content: str, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message: _FakeMessage) -> None:
        self.message = message


class _FakeCompletion:
    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    def create(self, **_kwargs):
        return self._client._next_completion()


class _FakeChat:
    def __init__(self, client: "FakeClient") -> None:
        self.completions = _FakeCompletions(client)


class FakeClient:
    """第一次返回工具调用，第二次返回最终回答。"""

    def __init__(self) -> None:
        self.calls = 0
        self.chat = _FakeChat(self)

    def _next_completion(self):
        self.calls += 1
        if self.calls == 1:
            return _FakeCompletion(
                _FakeMessage("", [_FakeToolCall("get_current_time", "{}")])
            )
        return _FakeCompletion(_FakeMessage("当前时间已查到，回答完毕。", None))


def main() -> int:
    registry = ToolRegistry.create_default(memory=None, knowledge_store=None)
    provider = LocalToolProvider(registry)
    client = FakeClient()

    orchestrator = AgentOrchestrator(
        tool_provider=provider,
        llm_client=client,
        model="fake-model",
        max_tokens=256,
        temperature=1.0,
        policy=AgentRuntimePolicy(max_tool_calls=4),
    )

    request = AgentTurnRequest(user_id=1, session_id=1, query="现在几点了？")
    response = orchestrator.run_chat_turn(request)

    assert response.answer == "当前时间已查到，回答完毕。", response.answer
    assert len(response.tool_traces) == 1, response.tool_traces
    assert response.tool_traces[0]["tool"] == "get_current_time"
    assert response.tool_traces[0]["status"] == "ok"

    # 工具错误统一在 provider 层捕获：工具抛异常 → 结构化 is_error，不再靠字符串前缀
    def _boom(**kwargs):
        raise RuntimeError("boom")

    registry.register(
        Tool("boom_tool", "always fails", {"type": "object", "properties": {}}, _boom)
    )
    err_result = provider.call_tool("boom_tool", {})
    assert err_result.is_error is True, err_result
    assert "boom" in err_result.content, err_result.content
    ok_result = provider.call_tool("get_current_time", {})
    assert ok_result.is_error is False, ok_result

    print("SMOKE OK | answer=%r | tool_traces=%d | error_capture=%s"
          % (response.answer, len(response.tool_traces), err_result.is_error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
