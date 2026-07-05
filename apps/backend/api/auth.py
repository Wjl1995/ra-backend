from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.backend.auth import (
    WeChatLoginError,
    account_openid,
    create_access_token,
    hash_password,
    normalize_username,
    resolve_openid_from_code,
    verify_password,
)
from apps.backend.config import settings
from apps.backend.dependencies import get_db
from apps.backend.models import User
from apps.backend.schemas import LoginRequest, LoginResponse, PasswordAuthRequest, QuotaSchema, UserSchema

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wx-login", response_model=LoginResponse)
def wx_login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        openid = resolve_openid_from_code(payload.code)
    except WeChatLoginError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    user = db.query(User).filter(User.openid == openid).first()
    if user is None:
        user = User(openid=openid, daily_quota=settings.daily_quota)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(
        token=token,
        user=_to_user_schema(user),
    )


@router.post("/password-register", response_model=LoginResponse)
def password_register(payload: PasswordAuthRequest, db: Session = Depends(get_db)):
    username = normalize_username(payload.username)
    if len(username) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 3 characters")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        openid=account_openid(username),
        username=username,
        password_hash=hash_password(payload.password),
        nickname=username,
        daily_quota=settings.daily_quota,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return LoginResponse(token=create_access_token(user.id), user=_to_user_schema(user))


@router.post("/password-login", response_model=LoginResponse)
def password_login(payload: PasswordAuthRequest, db: Session = Depends(get_db)):
    username = normalize_username(payload.username)
    if len(username) < 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    return LoginResponse(token=create_access_token(user.id), user=_to_user_schema(user))


def _to_user_schema(user: User) -> UserSchema:
    return UserSchema(
        id=user.id,
        nickname=user.nickname,
        avatar=user.avatar,
        quota=QuotaSchema(used=user.daily_used, total=user.daily_quota),
        username=user.username or "",
        account_bound=bool(user.username and user.password_hash),
    )
