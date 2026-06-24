from __future__ import annotations

import json
import os
import sys

from apps.backend.mcp.exceptions import MCPConfigurationError
from apps.backend.mcp.server_registry import MCPServerRegistry


def build_default_stdio_registry() -> MCPServerRegistry:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    python_executable = sys.executable
    return MCPServerRegistry.from_mapping(
        {
            "memory": {
                "transport": "stdio",
                "command": python_executable,
                "args": ["-m", "mcp_servers.memory_server.server"],
                "metadata": {"cwd": repo_root},
            },
            "knowledge": {
                "transport": "stdio",
                "command": python_executable,
                "args": ["-m", "mcp_servers.knowledge_server.server"],
                "metadata": {"cwd": repo_root},
            },
            "utility": {
                "transport": "stdio",
                "command": python_executable,
                "args": ["-m", "mcp_servers.utility_server.server"],
                "metadata": {"cwd": repo_root},
            },
        }
    )


def load_registry_from_json(raw_json: str) -> MCPServerRegistry:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise MCPConfigurationError("MCP_SERVER_CONFIG_JSON is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise MCPConfigurationError("MCP_SERVER_CONFIG_JSON must be a JSON object")

    return MCPServerRegistry.from_mapping(payload)
