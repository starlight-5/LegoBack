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
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _merge_specifiers(specifiers: list[str]) -> str:
    """버전 제약 조건을 하나의 현실적인 문자열로 합친다."""
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
        _, best = min(upper_bounds, key=lambda item: item[1])
        parts.append(f"<={best}")
    return ",".join(parts)


def merge_packages(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[str]:
    """[2.4.2] pip_packages 병합: 같은 패키지의 버전 범위는 교집합으로 정리한다."""
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
    """[2.3.1] 최소 뼈대: 모듈 0개여도 uvicorn 구동 + /health 200."""
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
    """[2.4.1] 검수 코드를 지정 경로로 복사. 경로 충돌은 덮어쓰지 않고 에러."""
    owner: dict[str, str] = {}
    for name in ordered:                     # 1차: 복사 전에 충돌 전체 선검사
        for fm in manifests[name].files:
            if fm.dest in owner:
                raise DuplicateFileError(fm.dest, owner[fm.dest], name)
            owner[fm.dest] = name
    for name in ordered:                     # 2차: 검사 통과 후에만 복사 실행
        for fm in manifests[name].files:
            src = modules_dir / name / fm.src
            dest = project_dir / fm.dest
            dest.parent.mkdir(parents=True, exist_ok=True)   # 빈 폴더 미생성 원칙
            shutil.copyfile(src, dest)


def write_env_file(project_dir: Path, pairs: list[tuple[str, EnvVar]]) -> None:
    """[2.4.3] 용도 주석이 달린 .env 생성. 외부 비밀값은 빈 값 + 안내."""
    lines: list[str] = []
    for module, var in pairs:
        desc = var.description or "설명 없음"
        lines.append(f"# [{module}] {desc}")
        if var.default:
            lines.append(f"{var.name}={var.default}")
        else:
            lines.append(f"{var.name}=   # 여기에 값을 입력하세요")
        lines.append("")
    (project_dir / ".env").write_text("\n".join(lines), encoding="utf-8")


def _named_volumes(services: list[tuple[str, object]]) -> list[str]:
    """[신규] 서비스 volumes 중 이름 있는(named) 볼륨만 추출 (바인드 마운트 경로는 제외).

    compose 짧은 문법 "VOLUME:CONTAINER_PATH"에서 VOLUME이 "."나 "/"로 시작하지
    않으면 이름 있는 볼륨이고, docker compose는 이걸 최상단 volumes:에 선언하지
    않으면 "undefined volume"으로 거부한다.
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
    """
    env = _env()
    has_database = "database" in ordered
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
    """전체 생성 파이프라인 실행. cli.run_init_flow[4.1.4]가 호출한다."""
    create_skeleton(project_dir, project_name, ordered, manifests)
    copy_module_files(project_dir, ordered, manifests, modules_dir)
    write_env_file(project_dir, env_pairs)
    if "docker" in ordered:
        compose_project_name = f"{project_name}-{secrets.token_hex(3)}"
        write_docker(project_dir, ordered, manifests, compose_project_name=compose_project_name)
