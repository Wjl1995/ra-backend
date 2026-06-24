from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    transport: str = "stdio"
    enabled: bool = True
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    timeout_seconds: float = 15.0
    env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class MCPServerRegistry:
    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}

    def register(self, config: MCPServerConfig) -> None:
        self._servers[config.name] = config

    def get(self, name: str | None) -> MCPServerConfig | None:
        if not name:
            return None
        return self._servers.get(name)

    def all(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    def enabled(self) -> list[MCPServerConfig]:
        return [server for server in self._servers.values() if server.enabled]

    @classmethod
    def from_mapping(cls, payload: dict[str, dict[str, Any]]) -> "MCPServerRegistry":
        registry = cls()
        for name, raw in payload.items():
            registry.register(
                MCPServerConfig(
                    name=name,
                    transport=str(raw.get("transport", "stdio")),
                    enabled=bool(raw.get("enabled", True)),
                    command=raw.get("command"),
                    args=tuple(raw.get("args", ())),
                    url=raw.get("url"),
                    timeout_seconds=float(raw.get("timeout_seconds", 15.0)),
                    env=dict(raw.get("env", {})),
                    metadata=dict(raw.get("metadata", {})),
                )
            )
        return registry
