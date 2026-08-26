"""[2.3~2.5] 파일을 실제로 만드는 쓰기 단계.

원칙: 같은 입력이면 항상 같은 결과(결정적 출력). AI도 템플릿도 코드를
'창작'하지 않는다 — 검수된 파일을 복사하거나, manifest 값을 채워 넣을 뿐이다.
"""
from pathlib import Path
import secrets
import shutil

from jinja2 import Environment, FileSystemLoader
from packaging.requirements import Requirement
from packaging.version import Version

from .errors import DuplicateFileError
from .manifest import EnvVar, ModuleManifest, package_requirement

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
BASE_PACKAGES = ["fastapi>=0.115", "uvicorn[standard]>=0.30"]


def _env() -> Environment:
    """템플릿 파일(main.py.j2 등)을 읽어서 실제 코드로 채워 넣을 때 쓰는
    Jinja2 렌더링 도구를 준비한다.

    Returns:
        렌더링에 사용할 Jinja2 Environment.
    """
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _merge_specifiers(specifiers: list[str]) -> str:
    """여러 개의 버전 제약 조건(예: [">=2.0", ">=2.5"])을 실제로 pip에 넘길 수 있는
    문자열 하나로 합친다. 하한선은 가장 높은 값을, 상한선은 가장 낮은 값을 골라서
    합치면 모든 조건을 동시에 만족하는 가장 좁은 범위가 된다.

    Args:
        specifiers: 합칠 버전 제약 조건 문자열 목록.

    Returns:
        하나로 합쳐진 버전 제약 조건 문자열.
    """
    if not specifiers:
        return ""

    lower_bounds: list[tuple[str, Version]] = []
    upper_bounds: list[tuple[str, Version]] = []
    exact_versions: list[Version] = []
    for raw in specifiers:
        if raw.startswith(">="):
            lower_bounds.append((">=", Version(raw[2:])))
        elif raw.startswith(">"):
            lower_bounds.append((">", Version(raw[1:])))
        elif raw.startswith("<="):
            upper_bounds.append(("<=", Version(raw[2:])))
        elif raw.startswith("<"):
            upper_bounds.append(("<", Version(raw[1:])))
        elif raw.startswith("=="):
            exact_versions.append(Version(raw[2:]))
        else:
            return ",".join(sorted(specifiers))

    if exact_versions:
        if len(set(exact_versions)) != 1:
            return ""
        return f"=={exact_versions[0]}"

    parts: list[str] = []
    if lower_bounds:
        _, best = max(lower_bounds, key=lambda item: item[1])
        parts.append(f">={best}")
    if upper_bounds:
        op, best = min(upper_bounds, key=lambda item: item[1])
        parts.append(f"{op}{best}")
    return ",".join(parts)


