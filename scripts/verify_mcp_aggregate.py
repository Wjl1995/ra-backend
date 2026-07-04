from __future__ import annotations

import asyncio
import os
import sys
import uuid

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from apps.backend.mcp import MCPClientManager, build_default_stdio_registry


async def verify_manager() -> dict:
    manager = MCPClientManager(build_default_stdio_registry())
    token = f"phase2-aggregate-{uuid.uuid4().hex[:8]}"

    try:
        tools = await manager.list_tools()
        resources = await manager.list_resources()
        prompts = await manager.list_prompts()

        calculator = await manager.call_tool(
            server=None,
            tool="calculator",
            arguments={"expression": "2 + 3 * 4"},
        )
        write_markdown_file = await manager.call_tool(
            server=None,
            tool="write_markdown_file",
            arguments={
                "title": f"聚合验证导出 {token}",
                "filename_hint": f"aggregate-{token}",
                "content": f"聚合验证导出内容 {token}",
            },
            context={"user_id": 880001},
        )
        save_memory = await manager.call_tool(
            server=None,
            tool="save_memory",
            arguments={"content": f"聚合验证记忆 {token}", "tag": token},
        )
        search_memory = await manager.call_tool(
            server=None,
            tool="search_memory",
            arguments={"query": token, "top_k": 3},
        )
        save_experience = await manager.call_tool(
            server=None,
            tool="save_experience",
            arguments={
                "content": f"聚合验证经验 {token}",
                "scenario": f"Phase2 aggregate {token}",
                "outcome": "success",
                "tags": token,
            },
        )
        retrieve_case = await manager.call_tool(
            server=None,
            tool="retrieve_case",
            arguments={"query": "聚合验证经验", "top_k": 5},
        )

        utility_status = await manager.read_resource(server=None, uri="utility://status")
        memory_stats = await manager.read_resource(server=None, uri="memory://stats")
        knowledge_stats = await manager.read_resource(server=None, uri="knowledge://stats")

        return {
            "token": token,
            "tool_names": sorted(item["name"] for item in tools),
            "resource_uris": sorted(item["uri"] for item in resources),
            "prompt_names": sorted(item["name"] for item in prompts),
            "calculator_result": calculator["content"],
            "write_markdown_file_result": write_markdown_file["content"],
            "save_memory_result": save_memory["content"],
            "search_memory_result": search_memory["content"],
            "save_experience_result": save_experience["content"],
            "retrieve_case_result": retrieve_case["content"],
            "utility_status": utility_status["content"],
            "memory_stats": memory_stats["content"],
            "knowledge_stats": knowledge_stats["content"],
        }
    finally:
        await manager.stop()


def verify_agent_tool_provider() -> dict:
    os.environ["AGENT_TOOL_MODE"] = "mcp"
    os.environ.setdefault("KIMI_API_KEY", "phase2-aggregate-smoke")

    from agent.react_agent import ReActAgent

    agent = ReActAgent(api_key=os.environ["KIMI_API_KEY"])
    tools = agent.tool_provider.list_tools(context={"query": "列出可用工具"})
    return {
        "agent_tool_names": sorted(tool.name for tool in tools),
        "tool_count": len(tools),
    }


def main() -> int:
    manager_result = asyncio.run(verify_manager())
    agent_result = verify_agent_tool_provider()

    expected_tools = {
        "calculator",
        "get_current_time",
        "json_format",
        "write_markdown_file",
        "save_memory",
        "search_memory",
        "search_knowledge",
        "lookup_rule",
        "retrieve_case",
        "save_experience",
        "search_document_chunks",
    }
    missing = sorted(expected_tools - set(manager_result["tool_names"]))
    if missing:
        raise RuntimeError(f"Missing aggregated MCP tools: {missing}")
    if manager_result["calculator_result"].strip() != "14":
        raise RuntimeError("calculator MCP call did not return 14")
    if "已导出 Markdown 文件" not in manager_result["write_markdown_file_result"]:
        raise RuntimeError("write_markdown_file did not succeed")
    if "已保存" not in manager_result["save_experience_result"]:
        raise RuntimeError("save_experience did not succeed")
    if manager_result["token"] not in manager_result["search_memory_result"]:
        raise RuntimeError("search_memory did not find the saved marker")
    if "聚合验证经验" not in manager_result["retrieve_case_result"]:
        raise RuntimeError("retrieve_case did not find the saved experience marker")
    if sorted(agent_result["agent_tool_names"]) != sorted(manager_result["tool_names"]):
        raise RuntimeError("ReActAgent MCP tool list does not match manager aggregate view")

    import json

    payload = {
        "manager": manager_result,
        "agent": agent_result,
        "status": "ok",
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
