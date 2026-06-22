import os

from apps.backend.auth import resolve_openid_from_code
from apps.backend.config import settings


def main() -> int:
    code = os.getenv("WECHAT_LOGIN_CODE", "codex-invalid-code-check")
    print(f"mode={settings.wechat_login_mode}")
    print(f"appid={settings.wechat_app_id}")
    print(f"has_secret={bool(settings.wechat_app_secret)}")
    try:
        print(resolve_openid_from_code(code))
    except Exception as exc:  # noqa: BLE001
        print(type(exc).__name__)
        print(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
