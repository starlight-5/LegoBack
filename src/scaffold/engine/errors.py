"""[4.4.1] 공통 오류 형식. 모든 파트는 ScaffoldError를 사용한다."""


class ScaffoldError(Exception):
    """오류 코드 · 설명 · 조치를 담는 공통 예외."""

    def __init__(self, code: str, message: str, hint: str = ""):
        self.code = code
        self.hint = hint
        super().__init__(message)


class CircularDependencyError(ScaffoldError):
    """[2.2.2] 모듈 순환 의존성."""

    def __init__(self, cycle: list[str]):
        super().__init__(
            "E-CYCLE",
            f"모듈 순환 의존성 발견: {' → '.join(cycle)}",
            "모듈 제작자에게 manifest의 depends_on 수정을 요청하세요.",
        )


class DuplicateFileError(ScaffoldError):
    """[2.4.1] 두 모듈이 같은 도착 경로에 파일을 배달하려는 경우."""

    def __init__(self, dest: str, first: str, second: str):
        super().__init__(
            "E-DUPFILE",
            f"파일 경로 충돌: '{dest}' — {first} 모듈과 {second} 모듈이 같은 위치에 씁니다.",
            "두 모듈 중 하나의 manifest files.dest를 수정해야 합니다.",
        )


class OptionMismatchError(ScaffoldError):
    """[신규] 같은 옵션 이름인데 모듈마다 choices가 다른 경우."""

    def __init__(self, option: str, mod_a: str, choices_a: list[str], mod_b: str, choices_b: list[str]):
        super().__init__(
            "E-OPTMISMATCH",
            f"옵션 '{option}'의 선택지가 다릅니다: {mod_a}={choices_a} vs {mod_b}={choices_b}",
            "두 모듈의 manifest.yaml에서 options의 choices를 동일하게 맞춰주세요.",
        )


class UnknownWhenKeyError(ScaffoldError):
    """[신규] when 절이 참조하는 옵션 이름이 어느 모듈에도 선언되어 있지 않은 경우."""

    def __init__(self, module: str, key: str):
        super().__init__(
            "E-UNKNOWNWHEN",
            f"{module} 모듈의 when에 쓰인 옵션 '{key}'가 어느 모듈에도 선언되어 있지 않습니다.",
            "옵션 이름 오타를 확인하거나, 해당 옵션을 선언하는 모듈의 manifest.yaml에 options를 추가하세요.",
        )


class UnusedOptionError(ScaffoldError):
    """[신규] options로 선언됐지만 어느 when 절에서도 참조되지 않는 옵션."""

    def __init__(self, module: str, option: str):
        super().__init__(
            "E-UNUSEDOPT",
            f"{module} 모듈이 선언한 옵션 '{option}'을 참조하는 when 절이 어디에도 없습니다.",
            "해당 옵션을 사용하는 when 절을 추가하거나, 아직 쓸 곳이 없으면 options 선언을 지워주세요.",
        )


class AIConnectionError(ScaffoldError):
    """[1.2.1] Gemini 호출 실패 (키 없음·패키지 미설치·네트워크·파싱 오류 등)."""

    def __init__(self, reason: str):
        super().__init__(
            "E-AI",
            f"AI 연결에 실패했습니다: {reason}",
            "GEMINI_API_KEY 환경변수와 네트워크 연결 상태를 확인하세요.",
        )
