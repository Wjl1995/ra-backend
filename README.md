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
