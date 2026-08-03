"""RBAC (rbac 모듈). 사용 예: @router.get(..., dependencies=[require_role("ADMIN")])"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.routers.auth import decode_access_token

security = HTTPBearer()


def require_role(role: str):
    def checker(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        payload = decode_access_token(credentials.credentials)
        if payload.get("role") != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"{role} 권한이 필요합니다.",
            )
        return payload
    return Depends(checker)
