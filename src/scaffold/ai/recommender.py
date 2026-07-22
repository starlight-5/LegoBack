"""[1.2] AI 요구사항 분석 / [1.3] 모듈 추천.

Google Gemini(`google-genai`)로 분석한다. 실패 시(키 없음·패키지 미설치·네트워크 오류 등)
AIConnectionError를 던진다. 이 파일 밖에서는 analyze()만 사용할 것.
"""
import os

from pydantic import BaseModel, Field

from scaffold.engine.errors import AIConnectionError
from scaffold.engine.manifest import ModuleManifest

from .schema import AnalysisResult

_API_KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_MODEL_ENV = "GEMINI_MODEL"
_DEFAULT_MODEL = "gemini-flash-latest"

_MAX_QUESTIONS = 10  # [1.1.3] 보완 질문 최대 개수 (고정값)
_REASON_MAX_CHARS = 30  # 추천 근거 한 줄 요약 길이 (체크박스 목록에서 안 잘리도록)

# 설명이 불충분할 때 쓰는 기본 보완 질문. LLM이 sufficient=False이면서 질문을 주지 않은 경우 사용.
_DEFAULT_CLARIFYING_QUESTIONS = [
    "어떤 종류의 서비스인가요? (예: 블로그, 쇼핑몰, 사내 도구)",
    "로그인/회원 기능이 필요한가요?",
    "데이터를 저장해야 하나요? 어떤 데이터인가요?",
]


class _ModuleReason(BaseModel):
    """_LLMSuggestion.reasons 항목 하나: 모듈명 + 추천 근거."""
    module: str
    reason: str


class _LLMSuggestion(BaseModel):
    """_call_llm의 구조화 출력 스키마. AnalysisResult와는 별개(모듈 밖 계약 아님).

    reasons는 dict[str, str]이 아니라 리스트로 받는다: Gemini Developer API의
    구조화 출력은 스키마에 additionalProperties(자유 형식 dict)를 허용하지 않는다.
    """
    sufficient: bool
    clarifying_questions: list[str] = Field(default_factory=list)
    recommended_modules: list[str] = Field(default_factory=list)
    reasons: list[_ModuleReason] = Field(default_factory=list)


# 입력: manifests(dict[str, ModuleManifest]) - 모듈명→매니페스트 매핑
# 출력: str - "- 이름 (카테고리): 설명" 형태로 정렬된 카탈로그 문자열
def _build_catalog(manifests: dict[str, ModuleManifest]) -> str:
    """모듈 카탈로그를 프롬프트에 주입할 문자열로 렌더링 ("- 이름 (카테고리): 설명" 형태)."""
    modules = sorted(manifests.values(), key=lambda m: m.name)
    return "\n".join(f"- {m.name} ({m.category}): {m.description}" for m in modules)


# 입력: description(str) - 사용자 자연어 설명, module_catalog(str) - _build_catalog 결과
# 출력: str - Gemini에 전달할 프롬프트 전문
def _build_prompt(description: str, module_catalog: str) -> str:
    """LLM에 전달할 프롬프트 텍스트를 생성."""
    return (
        "당신은 FastAPI 백엔드 스캐폴딩 도구의 모듈 추천 엔진입니다.\n\n"
        f"사용 가능한 모듈 목록:\n{module_catalog}\n\n"
        f'사용자 설명: "{description}"\n\n'
        "위 목록에 있는 모듈 중에서만 이 프로젝트에 필요한 모듈을 추천하세요. "
        "목록에 없는 이름은 추천하지 마세요. "
        "설명이 추천하기에 충분히 구체적이지 않다면 sufficient를 false로 하고 "
        f"최대 {_MAX_QUESTIONS}개의 한국어 보완 질문을 clarifying_questions에 담으세요. "
        "추천한 모듈에는 reasons에 한국어로 간단한 추천 근거를 함께 담으세요. "
        f"각 근거는 공백 포함 {_REASON_MAX_CHARS}자 이내의 한 줄 요약으로 쓰세요."
    )


