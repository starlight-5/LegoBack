"""RBAC (rbac 모듈). 사용 예: @router.get(..., dependencies=[require_role("ADMIN")])

TODO(모듈 파트): jwt-auth의 토큰 해석과 연결해 실제 role 검사 구현.
"""
from fastapi import Depends, HTTPException


def require_role(role: str):
    def checker():
        # TODO: 토큰에서 role 추출 후 비교
        raise HTTPException(status_code=501, detail=f"TODO: {role} 검사 미구현")
    return Depends(checker)
