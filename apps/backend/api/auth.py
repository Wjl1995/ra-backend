from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.backend.auth import create_access_token, mock_openid_from_code
from apps.backend.config import settings
from apps.backend.dependencies import get_db
from apps.backend.models import User
from apps.backend.schemas import LoginRequest, LoginResponse, QuotaSchema, UserSchema

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wx-login", response_model=LoginResponse)
def wx_login(payload: LoginRequest, db: Session = Depends(get_db)):
    openid = mock_openid_from_code(payload.code)
    user = db.query(User).filter(User.openid == openid).first()
    if user is None:
        user = User(openid=openid, daily_quota=settings.daily_quota)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(
        token=token,
        user=UserSchema(
            id=user.id,
            nickname=user.nickname,
            avatar=user.avatar,
            quota=QuotaSchema(used=user.daily_used, total=user.daily_quota),
        ),
    )