def merge_packages(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[str]:
    """[2.4.2] 선택된 모듈들이 요구하는 pip 패키지를 전부 모아 하나의 목록으로 만든다.

    여러 모듈이 같은 패키지를 요구하면 중복으로 넣지 않고, 버전 범위를 교집합으로
    좁혀서 한 줄로 합친다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        병합된 pip 패키지 요구사항 문자열 목록.
    """
    merged: dict[str, list[str]] = {}
    for raw in BASE_PACKAGES:
        req = Requirement(raw)
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        key = req.name + extras
        merged.setdefault(key, []).extend(str(s) for s in req.specifier)
    for name in ordered:
        for raw in manifests[name].pip_packages:
            req = Requirement(package_requirement(raw))
            extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
            key = req.name + extras
            merged.setdefault(key, []).extend(str(s) for s in req.specifier)
    rendered: list[str] = []
    for pkg, specs in sorted(merged.items()):
        spec_str = _merge_specifiers(specs)
        if spec_str:
            rendered.append(f"{pkg}{spec_str}")
        else:
            rendered.append(pkg)
    return rendered


def create_skeleton(project_dir: Path, project_name: str,
                    ordered: list[str], manifests: dict[str, ModuleManifest]) -> None:
    """[2.3.1] 프로젝트의 최소 뼈대를 만든다. 모듈을 하나도 안 골라도 uvicorn으로
    바로 실행되고 /health가 200을 돌려주도록, main.py·pyproject.toml·README 등을
    기본으로 채워 넣는다.

    Args:
        project_dir: 생성할 프로젝트 경로.
        project_name: 프로젝트 이름.
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.
    """
    env = _env()
    routers = [r for name in ordered for r in manifests[name].routers]
    regs = []                                          # [선택2] 등록 함수 수집  ← 추가 1
    for name in ordered:
        for path in manifests[name].registrations:
            mod, fn = path.rsplit(".", 1)
            alias = mod.split(".")[-1] + "_" + fn
            regs.append({"mod": mod, "fn": fn, "alias": alias})

    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "tests").mkdir(parents=True, exist_ok=True)
    (project_dir / "logs").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "__init__.py").touch()

    (project_dir / "src" / "main.py").write_text(
        env.get_template("main.py.j2").render(
            project_name=project_name, routers=routers,
            registrations=regs),                       # ← 추가 2
        encoding="utf-8")
    (project_dir / "pyproject.toml").write_text(
        env.get_template("pyproject.toml.j2").render(
            project_name=project_name,
            packages=merge_packages(ordered, manifests)),
        encoding="utf-8")
    (project_dir / "README.md").write_text(
        env.get_template("README.md.j2").render(project_name=project_name, modules=ordered),
        encoding="utf-8")
    shutil.copyfile(TEMPLATES_DIR / "gitignore", project_dir / ".gitignore")
    shutil.copyfile(TEMPLATES_DIR / "test_health.py", project_dir / "tests" / "test_health.py")


def copy_module_files(project_dir: Path, ordered: list[str],
                      manifests: dict[str, ModuleManifest], modules_dir: Path) -> None:
    """[2.4.1] 각 모듈이 갖고 있는 검수된 코드 파일들을, manifest에 적힌 도착 경로로
    실제 복사한다.

    두 모듈이 같은 경로에 파일을 두려고 하면 조용히 덮어쓰지 않고 에러로 멈춘다.

    Args:
        project_dir: 생성할 프로젝트 경로.
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.
        modules_dir: 모듈 파일들이 위치한 디렉터리.

    Raises:
        DuplicateFileError: 두 모듈이 같은 도착 경로에 파일을 배달하려는 경우.
    """
    owner: dict[str, str] = {}
    for name in ordered:                     # 1차: 복사 전에 충돌 전체 선검사
        for fm in manifests[name].files:
            if fm.dest in owner:
                raise DuplicateFileError(fm.dest, owner[fm.dest], name)
            owner[fm.dest] = name
    services = {
        service_name: service
        for name in ordered
        for service_name, service in manifests[name].docker_services.items()
    }
    for name in ordered:                     # 2차: 검사 통과 후에만 복사 실행
        for fm in manifests[name].files:
            src = modules_dir / name / fm.src
            dest = project_dir / fm.dest
            dest.parent.mkdir(parents=True, exist_ok=True)   # 빈 폴더 미생성 원칙
            if fm.render:
                rendered = _env().from_string(src.read_text(encoding="utf-8")).render(
                    modules=ordered,
                    services=services,
                )
                dest.write_text(rendered, encoding="utf-8")
            else:
                shutil.copyfile(src, dest)


def write_env_file(project_dir: Path, pairs: list[tuple[str, EnvVar]]) -> None:
    """[2.4.3] .env 파일을 만든다. 각 변수 위에는 어떤 모듈이 왜 쓰는지 주석을 달고,
    JWT_SECRET_KEY처럼 사용자가 직접 채워야 하는 값은 빈 칸으로 두고 안내 문구를
    붙인다.

    Args:
        project_dir: 생성할 프로젝트 경로.
        pairs: (모듈명, 환경변수) 쌍 목록.
    """
    lines: list[str] = []
    for module, var in pairs:
        desc = var.description or "설명 없음"
        lines.append(f"# [{module}] {desc}")
        value = secrets.token_urlsafe(48) if var.generate == "secret" else var.default
        if value:
            lines.append(f"{var.name}={value}")
        else:
            lines.append(f"{var.name}=   # 여기에 값을 입력하세요")
        lines.append("")
    (project_dir / ".env").write_text("\n".join(lines), encoding="utf-8")


