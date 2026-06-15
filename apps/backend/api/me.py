from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import User
from apps.backend.schemas import QuotaSchema, UpdateProfileRequest, UserSchema

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile", response_model=UserSchema)
def get_profile(current_user: User = Depends(get_current_user)):
    return UserSchema(
        id=current_user.id,
        nickname=current_user.nickname,
        avatar=current_user.avatar,
        quota=QuotaSchema(used=current_user.daily_used, total=current_user.daily_quota),
    )


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
    return UserSchema(
        id=current_user.id,
        nickname=current_user.nickname,
        avatar=current_user.avatar,
        quota=QuotaSchema(used=current_user.daily_used, total=current_user.daily_quota),
    )
