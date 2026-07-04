from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.agent_runtime.models import ToolDescriptor


@dataclass(slots=True)
class AgentRuntimePolicy:
    enabled_tool_names: set[str] | None = None
    blocked_tool_names: set[str] = field(default_factory=set)
    max_tool_calls: int = 4

    def filter_tools(self, tools: list[ToolDescriptor]) -> list[ToolDescriptor]:
        filtered = []
        for tool in tools:
            if tool.name in self.blocked_tool_names:
                continue
            if self.enabled_tool_names is not None and tool.name not in self.enabled_tool_names:
                continue
            filtered.append(tool)
        return filtered
