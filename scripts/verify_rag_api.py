import json
import mimetypes
import uuid
import urllib.request
from pathlib import Path
from typing import Optional, Union


def post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def get_json(url: str, headers: Optional[dict] = None, timeout: int = 120) -> Union[dict, list]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def post_multipart(url: str, file_path: Path, domain: str, tags: str, headers: dict, timeout: int = 120) -> dict:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="domain"\r\n\r\n',
            domain.encode(),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="tags"\r\n\r\n',
            tags.encode(),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    base = "http://127.0.0.1:8000/api/v1"
    login = post_json(f"{base}/auth/wx-login", {"code": "codex-rag-test-login"}, timeout=60)
    token = login["token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample_path = Path("/root/ra-backend/scripts/rag_sample.md")
    document = post_multipart(
        f"{base}/documents",
        sample_path,
        domain="support",
        tags="support,policy",
        headers=headers,
        timeout=120,
    )

    search_results = get_json(
        f"{base}/search?q=support%20email&top_k=3&domain=support",
        headers=headers,
        timeout=60,
    )

    session = post_json(f"{base}/chat/sessions", {"title": "RAG integration test"}, headers=headers, timeout=60)
    message = post_json(
        f"{base}/chat/sessions/{session['id']}/messages",
        {"content": "What is the support email?", "document_id": document["id"]},
        headers=headers,
        timeout=120,
    )

    print(
        json.dumps(
            {
                "document": document,
                "search_results": search_results,
                "message": message,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