def _named_volumes(services: list[tuple[str, object]]) -> list[str]:
    """[신규] 서비스 volumes 중 이름 있는(named) 볼륨만 추출 (바인드 마운트 경로는 제외).

    compose 짧은 문법 "VOLUME:CONTAINER_PATH"에서 VOLUME이 "."나 "/"로 시작하지
    않으면 이름 있는 볼륨이고, docker compose는 이걸 최상단 volumes:에 선언하지
    않으면 "undefined volume"으로 거부한다.

    Args:
        services: (서비스명, DockerService) 쌍 목록.

    Returns:
        이름 있는 볼륨 이름 목록 (정렬됨).
    """
    names: set[str] = set()
    for _, svc in services:
        for v in svc.volumes:
            host_part = v.split(":", 1)[0]
            if not host_part.startswith((".", "/")):
                names.add(host_part)
    return sorted(names)


def write_docker(project_dir: Path, ordered: list[str],
                 manifests: dict[str, ModuleManifest],
                 compose_project_name: str | None = None) -> None:
    """[2.5] docker-compose.yml + Dockerfile. docker 모듈 선택 시에만 호출.

    compose_project_name을 주면 컴포즈 파일 최상단에 name:으로 박아, 폴더 이름이
    우연히 같은 다른 프로젝트와 Compose 프로젝트 네임스페이스(볼륨/네트워크 접두사)가
    겹치지 않게 한다.

    Args:
        project_dir: 생성할 프로젝트 경로.
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.
        compose_project_name: docker-compose.yml 최상단에 넣을 프로젝트 이름.
    """
    env = _env()
    # "database" 모듈 선택 여부가 아니라, 실제로 alembic.ini가 배달되는지(=SQL 계열
    # db_type)를 봐야 한다 — mongodb는 database 모듈이어도 alembic.ini/migrations가
    # 없어서, 모듈 이름만 보면 COPY/마운트 대상이 없는데 시도하다가 빌드가 깨진다.
    has_database = any(fm.dest == "alembic.ini" for name in ordered for fm in manifests[name].files)
    services: list[tuple[str, object]] = []
    for name in ordered:
        for svc_name, svc in sorted(manifests[name].docker_services.items()):
            services.append((svc_name, svc))
    (project_dir / "docker-compose.yml").write_text(
        env.get_template("docker-compose.yml.j2").render(
            services=services, named_volumes=_named_volumes(services),
            compose_project_name=compose_project_name, has_database=has_database),
        encoding="utf-8")
    (project_dir / "Dockerfile").write_text(
        env.get_template("Dockerfile.j2").render(has_database=has_database), encoding="utf-8")


def generate(project_dir: Path, project_name: str, ordered: list[str],
             manifests: dict[str, ModuleManifest], modules_dir: Path,
             env_pairs: list[tuple[str, EnvVar]]) -> None:
    """프로젝트 생성의 전체 흐름을 순서대로 실행한다: 뼈대 만들기 → 모듈 코드
    복사 → .env 쓰기 → (docker 모듈 선택 시) docker 설정까지. cli.run_init_flow가
    이 함수 하나만 호출하면 된다.

    Args:
        project_dir: 생성할 프로젝트 경로.
        project_name: 프로젝트 이름.
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.
        modules_dir: 모듈 파일들이 위치한 디렉터리.
        env_pairs: (모듈명, 환경변수) 쌍 목록.
    """
    create_skeleton(project_dir, project_name, ordered, manifests)
    copy_module_files(project_dir, ordered, manifests, modules_dir)
    write_env_file(project_dir, env_pairs)
    if "docker" in ordered:
        compose_project_name = f"{project_name}-{secrets.token_hex(3)}"
        write_docker(project_dir, ordered, manifests, compose_project_name=compose_project_name)
