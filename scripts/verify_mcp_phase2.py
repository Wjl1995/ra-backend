from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from apps.backend.mcp import MCPClientManager, build_default_stdio_registry


async def main() -> int:
    manager = MCPClientManager(build_default_stdio_registry())

    try:
        tools = await manager.list_tools(server="utility")
        calc_result = await manager.call_tool(
            server=None,
            tool="calculator",
            arguments={"expression": "2 + 3 * 4"},
        )
        resources = await manager.list_resources(server="utility")
        resource = await manager.read_resource(server=None, uri="utility://status")
        prompts = await manager.list_prompts(server="utility")
        prompt = await manager.get_prompt(
            server=None,
            name="calculation_helper",
            arguments={"expression": "2 + 3 * 4"},
        )

        payload = {
            "tool_names": [item["name"] for item in tools],
            "calculator_result": calc_result["content"],
            "resource_uris": [item["uri"] for item in resources],
            "resource_content": resource["content"],
            "prompt_names": [item["name"] for item in prompts],
            "prompt_content": prompt["content"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        await manager.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
