from __future__ import annotations

import json
import inspect
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


class JsonRpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(slots=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            payload["annotations"] = self.annotations
        return payload


@dataclass(slots=True)
class MCPResource:
    uri: str
    name: str
    description: str = ""
    mime_type: str = "application/json"
    handler: Callable[[], Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "uri": self.uri,
            "name": self.name,
        }
        if self.description:
            payload["description"] = self.description
        if self.mime_type:
            payload["mimeType"] = self.mime_type
        return payload


@dataclass(slots=True)
class MCPPrompt:
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)
    handler: Callable[[dict[str, Any]], Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {"name": self.name}
        if self.description:
            payload["description"] = self.description
        if self.arguments:
            payload["arguments"] = self.arguments
        return payload


class SimpleMCPServer:
    """
    Minimal stdio MCP server for Phase 1.

    Supports:
    - initialize
    - ping
    - tools/list
    - tools/call
    - resources/list
    - resources/read
    - prompts/list
    - prompts/get
    """

    def __init__(self, name: str, version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.tools: dict[str, MCPTool] = {}
        self.resources: dict[str, MCPResource] = {}
        self.prompts: dict[str, MCPPrompt] = {}

    def register_tool(self, tool: MCPTool) -> None:
        self.tools[tool.name] = tool

    def register_resource(self, resource: MCPResource) -> None:
        self.resources[resource.uri] = resource

    def register_prompt(self, prompt: MCPPrompt) -> None:
        self.prompts[prompt.name] = prompt

    def serve_stdio(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break

            if "id" not in message:
                # Ignore notifications in Phase 1.
                continue

            request_id = message.get("id")
            try:
                result = self.handle_request(message)
                self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})
            except JsonRpcError as exc:
                self._write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "data": exc.data,
                        },
                    }
                )
            except Exception as exc:  # noqa: BLE001
                self._write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": f"Internal error: {exc}",
                            "data": traceback.format_exc(),
                        },
                    }
                )

    def handle_request(self, message: dict[str, Any]) -> dict[str, Any]:
        method = message.get("method")
        params = message.get("params") or {}

        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {} if self.tools else None,
                    "resources": {} if self.resources else None,
                    "prompts": {} if self.prompts else None,
                },
                "serverInfo": {
                    "name": self.name,
                    "version": self.version,
                },
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool.to_payload() for tool in self.tools.values()]}
        if method == "tools/call":
            return self._handle_tool_call(params)
        if method == "resources/list":
            return {"resources": [resource.to_payload() for resource in self.resources.values()]}
        if method == "resources/read":
            return self._handle_resource_read(params)
        if method == "prompts/list":
            return {"prompts": [prompt.to_payload() for prompt in self.prompts.values()]}
        if method == "prompts/get":
            return self._handle_prompt_get(params)

        raise JsonRpcError(-32601, f"Method not found: {method}")

    def _handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        context = params.get("context") or {}
        tool = self.tools.get(name)
        if tool is None:
            raise JsonRpcError(-32602, f"Unknown tool: {name}")

        if not isinstance(arguments, dict):
            raise JsonRpcError(-32602, "Tool arguments must be an object")

        try:
            payload = self._invoke_handler(tool.handler, arguments, context)
            if isinstance(payload, dict) and "content" in payload:
                return payload
            return {
                "content": [
                    {
                        "type": "text",
                        "text": self._to_text(payload),
                    }
                ],
                "isError": False,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"[工具执行错误] {type(exc).__name__}: {exc}",
                    }
                ],
                "isError": True,
            }

    def _handle_resource_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = str(params.get("uri") or "").strip()
        context = params.get("context") or {}
        resource = self.resources.get(uri)
        if resource is None or resource.handler is None:
            raise JsonRpcError(-32602, f"Unknown resource: {uri}")

        payload = self._invoke_handler(resource.handler, {}, context)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource.mime_type,
                    "text": self._to_text(payload),
                }
            ]
        }

    def _handle_prompt_get(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        context = params.get("context") or {}
        prompt = self.prompts.get(name)
        if prompt is None or prompt.handler is None:
            raise JsonRpcError(-32602, f"Unknown prompt: {name}")

        payload = self._invoke_handler(prompt.handler, arguments, context)
        if isinstance(payload, dict):
            return payload
        return {
            "description": prompt.description,
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": self._to_text(payload),
                    },
                }
            ],
        }

    @staticmethod
    def _to_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _invoke_handler(handler: Callable, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
        params = inspect.signature(handler).parameters
        if len(params) <= 0:
            return handler()
        if len(params) == 1:
            return handler(arguments)
        return handler(arguments, context)

    @staticmethod
    def _read_message() -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            decoded = line.decode("utf-8").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None
        body = sys.stdin.buffer.read(content_length)
        return json.loads(body.decode("utf-8"))

    @staticmethod
    def _write_message(payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8"))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
