"""[1.2.1] Gemini 호출 실패 → AIConnectionError 변환 검증. 실제 네트워크 호출은 하지 않는다."""
import pytest

from scaffold.ai import recommender
from scaffold.engine.errors import AIConnectionError


def test_analyze_raises_aiconnectionerror_when_no_api_key(monkeypatch):
    """키가 아예 없는 경우는 _call_llm이 네트워크 호출 전에 RuntimeError를 던지는 실제 경로."""
    # Arrange
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    # Act
    with pytest.raises(AIConnectionError) as exc_info:
        recommender.analyze("블로그 만들고 싶어", {})

    # Assert
    assert exc_info.value.code == "E-AI"
    assert "GEMINI_API_KEY" in str(exc_info.value)


def test_analyze_wraps_any_call_llm_failure_into_aiconnectionerror(monkeypatch):
    """네트워크/파싱 등 _call_llm에서 나는 임의의 예외도 항상 AIConnectionError로 변환되는지."""
    # Arrange
    def _boom(description, catalog):
        raise TimeoutError("네트워크 타임아웃")
    monkeypatch.setattr(recommender, "_call_llm", _boom)

    # Act
    with pytest.raises(AIConnectionError) as exc_info:
        recommender.analyze("아무 설명", {})

    # Assert
    assert "네트워크 타임아웃" in str(exc_info.value)
