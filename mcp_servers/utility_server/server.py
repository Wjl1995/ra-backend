from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import uuid

from apps.backend.config import settings
from mcp_servers.shared import MCPPrompt, MCPResource, MCPTool, SimpleMCPServer
from mcp_servers.shared.auth_context import parse_request_context, require_user_id
from tools.tools import _calculator, _get_current_time, _json_format


def build_server() -> SimpleMCPServer:
    server = SimpleMCPServer(name="utility-mcp-server", version="0.1.0")

    def calculator(arguments: dict) -> str:
        expression = str(arguments.get("expression") or "").strip()
        if not expression:
            raise ValueError("expression is required")
        return _calculator(expression)

    def current_time(arguments: dict) -> str:
        del arguments
        return _get_current_time()

    def json_format(arguments: dict) -> str:
        text = str(arguments.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        return _json_format(text)

    def write_markdown_file(arguments: dict, raw_context: dict) -> dict:
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("content is required")

        context = parse_request_context(raw_context)
        user_id = require_user_id(context)
        title = str(arguments.get("title") or "").strip()
        filename_hint = str(arguments.get("filename_hint") or "").strip()

        export_root = Path(settings.user_export_dir) / str(user_id)
        export_root.mkdir(parents=True, exist_ok=True)

        base_name = _sanitize_filename(filename_hint or title or "report")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_name = f"{base_name}-{timestamp}-{uuid.uuid4().hex[:8]}.md"
        target = export_root / file_name

        full_content = content
        if title:
            full_content = f"# {title}\n\n{content}"
        target.write_text(full_content, encoding="utf-8")

        relative_path = target.relative_to(Path(settings.user_export_dir))
        text = f"已导出 Markdown 文件: {target.name}"
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": {
                "file_name": target.name,
                "relative_path": relative_path.as_posix(),
            },
            "metadata": {
                "file_name": target.name,
                "relative_path": relative_path.as_posix(),
                "absolute_path": str(target),
                "user_id": user_id,
            },
            "isError": False,
        }

    def status_resource() -> dict:
        return {
            "server": "utility-mcp-server",
            "time": datetime.now().isoformat(),
            "tools": ["calculator", "get_current_time", "json_format", "write_markdown_file"],
        }

    def calculation_prompt(arguments: dict) -> dict:
        expression = str(arguments.get("expression") or "").strip()
        return {
            "description": "Calculation helper prompt",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"请先调用计算工具，再解释表达式 `{expression}` 的结果。",
                    },
                }
            ],
        }

    server.register_tool(
        MCPTool(
            name="calculator",
            description="计算数学表达式，支持加减乘除、三角函数、对数等。",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "要计算的数学表达式"},
                },
                "required": ["expression"],
            },
            handler=calculator,
        )
    )
    server.register_tool(
        MCPTool(
            name="get_current_time",
            description="获取当前日期和时间",
            input_schema={"type": "object", "properties": {}},
            handler=current_time,
        )
    )
    server.register_tool(
        MCPTool(
            name="json_format",
            description="格式化或验证 JSON 文本",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "需要格式化的 JSON 字符串"},
                },
                "required": ["text"],
            },
            handler=json_format,
        )
    )
    server.register_tool(
        MCPTool(
            name="write_markdown_file",
            description="为当前用户安全导出 Markdown 文件，只会写入受控导出目录。",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Markdown 正文内容"},
                    "title": {"type": "string", "description": "可选标题，会自动写入一级标题"},
                    "filename_hint": {"type": "string", "description": "可选文件名提示，不支持自定义路径"},
                },
                "required": ["content"],
            },
            handler=write_markdown_file,
        )
    )

    server.register_resource(
        MCPResource(
            uri="utility://status",
            name="Utility Status",
            description="utility server 当前状态",
            mime_type="application/json",
            handler=status_resource,
        )
    )

    server.register_prompt(
        MCPPrompt(
            name="calculation_helper",
            description="要求模型优先调用 calculator 的提示模板",
            arguments=[{"name": "expression", "description": "待计算表达式", "required": True}],
            handler=calculation_prompt,
        )
    )

    return server


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip())
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = cleaned.strip(" .-_")
    return cleaned[:64] or "report"


if __name__ == "__main__":
    build_server().serve_stdio()
