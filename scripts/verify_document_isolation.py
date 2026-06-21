import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple, Union


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


def get_status(url: str, headers: Optional[dict] = None, timeout: int = 120) -> Tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def post_multipart(
    url: str,
    file_path: Path,
    domain: str,
    tags: str,
    headers: dict,
    title: str,
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

    user_a_login = post_json(f"{base}/auth/wx-login", {"code": "codex-isolation-user-a"}, timeout=60)
    user_b_login = post_json(f"{base}/auth/wx-login", {"code": "codex-isolation-user-b"}, timeout=60)

    user_a_headers = {"Authorization": f"Bearer {user_a_login['token']}"}
    user_b_headers = {"Authorization": f"Bearer {user_b_login['token']}"}

    user_a_document = post_multipart(
        f"{base}/documents",
        sample_path,
        domain="support",
        tags="support,a",
        headers=user_a_headers,
        title="User A Support Notes",
        timeout=120,
    )
    user_b_document = post_multipart(
        f"{base}/documents",
        sample_path,
        domain="support",
        tags="support,b",
        headers=user_b_headers,
        title="User B Support Notes",
        timeout=120,
    )

    user_a_docs = get_json(f"{base}/documents", headers=user_a_headers, timeout=60)
    user_b_docs = get_json(f"{base}/documents", headers=user_b_headers, timeout=60)

    user_a_cross_detail_status, user_a_cross_detail_body = get_status(
        f"{base}/documents/{user_b_document['id']}",
        headers=user_a_headers,
        timeout=60,
    )
    user_b_cross_detail_status, user_b_cross_detail_body = get_status(
        f"{base}/documents/{user_a_document['id']}",
        headers=user_b_headers,
        timeout=60,
    )

    q = urllib.parse.quote("support email")
    user_a_search = get_json(f"{base}/search?q={q}&top_k=5&domain=support", headers=user_a_headers, timeout=60)
    user_b_search = get_json(f"{base}/search?q={q}&top_k=5&domain=support", headers=user_b_headers, timeout=60)

    user_a_session = post_json(
        f"{base}/chat/sessions",
        {"title": "Isolation test A"},
        headers=user_a_headers,
        timeout=60,
    )
    user_b_session = post_json(
        f"{base}/chat/sessions",
        {"title": "Isolation test B"},
        headers=user_b_headers,
        timeout=60,
    )

    user_a_chat = post_json(
        f"{base}/chat/sessions/{user_a_session['id']}/messages",
        {"content": "What is the support email?", "document_id": user_a_document["id"]},
        headers=user_a_headers,
        timeout=120,
    )
    user_b_chat = post_json(
        f"{base}/chat/sessions/{user_b_session['id']}/messages",
        {"content": "What is the support email?", "document_id": user_b_document["id"]},
        headers=user_b_headers,
        timeout=120,
    )

    payload = {
        "user_a": {
            "login_user_id": user_a_login["user"]["id"],
            "document_id": user_a_document["id"],
            "document_titles": [item["title"] for item in user_a_docs],
            "search_document_ids": [item["document_id"] for item in user_a_search],
            "chat_ref_document_ids": [item["document_id"] for item in user_a_chat.get("refs", [])],
        },
        "user_b": {
            "login_user_id": user_b_login["user"]["id"],
            "document_id": user_b_document["id"],
            "document_titles": [item["title"] for item in user_b_docs],
            "search_document_ids": [item["document_id"] for item in user_b_search],
            "chat_ref_document_ids": [item["document_id"] for item in user_b_chat.get("refs", [])],
        },
        "cross_access": {
            "user_a_reads_user_b_status": user_a_cross_detail_status,
            "user_b_reads_user_a_status": user_b_cross_detail_status,
            "user_a_reads_user_b_body": user_a_cross_detail_body,
            "user_b_reads_user_a_body": user_b_cross_detail_body,
        },
    }

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
