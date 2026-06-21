import json
import sys
import urllib.request
from typing import Optional


def post(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    base = "http://127.0.0.1:8000/api/v1"
    login = post(f"{base}/auth/wx-login", {"code": "codex-test-login"}, timeout=60)
    token = login["token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = post(f"{base}/chat/sessions", {"title": "Kimi integration test"}, headers=headers, timeout=60)
    message = post(
        f"{base}/chat/sessions/{session['id']}/messages",
        {"content": "Please introduce yourself in one sentence."},
        headers=headers,
        timeout=120,
    )

    sys.stdout.write(json.dumps({"session": session, "message": message}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
