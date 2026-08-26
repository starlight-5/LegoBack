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
_DEFAULT_MODEL = "gemini-3.1-flash-lite"

_MAX_QUESTIONS = 10  # [1.1.3] 보완 질문 최대 개수 (고정값)
_REASON_MAX_CHARS = 30  # 추천 근거 한 줄 요약 길이 (체크박스 목록에서 안 잘리도록)

# 설명이 불충분할 때 쓰는 기본 보완 질문. LLM이 sufficient=False이면서 질문을 주지 않은 경우 사용.
_DEFAULT_CLARIFYING_QUESTIONS = [
    "어떤 종류의 서비스인가요? (예: 블로그, 쇼핑몰, 사내 관리 도구, 모바일 앱 백엔드)",
    "회원가입/로그인 기능이 필요한가요? 필요하다면 관리자와 일반 사용자 권한도 구분해야 하나요?",
    "DB에 저장할 데이터가 있나요? 있다면 어떤 데이터인가요? (예: 게시글, 주문 내역, 상품 재고)",
    "프론트엔드(웹/앱)를 별도로 만들어 이 API를 호출하나요, 아니면 서버에서 화면까지 함께 제공하나요?",
]


class _ModuleReason(BaseModel):
    """_LLMSuggestion.reasons 항목 하나: 모듈명 + 추천 근거."""
    module: str
    reason: str


class _LLMSuggestion(BaseModel):
    """Gemini에게 이 형식으로 답하라고 요청하는 구조화 출력 스키마.
    AnalysisResult와는 별개다 (이 파일 밖에서는 안 쓰는 내부 계약).

    reasons를 dict[str, str]이 아니라 리스트로 받는 이유: Gemini Developer API의
    구조화 출력은 스키마에 자유 형식 dict(additionalProperties)를 허용하지 않는다.
    """
    sufficient: bool
    clarifying_questions: list[str] = Field(default_factory=list)
    recommended_modules: list[str] = Field(default_factory=list)
    reasons: list[_ModuleReason] = Field(default_factory=list)


def _build_catalog(manifests: dict[str, ModuleManifest]) -> str:
    """등록된 모듈 목록을, AI 프롬프트에 넣을 수 있는 "- 이름 (카테고리): 설명"
    형태의 카탈로그 문자열로 바꾼다.

    Args:
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        이름순으로 정렬된 카탈로그 문자열.
    """
    modules = sorted(manifests.values(), key=lambda m: m.name)
    return "\n".join(f"- {m.name} ({m.category}): {m.description}" for m in modules)


def _build_prompt(description: str, module_catalog: str) -> str:
    """사용자 설명과 모듈 카탈로그를 합쳐서, Gemini에게 보낼 프롬프트 전문을 만든다.

    Args:
        description: 사용자가 입력한 자연어 설명.
        module_catalog: _build_catalog가 만든 카탈로그 문자열.

    Returns:
        Gemini에 전달할 프롬프트 전문.
    """
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


def _call_llm(description: str, module_catalog: str) -> _LLMSuggestion:
    """[1.2.1] Gemini API를 실제로 호출해서 모듈 추천을 받아온다.

    API 키가 없거나, 패키지가 안 깔려 있거나, 응답을 구조화된 형식으로 못
    읽으면 예외를 던진다 — 여기서 직접 처리하지 않고, 호출한 쪽인 analyze()가
    받아서 AIConnectionError 하나로 통일해서 다시 던진다.

    Args:
        description: 사용자가 입력한 자연어 설명.
        module_catalog: _build_catalog가 만든 카탈로그 문자열.

    Returns:
        Gemini의 구조화 응답.

    Raises:
        RuntimeError: API 키 환경변수가 설정되지 않은 경우.
        ValueError: Gemini 응답을 구조화된 형식으로 파싱하지 못한 경우.
    """

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


def _sanitize(picked: list[str], reasons: dict[str, str],
              manifests: dict[str, ModuleManifest]) -> tuple[list[str], dict[str, str]]:
    """[1.2.3] AI가 추천한 목록을 실제로 써도 되는 상태로 정리한다.

    실제로 존재하지 않는 모듈(환각)은 걸러내고, 항상 포함돼야 하는 필수 모듈은
    AI가 빠뜨렸어도 강제로 넣어주고, 근거가 없는 모듈에는 기본 문구를 채워준다.

    Args:
        picked: AI가 추천한 모듈명 목록.
        reasons: 모듈명→추천 근거 매핑.
        manifests: 실존 모듈 검증에 쓸 매니페스트.

    Returns:
        (검증·필수모듈 보강된 모듈 목록, 근거 기본값이 채워진 매핑) 쌍.
    """
    always = [m.name for m in manifests.values() if m.required]
    merged = always + [m for m in picked if m not in always]
    valid = [m for m in dict.fromkeys(merged) if m in manifests]
    out_reasons = {
        m: reasons.get(m) or f"설명에서 '{m}' 관련 요구가 감지되었습니다."
        for m in valid
    }
    return valid, out_reasons


def _finalize(picked: list[str], reasons: dict[str, str], manifests: dict[str, ModuleManifest],
              sufficient: bool, questions: list[str]) -> AnalysisResult:
    """_sanitize로 정리한 결과를, 이 파일 밖에서 쓰는 공식 결과 타입인
    AnalysisResult로 조립한다.

    Args:
        picked: AI가 추천한 모듈명 목록.
        reasons: 모듈명→추천 근거 매핑.
        manifests: 실존 모듈 검증에 쓸 매니페스트.
        sufficient: 설명이 추천하기에 충분했는지 여부.
        questions: 보완 질문 목록.

    Returns:
        조립된 최종 분석 결과.
    """
    valid, out_reasons = _sanitize(picked, reasons, manifests)
    return AnalysisResult(
        sufficient=sufficient,
        clarifying_questions=questions[:_MAX_QUESTIONS],
        recommended_modules=valid,
        reasons=out_reasons,
    )


def analyze(description: str, manifests: dict[str, ModuleManifest]) -> AnalysisResult:
    """[1.2.2] 사용자 설명을 분석해 모듈을 추천한다. 이 파일 밖에서는 이 함수만
    쓰면 된다.

    내부적으로 Gemini를 호출하는데, 어떤 이유로든(키 없음, 네트워크 오류,
    파싱 실패 등) 실패하면 원인이 무엇이든 전부 AIConnectionError 하나로
    통일해서 던진다 — 호출하는 쪽은 이 예외 하나만 잡으면 된다.

    Args:
        description: 사용자가 입력한 자연어 설명.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        추천 모듈·근거·보완 질문이 담긴 분석 결과.

    Raises:
        AIConnectionError: Gemini 호출이 실패한 경우.
    """
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
