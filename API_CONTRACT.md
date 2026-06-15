# API Contract

This document captures the initial API surface for the online ReActAgent backend.
It is intentionally small and aligned with `docs/ONLINE_PLAN_线上化项目计划与技术方案.md`.

## Base

- Base path: `/api/v1`
- Auth: `Authorization: Bearer <jwt>`
- Content type: `application/json` unless otherwise noted

## Auth

### `POST /auth/wx-login`

Request:

```json
{
  "code": "wx-login-code"
}
```

Response:

```json
{
  "token": "jwt-token",
  "user": {
    "id": 1,
    "nickname": "",
    "avatar": "",
    "quota": {
      "used": 0,
      "total": 50
    }
  }
}
```

## Profile

### `GET /me/profile`

Response:

```json
{
  "id": 1,
  "nickname": "",
  "avatar": "",
  "quota": {
    "used": 0,
    "total": 50
  }
}
```

### `PUT /me/profile`

Request:

```json
{
  "nickname": "demo",
  "avatar": "https://example.com/avatar.png"
}
```

## Chat

### `GET /chat/sessions`

Response:

```json
[
  {
    "id": 1,
    "title": "New session",
    "last_msg_at": "2026-06-15T00:00:00Z",
    "message_count": 1
  }
]
```

### `POST /chat/sessions`

Request:

```json
{
  "title": "Optional title"
}
```

### `GET /chat/sessions/{id}/messages`

Response:

```json
[
  {
    "id": 10,
    "role": "assistant",
    "content": "Answer text",
    "refs": [],
    "created_at": "2026-06-15T00:00:00Z"
  }
]
```

### `POST /chat/sessions/{id}/messages`

Synchronous response:

```json
{
  "id": 11,
  "role": "assistant",
  "content": "Answer text",
  "refs": [
    {
      "document_id": 1,
      "title": "Doc title",
      "snippet": "Quoted snippet",
      "score": 0.91
    }
  ]
}
```

Asynchronous fallback when generation exceeds the timeout budget:

```json
{
  "status": "thinking",
  "thinking_id": "job_123"
}
```

### `GET /chat/thinking/{thinking_id}`

Response while running:

```json
{
  "status": "running"
}
```

Response when completed:

```json
{
  "status": "completed",
  "message": {
    "id": 11,
    "role": "assistant",
    "content": "Answer text",
    "refs": []
  }
}
```

## Documents

### `GET /documents`

Query params:

- `domain`
- `keyword`
- `published`

### `POST /documents`

Multipart form:

- `file`
- `domain`
- `tags`

Response:

```json
{
  "id": 1,
  "title": "Uploaded file",
  "status": "parsing"
}
```

## Search

### `GET /search`

Query params:

- `q`
- `top_k`
- `domain`

Response:

```json
[
  {
    "id": 1,
    "title": "Doc title",
    "snippet": "Matched text",
    "score": 0.9,
    "document_id": 1
  }
]
```

## Notes

- Public-facing document APIs must filter unpublished content.
- The final implementation should persist async document and chat jobs instead of relying only on process-local memory.
