# ra-backend

Backend service for ReActAgent online deployment.

## Current Scope

The repository contains:

- the original ReAct agent, memory, and knowledge modules
- a FastAPI backend scaffold under `apps/backend/`
- deployment files for Docker Compose and Caddy

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Debug helpers for memory / knowledge stores:

```bash
python scripts/debug_memory.py --help
python scripts/debug_knowledge.py --help
```

Run the backend scaffold:

```bash
uvicorn apps.backend.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## API Coverage

Current scaffold routes:

- `POST /api/v1/auth/wx-login`
- `GET /api/v1/me/profile`
- `PUT /api/v1/me/profile`
- `GET /api/v1/chat/sessions`
- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{id}/messages`
- `POST /api/v1/chat/sessions/{id}/messages`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `POST /api/v1/documents`
- `GET /api/v1/search`
- `GET /api/v1/suggestions`

## Deployment Files

- `Dockerfile`
- `docker-compose.yml`
- `Caddyfile`
- `.env.example`
- `.dockerignore`

## Server Deployment

1. Clone the repo on the server:

```bash
git clone https://github.com/Wjl1995/ra-backend.git
cd ra-backend
```

2. Prepare environment variables:

```bash
cp .env.example .env
```

3. Edit `.env` and fill at least:

- `KIMI_API_KEY`
- `JWT_SECRET`
- `WECHAT_LOGIN_MODE=wechat`
- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

4. Update `Caddyfile` with your real API domain.

5. Build and run:

```bash
docker compose up -d --build
```

6. Check status:

```bash
docker compose ps
docker compose logs -f app
docker compose logs -f caddy
```

## Notes

- `docker-compose.yml` binds the app service to `127.0.0.1:8000` and expects Caddy to terminate public HTTP/HTTPS traffic.
- Persistent data is stored in `./data/`.
- The backend supports two auth modes:
  - `WECHAT_LOGIN_MODE=mock` for local/service smoke tests
  - `WECHAT_LOGIN_MODE=wechat` for real mini program `wx.login -> code2session -> openid -> JWT`

## MCP Phase 1

The repository now includes local stdio MCP server wrappers under `mcp_servers/`:

- `memory_server`
- `knowledge_server`
- `utility_server`

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
