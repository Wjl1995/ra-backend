from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from jose import JWTError, jwt

from apps.backend.config import settings


class WeChatLoginError(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_access_token(user_id: int) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": str(user_id), "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["sub"])


def mock_openid_from_code(code: str) -> str:
    return f"mock_{sha1(code.encode('utf-8')).hexdigest()[:16]}"


def resolve_openid_from_code(code: str) -> str:
    if settings.wechat_login_mode == "mock":
        return mock_openid_from_code(code)
    if settings.wechat_login_mode != "wechat":
        raise WeChatLoginError("Unsupported WeChat login mode", status_code=500)
    return _fetch_wechat_openid(code)


def is_valid_token(token: str) -> bool:
    try:
        decode_access_token(token)
        return True
    except JWTError:
        return False


def _fetch_wechat_openid(code: str) -> str:
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise WeChatLoginError("WeChat AppID/AppSecret is not configured", status_code=500)

    query = urlencode(
        {
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
    )
    url = f"https://api.weixin.qq.com/sns/jscode2session?{query}"
    try:
        with urlopen(url, timeout=settings.wechat_api_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise WeChatLoginError("WeChat login request failed", status_code=502) from exc
    except URLError as exc:
        raise WeChatLoginError("Unable to reach WeChat login service", status_code=502) from exc

    errcode = int(payload.get("errcode") or 0)
    if errcode:
        errmsg = str(payload.get("errmsg") or "unknown error")
        status_code = 401 if errcode in {40029, 40163} else 502
        raise WeChatLoginError(
            f"WeChat login failed ({errcode}): {errmsg}",
            status_code=status_code,
        )

    openid = str(payload.get("openid") or "").strip()
    if not openid:
        raise WeChatLoginError("WeChat login response did not include openid", status_code=502)
    return openid
