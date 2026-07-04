# ra-backend

Backend service for the ReActAgent mini program.

## Overview

`ra-backend` is the Python backend for a document-centric AI assistant. It provides:

- WeChat mini program authentication
- user profile and quota APIs
- chat sessions and message persistence
- document upload, parsing, and search
- retrieval-augmented chat over user documents
- local MCP servers for knowledge, memory, and utility tools

The online service is implemented with FastAPI under `apps/backend/`. The repository also keeps the original local agent, knowledge, memory, and tool modules that support the online runtime.

## Repository Layout

- `apps/backend/`: FastAPI app, API routes, services, schemas, auth, database, and agent runtime
- `knowledge/`: document processing, parsers, chunking, and knowledge store logic
- `memory/`: user memory helpers used by the agent stack
- `mcp_servers/`: local stdio MCP servers for knowledge, memory, and utility capabilities
- `scripts/`: smoke tests and verification helpers
- `docs/`: architecture notes and implementation documents
- `data/`: runtime data directory for SQLite, uploads, and vector store persistence

## Main API Surface

Base path: `/api/v1`

- `POST /auth/wx-login`
- `GET /me/profile`
- `PUT /me/profile`
- `GET /chat/sessions`
- `POST /chat/sessions`
- `GET /chat/sessions/{id}/messages`
- `POST /chat/sessions/{id}/messages`
- `GET /documents`
- `GET /documents/{id}`
- `POST /documents`
- `GET /search`
- `GET /suggestions`

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn apps.backend.main:app --reload
```

Useful verification commands:

```bash
python scripts/verify_chat_api.py
python scripts/verify_rag_api.py
python scripts/verify_document_summary.py
python scripts/verify_document_isolation.py
python scripts/verify_phase3_chat_runtime.py
```

Debug local knowledge and memory behavior:

```bash
python scripts/debug_knowledge.py --help
python scripts/debug_memory.py --help
```

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Common variables:

- `KIMI_API_KEY`: LLM API key
- `KIMI_BASE_URL`: LLM endpoint base URL
- `KIMI_MODEL`: model name
- `DATABASE_URL`: database connection string
- `UPLOAD_DIR`: uploaded document directory
- `CHROMA_PERSIST_DIR`: vector store persistence directory
- `JWT_SECRET`: JWT signing secret
- `WECHAT_LOGIN_MODE`: `mock` or `wechat`
- `WECHAT_APP_ID`: mini program app id
- `WECHAT_APP_SECRET`: mini program app secret
- `AGENT_TOOL_MODE`: `local` or `mcp`

For local smoke tests, `WECHAT_LOGIN_MODE=mock` is the simplest setup. For real mini program login, use `WECHAT_LOGIN_MODE=wechat` and fill the WeChat credentials.

## MCP and Agent Runtime

The backend can execute tools in two modes:

- `AGENT_TOOL_MODE=local`: uses the in-process tool registry
- `AGENT_TOOL_MODE=mcp`: uses local stdio MCP servers

Available MCP server groups:

- `knowledge_server`
- `memory_server`
- `utility_server`

The online chat path uses the shared agent runtime in `apps/backend/agent_runtime/`. That runtime supports:

- tool calls
- prompt templates
- resource references
- per-user and per-document context isolation
- trace metadata attached to assistant messages

## Deployment

Container deployment files are included:

- `Dockerfile`
- `docker-compose.yml`
- `Caddyfile`

Typical deployment flow:

```bash
git clone <repo-url>
cd ra-backend
cp .env.example .env
docker compose up -d --build
```

Notes:

- the app service listens on `127.0.0.1:8000` in Compose
- Caddy is expected to terminate public traffic on ports `80` and `443`
- persistent runtime data is stored under `./data/`

## Related Repository

The corresponding WeChat mini program frontend lives in `ra-miniapp`.
