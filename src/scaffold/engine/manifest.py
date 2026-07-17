"""[2.2.1] manifest.yaml 스키마 (배달 명세서).

이 파일의 수정 권한은 엔진 파트(A)에만 있다. 필드 추가는 이슈로 요청.
"""
from pydantic import BaseModel, Field


class FileMapping(BaseModel):
    """[2.4.1] 복사형 배달: 모듈 원본 → 생성 프로젝트 도착 경로."""
    src: str
    dest: str


class EnvVar(BaseModel):
    """[2.2.3 → 2.4.3] 환경 변수 선언. default가 빈 값이면 사용자 입력 필요."""
    name: str
    default: str = ""
    description: str = ""


class RouterSpec(BaseModel):
    """[2.4.4] main.py에 등록할 라우터."""
    module: str            # 예: src.routers.auth
    attr: str = "router"   # 모듈 안의 라우터 변수명
    prefix: str = ""
    tag: str = ""


class DockerService(BaseModel):
    """[2.5.1] docker-compose.yml에 들어갈 외부 서비스."""
    image: str
    ports: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    volumes: list[str] = Field(default_factory=list)


class ModuleManifest(BaseModel):
    """모듈 하나의 배달 명세서 전체."""
    name: str
    description: str = ""
    category: str = ""
    depends_on: list[str] = Field(default_factory=list)
    files: list[FileMapping] = Field(default_factory=list)
    pip_packages: list[str] = Field(default_factory=list)
    env_vars: list[EnvVar] = Field(default_factory=list)
    routers: list[RouterSpec] = Field(default_factory=list)
    registrations: list[str] = Field(default_factory=list)
    # main.py에서 호출할 등록 함수 경로. 함수는 app 하나를 인자로 받아야 한다. [선택2 결정]
    # 예: ["src.core.cors.apply"]
    docker_services: dict[str, DockerService] = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)   # [회의 안건] 예: db_type