from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from apps.backend.agent_runtime.models import (
    PromptDescriptor,
    PromptRenderResult,
    ResourceDescriptor,
    ResourceReadResult,
    ToolCallResult,
    ToolDescriptor,
)
from apps.backend.mcp.client_manager import MCPClientManager
from tools import ToolRegistry


class ToolProvider(ABC):
    @abstractmethod
    def list_tools(self, context: dict[str, Any] | None = None) -> list[ToolDescriptor]:
        raise NotImplementedError

    @abstractmethod
    def call_tool(
        self,
        tool_name: str,
        arguments: Any = None,
        context: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        raise NotImplementedError

    def list_resources(self, context: dict[str, Any] | None = None) -> list[ResourceDescriptor]:
        return []

    def read_resource(
        self,
        uri: str,
        context: dict[str, Any] | None = None,
    ) -> ResourceReadResult:
        raise NotImplementedError(f"Resource '{uri}' is not supported by this provider")

    def list_prompts(self, context: dict[str, Any] | None = None) -> list[PromptDescriptor]:
        return []

    def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PromptRenderResult:
        raise NotImplementedError(f"Prompt '{name}' is not supported by this provider")


class LocalToolProvider(ToolProvider):
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def list_tools(self, context: dict[str, Any] | None = None) -> list[ToolDescriptor]:
        del context
        return [
            ToolDescriptor(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                server_name="local",
            )
            for tool in self.registry.all_tools()
        ]

    def call_tool(
        self,
        tool_name: str,
        arguments: Any = None,
        context: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        del context
        tool = self.registry.get(tool_name)
        if tool is None:
            available = [item.name for item in self.registry.all_tools()]
            return ToolCallResult(
                tool_name=tool_name,
                server_name="local",
                content=f"错误: 未找到工具 '{tool_name}'，可用工具: {available}",
                is_error=True,
            )

        kwargs = self._coerce_arguments(tool.parameters, arguments)
        result = tool.run(**kwargs)
        is_error = result.startswith("[工具执行错误]") or result.startswith("错误:")
        return ToolCallResult(
            tool_name=tool_name,
            server_name="local",
            content=result,
            is_error=is_error,
            raw=result,
            metadata={"arguments": kwargs},
        )

    @staticmethod
    def _coerce_arguments(parameters: dict[str, Any], arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            if arguments:
                required = parameters.get("required", [])
                if required:
                    return {required[0]: arguments}
            return {}
        if arguments is None:
            return {}
        return {"input": arguments}


class MCPToolProvider(ToolProvider):
    def __init__(
        self,
        client_manager: MCPClientManager,
        default_server: str | None = None,
    ):
        self.client_manager = client_manager
        self.default_server = default_server

    def list_tools(self, context: dict[str, Any] | None = None) -> list[ToolDescriptor]:
        raw_tools = self._run(self.client_manager.list_tools(server=self.default_server, context=context))
        return [
            ToolDescriptor(
                name=item.get("name", ""),
                description=item.get("description", ""),
                parameters=item.get("parameters", {}),
                server_name=item.get("server_name") or self.default_server,
                metadata=item.get("metadata", {}),
            )
            for item in raw_tools
        ]

    def call_tool(
        self,
        tool_name: str,
        arguments: Any = None,
        context: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        try:
            payload_arguments = arguments if isinstance(arguments, dict) else {}
            if not isinstance(arguments, dict) and arguments is not None:
                payload_arguments = {"input": arguments}
            payload = self._run(
                self.client_manager.call_tool(
                    server=self.default_server,
                    tool=tool_name,
                    arguments=payload_arguments,
                    context=context,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return ToolCallResult(
                tool_name=tool_name,
                server_name=self.default_server,
                content=f"[MCP工具执行错误] {type(exc).__name__}: {exc}",
                is_error=True,
                raw=exc,
            )

        return ToolCallResult(
            tool_name=tool_name,
            server_name=payload.get("server_name") or self.default_server,
            content=str(payload.get("content", "")),
            is_error=bool(payload.get("is_error", False)),
            raw=payload,
            metadata=payload.get("metadata", {}),
        )

    def list_resources(self, context: dict[str, Any] | None = None) -> list[ResourceDescriptor]:
        raw_resources = self._run(self.client_manager.list_resources(server=self.default_server, context=context))
        return [
            ResourceDescriptor(
                uri=item.get("uri", ""),
                name=item.get("name", item.get("uri", "")),
                description=item.get("description", ""),
                mime_type=item.get("mime_type"),
                server_name=item.get("server_name") or self.default_server,
                metadata=item.get("metadata", {}),
            )
            for item in raw_resources
        ]

    def read_resource(
        self,
        uri: str,
        context: dict[str, Any] | None = None,
    ) -> ResourceReadResult:
        payload = self._run(self.client_manager.read_resource(self.default_server, uri, context=context))
        return ResourceReadResult(
            uri=payload.get("uri", uri),
            content=payload.get("content"),
            mime_type=payload.get("mime_type"),
            server_name=payload.get("server_name") or self.default_server,
            metadata=payload.get("metadata", {}),
        )

    def list_prompts(self, context: dict[str, Any] | None = None) -> list[PromptDescriptor]:
        raw_prompts = self._run(self.client_manager.list_prompts(server=self.default_server, context=context))
        return [
            PromptDescriptor(
                name=item.get("name", ""),
                description=item.get("description", ""),
                arguments_schema=item.get("arguments_schema", {}),
                server_name=item.get("server_name") or self.default_server,
                metadata=item.get("metadata", {}),
            )
            for item in raw_prompts
        ]

    def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PromptRenderResult:
        payload = self._run(
            self.client_manager.get_prompt(
                server=self.default_server,
                name=name,
                arguments=arguments or {},
                context=context,
            )
        )
        return PromptRenderResult(
            name=payload.get("name", name),
            content=payload.get("content", ""),
            messages=payload.get("messages", []),
            server_name=payload.get("server_name") or self.default_server,
            metadata=payload.get("metadata", {}),
        )

    @staticmethod
    def _run(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "MCPToolProvider synchronous calls cannot run inside an active event loop in Phase 0. "
            "Use the async MCPClientManager directly from async runtime code."
        )
