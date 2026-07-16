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