# 입력: description(str) - 사용자 자연어 설명, module_catalog(str) - _build_catalog 결과
# 출력: _LLMSuggestion - Gemini 구조화 응답 (실패 시 예외 발생, 호출부 analyze()가 AIConnectionError로 변환)
def _call_llm(description: str, module_catalog: str) -> _LLMSuggestion:
    """[1.2.1] Gemini 호출. 실패 시 예외를 던진다."""

    api_key = next((os.environ[k] for k in _API_KEY_ENVS if os.environ.get(k)), None)

    if not api_key:
        raise RuntimeError(f"{'/'.join(_API_KEY_ENVS)} 환경변수가 설정되지 않았습니다.")

    from google import genai  # google-genai 패키지 미설치 환경을 지원하기 위한 지연 임포트
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.environ.get(_MODEL_ENV, _DEFAULT_MODEL)
    response = client.models.generate_content(
        model=model,
        contents=_build_prompt(description, module_catalog),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_LLMSuggestion,
            temperature=0.2,
        ),
    )
    if response.parsed is None:
        raise ValueError("Gemini 응답을 구조화된 형식으로 파싱하지 못했습니다.")
    return response.parsed


# 입력: picked(list[str]) - 추천된 모듈명 목록, reasons(dict[str, str]) - 모듈명→근거,
#       manifests(dict[str, ModuleManifest]) - 실존 모듈 검증용 매니페스트
# 출력: tuple[list[str], dict[str, str]] - (검증·필수모듈 보강된 모듈 목록, 근거 기본값 채운 딕셔너리)
def _sanitize(picked: list[str], reasons: dict[str, str],
              manifests: dict[str, ModuleManifest]) -> tuple[list[str], dict[str, str]]:
    """[1.2.3] 환각 모듈 제거 + 필수 모듈 보장 + 근거 기본값 채우기."""
    always = [m.name for m in manifests.values() if m.required]
    merged = always + [m for m in picked if m not in always]
    valid = [m for m in dict.fromkeys(merged) if m in manifests]
    out_reasons = {
        m: reasons.get(m) or f"설명에서 '{m}' 관련 요구가 감지되었습니다."
        for m in valid
    }
    return valid, out_reasons


# 입력: picked(list[str]) - 추천 모듈명, reasons(dict[str, str]) - 모듈명→근거,
#       manifests(dict[str, ModuleManifest]) - 매니페스트, sufficient(bool) - 정보 충분 여부,
#       questions(list[str]) - 보완 질문 목록
# 출력: AnalysisResult - _sanitize 적용 후 조립된 최종 분석 결과
def _finalize(picked: list[str], reasons: dict[str, str], manifests: dict[str, ModuleManifest],
              sufficient: bool, questions: list[str]) -> AnalysisResult:
    """_sanitize를 적용해 AnalysisResult로 조립."""
    valid, out_reasons = _sanitize(picked, reasons, manifests)
    return AnalysisResult(
        sufficient=sufficient,
        clarifying_questions=questions[:_MAX_QUESTIONS],
        recommended_modules=valid,
        reasons=out_reasons,
    )


# 입력: description(str) - 사용자 자연어 설명, manifests(dict[str, ModuleManifest]) - 매니페스트
# 출력: AnalysisResult - 분석 결과
# 예외: AIConnectionError - Gemini 호출 실패 시(키 없음·패키지 미설치·네트워크/파싱 오류 등)
def analyze(description: str, manifests: dict[str, ModuleManifest]) -> AnalysisResult:
    """[1.2.2] 분석 실행 → AnalysisResult 반환. Gemini 호출 실패 시 AIConnectionError를 던진다."""
    catalog = _build_catalog(manifests)
    try:
        suggestion = _call_llm(description, catalog)
    except Exception as e:
        raise AIConnectionError(str(e)) from e

    reasons_by_module = {r.module: r.reason for r in suggestion.reasons}
    questions = suggestion.clarifying_questions[:_MAX_QUESTIONS]
    if not suggestion.sufficient and not questions:
        questions = _DEFAULT_CLARIFYING_QUESTIONS

    return _finalize(
        suggestion.recommended_modules, reasons_by_module, manifests,
        suggestion.sufficient, questions,
    )
