"""관리자 전용: 사용자 권한 승격 (rbac 모듈)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.core.rbac import require_role
from src.models.user import User

router = APIRouter()


def _get_user_or_404(email: str, db: Session) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="존재하지 않는 사용자입니다.")
    return user


@router.patch("/users/{email}/promote", dependencies=[require_role("ADMIN")])
def promote_to_admin(email: str, db: Session = Depends(get_db)) -> dict:
    user = _get_user_or_404(email, db)

    user.role = "ADMIN"
    db.commit()
    return {"email": user.email, "role": user.role}


@router.patch("/users/{email}/demote", dependencies=[require_role("ADMIN")])
def demote_to_user(email: str, db: Session = Depends(get_db)) -> dict:
    user = _get_user_or_404(email, db)

    if user.role == "ADMIN" and db.query(User).filter(User.role == "ADMIN").count() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="마지막 ADMIN은 강등할 수 없습니다.",
        )

    user.role = "USER"
    db.commit()
    return {"email": user.email, "role": user.role}
