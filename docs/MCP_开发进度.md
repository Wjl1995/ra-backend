# MCP 开发进度

> 本文档从 `README.md` 拆出，集中记录 MCP 相关的分期规划与落地进度。
> `README.md` 只保留仓库功能与架构的概览，详细进度请见本文件。

## MCP Phase 1

The repository now includes local stdio MCP server wrappers under `mcp_servers/`:

- `memory_server`
- `knowledge_server`
- `utility_server`

Current `utility_server` tools include low-risk helpers such as:

- `calculator`
- `get_current_time`
- `json_format`
- `write_markdown_file` (safe export mode; writes only to `data/user_exports/{user_id}/`)

They currently target Phase 1 wrapping of existing tools and can be inspected locally with:

```bash
python scripts/inspect_mcp_server.py utility tools/list
python scripts/inspect_mcp_server.py knowledge resources/list
```

Each server can also be started as a stdio process:

```bash
python -m mcp_servers.utility_server.server
python -m mcp_servers.memory_server.server
python -m mcp_servers.knowledge_server.server
```

## MCP Phase 2

The CLI `ReActAgent` can now opt into the local MCP tool runtime:

```bash
set AGENT_TOOL_MODE=mcp
python scripts/verify_mcp_phase2.py
python main.py "2+3*4 等于多少"
```

Behavior notes:

- `AGENT_TOOL_MODE=local` remains the default and keeps the previous direct `ToolRegistry` execution path.
- `AGENT_TOOL_MODE=mcp` starts the local stdio servers with `sys.executable -m mcp_servers...`.
- `MCP_SERVER_CONFIG_JSON` can override the default stdio server registry if you need custom commands or timeouts.
- Full Phase 2 MCP mode assumes the repo dependencies are installed, including packages needed by `memory` / `knowledge` / `openai`.
- For full aggregate verification, run `python scripts/verify_mcp_aggregate.py`.

## MCP Phase 3

The online chat path now runs on the shared agent runtime:

```bash
set AGENT_TOOL_MODE=mcp
python scripts/verify_phase3_chat_runtime.py
```

Behavior notes:

- `chat_service` now routes through `AgentOrchestrator` by default.
- The backend passes `user_id`, `session_id`, and `document_id` into MCP tool calls to preserve user-level document isolation.
- `AGENT_TOOL_MODE=mcp` is the recommended online setting so the chat path uses the MCP servers instead of the local in-process registry.

## MCP Phase 4

Phase 4 focuses on resources and prompts:

- `knowledge://document/{document_id}`
- `knowledge://document/{document_id}/outline`
- `memory://user/{user_id}/recent`
- `document_summary`
- `knowledge_qa`
- `rule_audit`
- `case_reference`

The server and client routing now support template-style resource URIs.
