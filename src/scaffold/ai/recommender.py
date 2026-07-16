"""[1.2] AI 요구사항 분석 / [1.3] 모듈 추천.

현재는 오프라인 키워드 휴리스틱으로 동작한다(데모·테스트 가능).
TODO [1.2.1]: _call_llm 을 Gemini 등 실제 LLM 호출로 교체 — 어댑터 함수 하나만
바꾸면 되도록 이 파일 밖에서는 analyze()만 사용할 것.
"""
from scaffold.engine.manifest import ModuleManifest

from .schema import AnalysisResult

_KEYWORDS = {   # 임시 휴리스틱: LLM 연동 전까지의 대체 추천 규칙
    "jwt-auth": ["로그인", "회원", "인증", "auth", "user"],
    "database": ["db", "데이터", "저장", "게시", "블로그", "쇼핑"],
    "redis-cache": ["캐시", "빠른", "조회", "redis"],
    "docker": ["배포", "docker", "컨테이너"],
    "ci": ["테스트", "ci", "자동화"],
}
_ALWAYS = ["settings"]


def _call_llm(description: str, module_catalog: str) -> dict:
    """TODO [1.2.1]: 실제 LLM 호출로 교체. 프롬프트에 module_catalog를 주입해
    실존 모듈만 추천하도록 강제하고, JSON(structured output)으로 응답받는다."""
    raise NotImplementedError


def analyze(description: str, manifests: dict[str, ModuleManifest]) -> AnalysisResult:
    """[1.2.2] 분석 실행 → AnalysisResult 반환. [1.2.3] 환각 모듈 제거 포함."""
    text = description.lower()
    picked = [m for m in _ALWAYS if m in manifests]
    for module, words in _KEYWORDS.items():
        if module in manifests and any(w in text for w in words):
            picked.append(module)

    sufficient = len(description.strip()) >= 10
    questions: list[str] = []
    if not sufficient:                       # [1.1.3] 보완 질문 최대 3개, 1라운드
        questions = [
            "어떤 종류의 서비스인가요? (예: 블로그, 쇼핑몰, 사내 도구)",
            "로그인/회원 기능이 필요한가요?",
            "데이터를 저장해야 하나요? 어떤 데이터인가요?",
        ]

    picked = [m for m in dict.fromkeys(picked) if m in manifests]   # [1.2.3] 검증
    reasons = {m: f"설명에서 '{m}' 관련 요구가 감지되었습니다." for m in picked}
    return AnalysisResult(
        sufficient=sufficient,
        clarifying_questions=questions[:3],
        recommended_modules=picked,
        reasons=reasons,
    )
