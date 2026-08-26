"""[4.4.1] 공통 오류 형식. 모든 파트는 ScaffoldError를 사용한다."""


class ScaffoldError(Exception):
    """legoback에서 나는 모든 에러의 부모 클래스. 에러 코드, 사용자에게 보여줄 설명,
    해결 방법 안내(hint)를 한 세트로 묶어서 던진다.

    Args:
        code: 에러를 구분하는 코드 (예: "E-CYCLE").
        message: 화면에 보여줄 에러 설명.
        hint: "이렇게 고치세요"에 해당하는 조치 안내.
    """

    def __init__(self, code: str, message: str, hint: str = ""):
        self.code = code
        self.hint = hint
        super().__init__(message)


class CircularDependencyError(ScaffoldError):
    """[2.2.2] 모듈끼리 서로를 의존해서 끝나지 않는 경우(순환 의존성)에 나는 에러.

    예: A가 B를 필요로 하는데 B도 A를 필요로 하면, 어느 걸 먼저 설치해야 할지
    정할 수 없다. 이런 경우를 미리 찾아내서 에러로 알려준다.

    Args:
        cycle: 순환을 이루는 모듈 이름들 (A → B → A 같은 순서).
    """

    def __init__(self, cycle: list[str]):
        super().__init__(
            "E-CYCLE",
            f"모듈 순환 의존성 발견: {' → '.join(cycle)}",
            "모듈 제작자에게 manifest의 depends_on 수정을 요청하세요.",
        )


class DuplicateFileError(ScaffoldError):
    """[2.4.1] 두 모듈이 똑같은 경로에 각자 파일을 놓으려고 할 때 나는 에러.

    가만히 두면 나중 모듈의 파일이 먼저 모듈의 파일을 덮어써버리기 때문에,
    조용히 덮어쓰는 대신 여기서 멈추고 알려준다.

    Args:
        dest: 겹친 도착 경로.
        first: 그 경로를 먼저 쓰겠다고 한 모듈명.
        second: 같은 경로를 나중에 또 쓰겠다고 한 모듈명.
    """

    def __init__(self, dest: str, first: str, second: str):
        super().__init__(
            "E-DUPFILE",
            f"파일 경로 충돌: '{dest}' — {first} 모듈과 {second} 모듈이 같은 위치에 씁니다.",
            "두 모듈 중 하나의 manifest files.dest를 수정해야 합니다.",
        )


class OptionMismatchError(ScaffoldError):
    """[신규] 여러 모듈이 같은 이름의 옵션(예: db_type)을 선언했는데, 고를 수 있는
    선택지가 모듈마다 다를 때 나는 에러.

    예: A 모듈은 db_type 선택지로 [mysql, mongodb]를 주고, B 모듈은 [mysql]만
    준다면 사용자가 mongodb를 골랐을 때 B 모듈이 어떻게 반응해야 할지 알 수 없다.

    Args:
        option: 선택지가 서로 다른 옵션 이름.
        mod_a: 먼저 그 옵션을 선언한 모듈명.
        choices_a: mod_a가 준 선택지 목록.
        mod_b: 같은 옵션을 다르게 선언한 모듈명.
        choices_b: mod_b가 준 선택지 목록.
    """

    def __init__(self, option: str, mod_a: str, choices_a: list[str], mod_b: str, choices_b: list[str]):
        super().__init__(
            "E-OPTMISMATCH",
            f"옵션 '{option}'의 선택지가 다릅니다: {mod_a}={choices_a} vs {mod_b}={choices_b}",
            "두 모듈의 manifest.yaml에서 options의 choices를 동일하게 맞춰주세요.",
        )


class UnknownWhenKeyError(ScaffoldError):
    """[신규] when 조건이 가리키는 옵션 이름이 실제로는 어디에도 선언돼 있지 않을 때
    나는 에러.

    대부분 오타 때문에 생긴다 (예: db_type이라고 써야 하는데 db_typ으로 씀).
    이걸 안 잡으면 오타 난 조건이 항상 매칭에 실패해서, 그 파일/설정이 아무도
    모르게 계속 빠지는 조용한 버그가 된다.

    Args:
        module: 오타 난 when 조건을 가진 모듈명.
        key: 어디에도 선언되지 않은 옵션 이름.
    """

    def __init__(self, module: str, key: str):
        super().__init__(
            "E-UNKNOWNWHEN",
            f"{module} 모듈의 when에 쓰인 옵션 '{key}'가 어느 모듈에도 선언되어 있지 않습니다.",
            "옵션 이름 오타를 확인하거나, 해당 옵션을 선언하는 모듈의 manifest.yaml에 options를 추가하세요.",
        )


class UnusedOptionError(ScaffoldError):
    """[신규] 모듈이 옵션(선택지)을 선언은 해놓고, 그 옵션을 실제로 쓰는 when 조건이
    어디에도 없을 때 나는 에러.

    이걸 안 잡으면 사용자한테 "뭘 고를지" 질문만 하나 더 뜨고, 뭘 골라도 결과가
    똑같은 쓸모없는 질문이 생긴다.

    Args:
        module: 옵션을 선언한 모듈명.
        option: 아무 데서도 안 쓰이는 옵션 이름.
    """

    def __init__(self, module: str, option: str):
        super().__init__(
            "E-UNUSEDOPT",
            f"{module} 모듈이 선언한 옵션 '{option}'을 참조하는 when 절이 어디에도 없습니다.",
            "해당 옵션을 사용하는 when 절을 추가하거나, 아직 쓸 곳이 없으면 options 선언을 지워주세요.",
        )


class AIConnectionError(ScaffoldError):
    """[1.2.1] Gemini(AI) 호출이 실패했을 때 나는 에러.

    API 키가 없거나, 필요한 패키지가 안 깔려 있거나, 네트워크가 끊기거나,
    응답을 제대로 못 읽는 등 원인은 다양한데, 호출하는 쪽에서는 이 에러 하나만
    잡으면 되도록 전부 이걸로 통일해서 던진다.

    Args:
        reason: 실패한 구체적인 이유.
    """

    def __init__(self, reason: str):
        super().__init__(
            "E-AI",
            f"AI 연결에 실패했습니다: {reason}",
            "GEMINI_API_KEY 환경변수와 네트워크 연결 상태를 확인하세요.",
        )
