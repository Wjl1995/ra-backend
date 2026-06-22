import json
import os
import urllib.error
import urllib.request


def main() -> int:
    base = os.getenv("VERIFY_BASE_URL", "http://127.0.0.1:8000/api/v1")
    code = os.getenv("WECHAT_LOGIN_CODE", "codex-invalid-code-check")
    payload = json.dumps({"code": code}).encode()
    req = urllib.request.Request(
        f"{base}/auth/wx-login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(resp.status)
            print(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.code)
        print(exc.read().decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
