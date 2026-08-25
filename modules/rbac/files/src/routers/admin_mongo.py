"""관리자 전용: 사용자 권한 승격 (rbac 모듈, MongoDB 변형)."""
from fastapi import APIRouter, Depends, HTTPException, status

from src.core.db import get_db
from src.core.rbac import require_role
from src.models.user import User

router = APIRouter()


async def _get_user_or_404(email: str) -> User:
    user = await User.find_one(User.email == email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="존재하지 않는 사용자입니다.")
    return user


@router.patch("/users/{email}/promote", dependencies=[require_role("ADMIN"), Depends(get_db)])
async def promote_to_admin(email: str) -> dict:
    user = await _get_user_or_404(email)

    user.role = "ADMIN"
    await user.save()
    return {"email": user.email, "role": user.role}


@router.patch("/users/{email}/demote", dependencies=[require_role("ADMIN"), Depends(get_db)])
async def demote_to_user(email: str) -> dict:
    user = await _get_user_or_404(email)

    if user.role == "ADMIN" and await User.find(User.role == "ADMIN").count() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="마지막 ADMIN은 강등할 수 없습니다.",
        )

    user.role = "USER"
    await user.save()
    return {"email": user.email, "role": user.role}
