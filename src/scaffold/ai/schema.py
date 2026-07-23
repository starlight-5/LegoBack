"""[1.2.2] AnalysisResult — AI 파트(B)와 CLI 파트(D) 사이의 유일한 계약.

필드 변경은 양 파트 합의 후에만 한다.
"""
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """자연어 설명 한 건에 대한 AI 분석 결과."""

    sufficient: bool = Field(
        default=True,
        description=(
            "입력 정보가 충분한가? False면 clarifying_questions로 1라운드 진행 [1.1.3]. "
            "예: '블로그 만들거야' → True / '뭐든' → False"
        ),
    )
    clarifying_questions: list[str] = Field(
        default_factory=list,
        description=(
            "[1.1.3] 최대 10개 추가 질문 (sufficient=False일 때만 채워짐). "
            "예: ['어떤 종류의 서비스인가요?', '로그인이 필요한가요?']"
        ),
    )
    recommended_modules: list[str] = Field(
        default_factory=list,
        description=(
            "[1.3.2] 최소 3개 추천 모듈 — modules/ 에 실존하는 이름만 (검증은 1.2.3). "
            "예: ['settings', 'jwt-auth', 'database']"
        ),
    )
    reasons: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "[1.3.3] 모듈명 → 추천 근거. recommended_modules의 모든 항목에 근거 필수. "
            "예: {'jwt-auth': '로그인 기능 요구가 감지되었습니다.'}"
        ),
    )
