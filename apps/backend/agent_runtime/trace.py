from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolTrace:
    tool: str
    server: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    duration_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentTrace:
    tool_traces: list[ToolTrace] = field(default_factory=list)
    resource_refs: list[dict[str, Any]] = field(default_factory=list)

    def add_tool_trace(self, trace: ToolTrace) -> None:
        self.tool_traces.append(trace)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_traces": [trace.to_dict() for trace in self.tool_traces],
            "resource_refs": list(self.resource_refs),
        }
