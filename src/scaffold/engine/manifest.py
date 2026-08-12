"""[2.2.1] manifest.yaml 스키마 (배달 명세서).

이 파일의 수정 권한은 엔진 파트(A)에만 있다. 필드 추가는 이슈로 요청.
"""
from pydantic import BaseModel, Field, field_validator

WhenClause = dict[str, list[str]]


def when_matches(when: WhenClause | None, option_answers: dict[str, str]) -> bool:
    """[신규] when 조건이 사용자의 옵션 답변과 맞는지 판정.

    when이 없으면 항상 포함. dict의 키 여러 개는 AND, 한 키의 리스트 값은 OR로 매칭된다. 
    오타방지.
    """
    if not when:
        return True
    return all(option_answers.get(key) in values for key, values in when.items())


class FileMapping(BaseModel):
    """[2.4.1] 복사형 배달: 모듈 원본 → 생성 프로젝트 도착 경로."""
    src: str
    dest: str
    when: WhenClause | None = None


class EnvVar(BaseModel):
    """[2.2.3 → 2.4.3] 환경 변수 선언. default가 빈 값이면 사용자 입력 필요."""
    name: str
    default: str = ""
    description: str = ""
    when: WhenClause | None = None


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
    """[신규] pip_packages 항목(문자열 또는 PackageSpec)에서 실제 요구사항 문자열을 꺼낸다."""
    return pkg.spec if isinstance(pkg, PackageSpec) else pkg


class ModuleOption(BaseModel):
    """[신규] 모듈이 선언하는 단일 선택 옵션. 이름이 같은 옵션은 모듈 간에 질문이 하나로 합쳐진다."""
    question: str
    choices: list[str]
    default: str | None = None

    @field_validator("default")
    @classmethod
    def _default_in_choices(cls, v: str | None, info) -> str | None:
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
