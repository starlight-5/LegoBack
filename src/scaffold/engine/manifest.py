"""[2.2.1] manifest.yaml 스키마 (배달 명세서).

이 파일의 수정 권한은 엔진 파트(A)에만 있다. 필드 추가는 이슈로 요청.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

WhenClause = dict[str, list[str]]


def when_matches(when: WhenClause | None, option_answers: dict[str, str]) -> bool:
    """이 when 조건이 사용자가 고른 옵션 값과 맞는지 판정한다.

    when이 아예 없으면 항상 포함된다. 조건에 키가 여러 개면 전부 다 맞아야 하고
    (AND), 한 키 안의 값이 여러 개면 그중 하나만 맞아도 된다 (OR).

    Args:
        when: 조건절 (없으면 항상 매칭).
        option_answers: 옵션명→사용자 답변 매핑.

    Returns:
        조건이 사용자 답변과 매칭되면 True.
    """
    if not when:
        return True
    return all(option_answers.get(key) in values for key, values in when.items())


class FileMapping(BaseModel):
    """[2.4.1] 복사형 배달: 모듈 원본 → 생성 프로젝트 도착 경로."""
    src: str
    dest: str
    when: WhenClause | None = None
    render: bool = False


class EnvVar(BaseModel):
    """[2.2.3 → 2.4.3] 환경 변수 선언. default가 빈 값이면 사용자 입력 필요."""
    name: str
    default: str = ""
    description: str = ""
    when: WhenClause | None = None
    generate: Literal["secret"] | None = None


class RouterSpec(BaseModel):
    """[2.4.4] main.py에 등록할 라우터."""
    module: str            # 예: src.routers.auth
    attr: str = "router"   # 모듈 안의 라우터 변수명
    prefix: str = ""
    tag: str = ""
    when: WhenClause | None = None


class DockerService(BaseModel):
    """[2.5.1] docker-compose.yml에 들어갈 외부 서비스."""
    image: str
    ports: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)
    when: WhenClause | None = None


class PackageSpec(BaseModel):
    """[신규] 조건부 pip 패키지. 무조건 포함될 패키지는 그냥 문자열로 써도 된다."""
    spec: str               # PEP 508 요구사항 문자열, 예: motor>=3.3
    when: WhenClause | None = None


def package_requirement(pkg: "str | PackageSpec") -> str:
    """pip_packages 목록의 항목 하나를 받아서 실제 pip 요구사항 문자열을 꺼낸다.

    항목이 그냥 문자열("redis>=5.0")이면 그대로 쓰고, 조건부 패키지(PackageSpec)면
    그 안의 spec 값을 꺼내온다. when 조건 유무와 상관없이 항상 같은 형태로 쓰기
    위한 헬퍼다.

    Args:
        pkg: pip_packages 항목 (문자열 또는 PackageSpec).

    Returns:
        실제 pip 요구사항 문자열.
    """
    return pkg.spec if isinstance(pkg, PackageSpec) else pkg


class ModuleOption(BaseModel):
    """[신규] 모듈이 선언하는 단일 선택 옵션. 이름이 같은 옵션은 모듈 간에 질문이 하나로 합쳐진다."""
    question: str
    choices: list[str]
    default: str | None = None

    @field_validator("default")
    @classmethod
    def _default_in_choices(cls, v: str | None, info) -> str | None:
        """옵션의 default 값이 그 옵션의 choices 목록 안에 실제로 있는지 확인한다.

        예: choices가 [mysql, mongodb]인데 default를 postgresql로 적으면,
        고를 수도 없는 값을 기본값으로 지정한 셈이라 에러로 막는다.

        Args:
            v: 검증할 default 값.
            info: choices 등 다른 필드 값을 담은 pydantic ValidationInfo.

        Returns:
            검증을 통과한 default 값.

        Raises:
            ValueError: default 값이 choices에 없는 경우.
        """
        choices = info.data.get("choices") or []
        if v is not None and v not in choices:
            raise ValueError(f"default '{v}'가 choices {choices}에 없습니다.")
        return v


class ModuleManifest(BaseModel):
    """모듈 하나의 배달 명세서 전체."""
    name: str
    description: str = ""
    category: str = ""
    required: bool = False  # True면 항상 포함 — 체크박스 UI에서 해제 불가능하게 잠긴다.
    depends_on: list[str] = Field(default_factory=list)
    files: list[FileMapping] = Field(default_factory=list)
    pip_packages: list[str | PackageSpec] = Field(default_factory=list)
    env_vars: list[EnvVar] = Field(default_factory=list)
    routers: list[RouterSpec] = Field(default_factory=list)
    registrations: list[str] = Field(default_factory=list)
    # main.py에서 호출할 등록 함수 경로. 함수는 app 하나를 인자로 받아야 한다. [선택2 결정]
    # 예: ["src.core.cors.apply"]
    docker_services: dict[str, DockerService] = Field(default_factory=dict)
    options: dict[str, ModuleOption] = Field(default_factory=dict)  # 예: db_type
