from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.backend.auth import hash_password, normalize_username
from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User
from apps.backend.schemas import PasswordAuthRequest, QuotaSchema, UpdateProfileRequest, UserSchema

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile", response_model=UserSchema)
def get_profile(current_user: User = Depends(get_current_user)):
    return _to_user_schema(current_user)


@router.put("/profile", response_model=UserSchema)
def update_profile(
    payload: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.nickname = payload.nickname
    current_user.avatar = payload.avatar
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _to_user_schema(current_user)


@router.post("/password", response_model=UserSchema)
def bind_password(
    payload: PasswordAuthRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    username = normalize_username(payload.username)
    if len(username) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 3 characters")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user is not None and existing_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    current_user.username = username
    current_user.password_hash = hash_password(payload.password)
    if not current_user.nickname:
        current_user.nickname = username
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _to_user_schema(current_user)


def _to_user_schema(user: User) -> UserSchema:
    return UserSchema(
        id=user.id,
        nickname=user.nickname,
        avatar=user.avatar,
        quota=QuotaSchema(used=user.daily_used, total=user.daily_quota),
        username=user.username or "",
        account_bound=bool(user.username and user.password_hash),
    )
