from __future__ import annotations

from datetime import datetime

from mcp_servers.shared import MCPPrompt, MCPResource, MCPTool, SimpleMCPServer
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

    def status_resource() -> dict:
        return {
            "server": "utility-mcp-server",
            "time": datetime.now().isoformat(),
            "tools": ["calculator", "get_current_time", "json_format"],
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


if __name__ == "__main__":
    build_server().serve_stdio()
