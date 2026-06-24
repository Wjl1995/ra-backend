from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from itertools import count
from typing import Any

from apps.backend.mcp.exceptions import MCPConfigurationError, MCPConnectionError, MCPToolError
from apps.backend.mcp.server_registry import MCPServerConfig, MCPServerRegistry


_JSONRPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass(slots=True)
class _MCPProcessSession:
    config: MCPServerConfig
    process: subprocess.Popen[bytes]
    lock: threading.Lock = field(default_factory=threading.Lock)
    initialized: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)
    server_info: dict[str, Any] = field(default_factory=dict)


class MCPClientManager:
    """
    Phase 2 stdio MCP client manager.

    采用同步 subprocess + JSON-RPC framing，实现对本地 stdio MCP server 的最小可用接入。
    对外仍保留 async 方法，便于后续平滑升级到真正的异步 transport。
    """

    def __init__(self, registry: MCPServerRegistry | None = None):
        self.registry = registry or MCPServerRegistry()
        self._started = False
        self._request_counter = count(1)
        self._sessions: dict[str, _MCPProcessSession] = {}
        self._tool_cache: dict[str, list[dict[str, Any]]] = {}
        self._resource_cache: dict[str, list[dict[str, Any]]] = {}
        self._prompt_cache: dict[str, list[dict[str, Any]]] = {}
        self._tool_routes: dict[str, str] = {}
        self._resource_routes: dict[str, str] = {}
        self._prompt_routes: dict[str, str] = {}
        self._atexit_registered = False

    async def start(self) -> None:
        self._started = True
        if not self._atexit_registered:
            atexit.register(self.close)
            self._atexit_registered = True

    async def stop(self) -> None:
        self.close()
        self._started = False

    async def list_tools(
        self,
        server: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del context
        await self._ensure_started()
        if server:
            return list(self._fetch_tools(server))

        items: list[dict[str, Any]] = []
        for config in self.registry.enabled():
            items.extend(self._fetch_tools(config.name))
        self._tool_cache["__all__"] = list(items)
        return items

    async def list_resources(
        self,
        server: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del context
        await self._ensure_started()
        if server:
            return list(self._fetch_resources(server))

        items: list[dict[str, Any]] = []
        for config in self.registry.enabled():
            items.extend(self._fetch_resources(config.name))
        self._resource_cache["__all__"] = list(items)
        return items

    async def list_prompts(
        self,
        server: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        del context
        await self._ensure_started()
        if server:
            return list(self._fetch_prompts(server))

        items: list[dict[str, Any]] = []
        for config in self.registry.enabled():
            items.extend(self._fetch_prompts(config.name))
        self._prompt_cache["__all__"] = list(items)
        return items

    async def call_tool(
        self,
        server: str | None,
        tool: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del context
        await self._ensure_started()
        server_name = server or self._resolve_tool_server(tool)
        payload = self._request(
            server_name,
            "tools/call",
            {
                "name": tool,
                "arguments": arguments or {},
            },
        )
        return self._normalize_tool_call_result(server_name, tool, payload)

    async def read_resource(
        self,
        server: str | None,
        uri: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del context
        await self._ensure_started()
        server_name = server or self._resolve_resource_server(uri)
        payload = self._request(server_name, "resources/read", {"uri": uri})
        return self._normalize_resource_read_result(server_name, uri, payload)

    async def get_prompt(
        self,
        server: str | None,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del context
        await self._ensure_started()
        server_name = server or self._resolve_prompt_server(name)
        payload = self._request(
            server_name,
            "prompts/get",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )
        return self._normalize_prompt_result(server_name, name, payload)

    def seed_tool_cache(self, server: str, tools: list[dict[str, Any]]) -> None:
        self._tool_cache[server] = list(tools)
        for item in tools:
            name = item.get("name")
            if name:
                self._bind_route(self._tool_routes, name, server, kind="tool")

    def seed_resource_cache(self, server: str, resources: list[dict[str, Any]]) -> None:
        self._resource_cache[server] = list(resources)
        for item in resources:
            uri = item.get("uri")
            if uri:
                self._bind_route(self._resource_routes, uri, server, kind="resource")

    def seed_prompt_cache(self, server: str, prompts: list[dict[str, Any]]) -> None:
        self._prompt_cache[server] = list(prompts)
        for item in prompts:
            name = item.get("name")
            if name:
                self._bind_route(self._prompt_routes, name, server, kind="prompt")

    def close(self) -> None:
        for server_name in list(self._sessions):
            self._stop_session(server_name)

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    def _fetch_tools(self, server: str) -> list[dict[str, Any]]:
        cached = self._tool_cache.get(server)
        if cached is not None:
            return cached

        payload = self._request(server, "tools/list", {})
        tools = [self._normalize_tool_descriptor(server, item) for item in payload.get("tools", [])]
        self.seed_tool_cache(server, tools)
        return self._tool_cache[server]

    def _fetch_resources(self, server: str) -> list[dict[str, Any]]:
        cached = self._resource_cache.get(server)
        if cached is not None:
            return cached

        payload = self._request(server, "resources/list", {})
        resources = [
            self._normalize_resource_descriptor(server, item)
            for item in payload.get("resources", [])
        ]
        self.seed_resource_cache(server, resources)
        return self._resource_cache[server]

    def _fetch_prompts(self, server: str) -> list[dict[str, Any]]:
        cached = self._prompt_cache.get(server)
        if cached is not None:
            return cached

        payload = self._request(server, "prompts/list", {})
        prompts = [self._normalize_prompt_descriptor(server, item) for item in payload.get("prompts", [])]
        self.seed_prompt_cache(server, prompts)
        return self._prompt_cache[server]

    def _resolve_tool_server(self, tool_name: str) -> str:
        server = self._tool_routes.get(tool_name)
        if server:
            return server
        for config in self.registry.enabled():
            self._fetch_tools(config.name)
        server = self._tool_routes.get(tool_name)
        if server:
            return server
        raise MCPToolError(f"MCP tool '{tool_name}' is not exposed by any registered server")

    def _resolve_resource_server(self, uri: str) -> str:
        server = self._resource_routes.get(uri)
        if server:
            return server
        for config in self.registry.enabled():
            self._fetch_resources(config.name)
        server = self._resource_routes.get(uri)
        if server:
            return server
        raise MCPToolError(f"MCP resource '{uri}' is not exposed by any registered server")

    def _resolve_prompt_server(self, name: str) -> str:
        server = self._prompt_routes.get(name)
        if server:
            return server
        for config in self.registry.enabled():
            self._fetch_prompts(config.name)
        server = self._prompt_routes.get(name)
        if server:
            return server
        raise MCPToolError(f"MCP prompt '{name}' is not exposed by any registered server")

    def _request(self, server_name: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        session = self._ensure_session(server_name)
        request_id = next(self._request_counter)
        request = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        }

        with session.lock:
            try:
                self._write_message(session.process, request)
                response = self._read_response_with_timeout(session)
            except BrokenPipeError as exc:
                self._stop_session(server_name)
                raise MCPConnectionError(
                    f"MCP server '{server_name}' disconnected while handling '{method}'"
                ) from exc

        if response.get("id") != request_id:
            raise MCPConnectionError(
                f"MCP server '{server_name}' returned mismatched response id "
                f"for '{method}': expected {request_id}, got {response.get('id')}"
            )

        error = response.get("error")
        if error:
            raise MCPToolError(
                f"MCP server '{server_name}' method '{method}' failed: "
                f"{error.get('message', 'unknown error')}"
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPConnectionError(
                f"MCP server '{server_name}' method '{method}' returned invalid payload"
            )
        return result

    def _ensure_session(self, server_name: str) -> _MCPProcessSession:
        session = self._sessions.get(server_name)
        if session is not None and session.process.poll() is None:
            if not session.initialized:
                self._initialize_session(server_name, session)
            return session

        config = self.registry.get(server_name)
        if config is None:
            raise MCPConfigurationError(f"MCP server '{server_name}' is not registered")
        if not config.enabled:
            raise MCPConfigurationError(f"MCP server '{server_name}' is disabled")
        if config.transport != "stdio":
            raise MCPConfigurationError(
                f"MCP server '{server_name}' uses unsupported transport '{config.transport}' in Phase 2"
            )
        if not config.command:
            raise MCPConfigurationError(f"MCP server '{server_name}' is missing stdio command")

        session = _MCPProcessSession(config=config, process=self._start_process(config))
        self._sessions[server_name] = session
        self._initialize_session(server_name, session)
        return session

    def _initialize_session(self, server_name: str, session: _MCPProcessSession) -> None:
        payload = self._request_raw(
            session,
            server_name,
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "ra-backend-cli",
                    "version": "0.2.0",
                },
            },
        )
        session.capabilities = dict(payload.get("capabilities") or {})
        session.server_info = dict(payload.get("serverInfo") or {})
        session.initialized = True

    def _request_raw(
        self,
        session: _MCPProcessSession,
        server_name: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = next(self._request_counter)
        request = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        }

        with session.lock:
            self._write_message(session.process, request)
            response = self._read_response_with_timeout(session)

        if response.get("id") != request_id:
            raise MCPConnectionError(
                f"MCP server '{server_name}' returned mismatched response id "
                f"for '{method}': expected {request_id}, got {response.get('id')}"
            )

        error = response.get("error")
        if error:
            raise MCPConnectionError(
                f"MCP server '{server_name}' initialize failed: {error.get('message', 'unknown error')}"
            )

        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPConnectionError(
                f"MCP server '{server_name}' method '{method}' returned invalid payload"
            )
        return result

    def _start_process(self, config: MCPServerConfig) -> subprocess.Popen[bytes]:
        env = os.environ.copy()
        env.update(config.env)
        cwd = config.metadata.get("cwd") if isinstance(config.metadata, dict) else None
        command = [config.command, *config.args]
        try:
            return subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            raise MCPConnectionError(
                f"Failed to start MCP server '{config.name}' with command: {command}"
            ) from exc

    def _read_response_with_timeout(self, session: _MCPProcessSession) -> dict[str, Any]:
        holder: dict[str, Any] = {}
        error_holder: dict[str, BaseException] = {}

        def target() -> None:
            try:
                holder["response"] = self._read_message(session.process)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        reader = threading.Thread(target=target, daemon=True)
        reader.start()
        reader.join(session.config.timeout_seconds)

        if reader.is_alive():
            self._terminate_process(session.process)
            reader.join(1.0)
            raise MCPConnectionError(
                f"MCP server '{session.config.name}' timed out after "
                f"{session.config.timeout_seconds:.1f}s"
            )

        if "error" in error_holder:
            raise MCPConnectionError(
                f"Failed to read response from MCP server '{session.config.name}'"
            ) from error_holder["error"]

        response = holder.get("response")
        if response is None:
            stderr_bytes = b""
            if session.process.stderr is not None:
                try:
                    stderr_bytes = session.process.stderr.read()
                except OSError:
                    stderr_bytes = b""
            stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
            detail = f" stderr: {stderr_text}" if stderr_text else ""
            raise MCPConnectionError(
                f"MCP server '{session.config.name}' closed the stdio stream unexpectedly.{detail}"
            )

        return response

    def _stop_session(self, server_name: str) -> None:
        session = self._sessions.pop(server_name, None)
        if session is None:
            return
        self._terminate_process(session.process)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    @staticmethod
    def _write_message(process: subprocess.Popen[bytes], payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise MCPConnectionError("MCP server stdin is unavailable")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8"))
        process.stdin.write(data)
        process.stdin.flush()

    @staticmethod
    def _read_message(process: subprocess.Popen[bytes]) -> dict[str, Any] | None:
        if process.stdout is None:
            raise MCPConnectionError("MCP server stdout is unavailable")

        headers: dict[str, str] = {}
        while True:
            line = process.stdout.readline()
            if not line:
                return None
            decoded = line.decode("utf-8").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise MCPConnectionError("MCP server returned an empty message body")

        body = process.stdout.read(content_length)
        if len(body) != content_length:
            raise MCPConnectionError("MCP server returned an incomplete message body")
        return json.loads(body.decode("utf-8"))

    def _normalize_tool_descriptor(self, server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = {}
        if "annotations" in payload:
            metadata["annotations"] = payload["annotations"]
        return {
            "name": payload.get("name", ""),
            "description": payload.get("description", ""),
            "parameters": payload.get("parameters") or payload.get("inputSchema") or {},
            "server_name": server_name,
            "metadata": metadata,
        }

    def _normalize_resource_descriptor(self, server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "uri": payload.get("uri", ""),
            "name": payload.get("name", payload.get("uri", "")),
            "description": payload.get("description", ""),
            "mime_type": payload.get("mime_type") or payload.get("mimeType"),
            "server_name": server_name,
            "metadata": {},
        }

    def _normalize_prompt_descriptor(self, server_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        arguments = payload.get("arguments") or []
        return {
            "name": payload.get("name", ""),
            "description": payload.get("description", ""),
            "arguments_schema": self._prompt_arguments_to_schema(arguments),
            "server_name": server_name,
            "metadata": {
                "arguments": arguments,
            },
        }

    def _normalize_tool_call_result(
        self,
        server_name: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        content_blocks = payload.get("content", [])
        return {
            "tool_name": tool_name,
            "server_name": server_name,
            "content": self._extract_text_from_blocks(content_blocks),
            "is_error": bool(payload.get("isError", False)),
            "metadata": {
                "content_blocks": content_blocks,
            },
        }

    def _normalize_resource_read_result(
        self,
        server_name: str,
        uri: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        contents = payload.get("contents") or []
        primary = contents[0] if contents else {}
        return {
            "uri": primary.get("uri", uri),
            "content": primary.get("text", self._extract_text_from_blocks(contents)),
            "mime_type": primary.get("mime_type") or primary.get("mimeType"),
            "server_name": server_name,
            "metadata": {
                "contents": contents,
            },
        }

    def _normalize_prompt_result(
        self,
        server_name: str,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        messages = payload.get("messages") or []
        return {
            "name": name,
            "content": self._extract_text_from_messages(messages),
            "messages": messages,
            "server_name": server_name,
            "metadata": {
                "description": payload.get("description", ""),
            },
        }

    @staticmethod
    def _prompt_arguments_to_schema(arguments: list[dict[str, Any]]) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for item in arguments:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            properties[name] = {
                "type": item.get("type", "string"),
                "description": item.get("description", ""),
            }
            if item.get("required"):
                required.append(name)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    @staticmethod
    def _extract_text_from_messages(messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, dict):
                if content.get("type") == "text":
                    parts.append(str(content.get("text", "")))
                else:
                    parts.append(json.dumps(content, ensure_ascii=False))
            elif content is not None:
                parts.append(json.dumps(content, ensure_ascii=False))
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _extract_text_from_blocks(blocks: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in blocks:
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _bind_route(
        routes: dict[str, str],
        key: str,
        server_name: str,
        *,
        kind: str,
    ) -> None:
        existing = routes.get(key)
        if existing and existing != server_name:
            raise MCPConfigurationError(
                f"Duplicate MCP {kind} '{key}' exposed by both '{existing}' and '{server_name}'"
            )
        routes[key] = server_name
