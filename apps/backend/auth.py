from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha1

from jose import JWTError, jwt

from apps.backend.config import settings


def create_access_token(user_id: int) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": str(user_id), "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["sub"])


def mock_openid_from_code(code: str) -> str:
    return f"mock_{sha1(code.encode('utf-8')).hexdigest()[:16]}"


def is_valid_token(token: str) -> bool:
    try:
        decode_access_token(token)
        return True
    except JWTError:
        return False
