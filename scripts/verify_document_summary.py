import json
import mimetypes
import urllib.request
import uuid
from pathlib import Path
from typing import Optional


def post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def post_multipart(
    url: str,
    file_path: Path,
    domain: str,
    tags: str,
    title: str,
    headers: dict,
    timeout: int = 120,
) -> dict:
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
            b'Content-Disposition: form-data; name="title"\r\n\r\n',
            title.encode(),
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
    sample_path = Path("/root/ra-backend/scripts/rag_sample.md")

    login = post_json(f"{base}/auth/wx-login", {"code": "codex-summary-check"}, timeout=60)
    headers = {"Authorization": f"Bearer {login['token']}"}

    document = post_multipart(
        f"{base}/documents",
        sample_path,
        domain="support",
        tags="support,summary",
        title="Summary Check Doc",
        headers=headers,
        timeout=120,
    )

    session = post_json(f"{base}/chat/sessions", {"title": "Summary check"}, headers=headers, timeout=60)
    message = post_json(
        f"{base}/chat/sessions/{session['id']}/messages",
        {"content": "总结一下这个文档", "document_id": document["id"]},
        headers=headers,
        timeout=120,
    )

    print(
        json.dumps(
            {
                "document": document,
                "assistant": message["content"],
                "refs": message.get("refs", []),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
