"""[2.3~2.5] 파일을 실제로 만드는 쓰기 단계.

원칙: 같은 입력이면 항상 같은 결과(결정적 출력). AI도 템플릿도 코드를
'창작'하지 않는다 — 검수된 파일을 복사하거나, manifest 값을 채워 넣을 뿐이다.
"""
from pathlib import Path
import shutil

from jinja2 import Environment, FileSystemLoader
from packaging.requirements import Requirement

from .errors import DuplicateFileError
from .manifest import EnvVar, ModuleManifest

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
BASE_PACKAGES = ["fastapi>=0.115", "uvicorn[standard]>=0.30"]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def merge_packages(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[str]:
    """[2.4.2] pip_packages 병합: 중복 제거, 같은 패키지의 버전 범위는 결합."""
    merged: dict[str, set[str]] = {}
    for raw in BASE_PACKAGES:
        req = Requirement(raw)
        merged.setdefault(req.name, set()).update(str(s) for s in req.specifier)
    for name in ordered:
        for raw in manifests[name].pip_packages:
            req = Requirement(raw)
            extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
            merged.setdefault(req.name + extras, set()).update(str(s) for s in req.specifier)
    return [pkg + ",".join(sorted(specs)) for pkg, specs in sorted(merged.items())]


def create_skeleton(project_dir: Path, project_name: str,
                    ordered: list[str], manifests: dict[str, ModuleManifest]) -> None:
    """[2.3.1] 최소 뼈대: 모듈 0개여도 uvicorn 구동 + /health 200."""
    env = _env()
    routers = [r for name in ordered for r in manifests[name].routers]
    (project_dir / "src").mkdir(parents=True, exist_ok=True)
    (project_dir / "tests").mkdir(parents=True, exist_ok=True)
    (project_dir / "src" / "__init__.py").touch()

    (project_dir / "src" / "main.py").write_text(
        env.get_template("main.py.j2").render(project_name=project_name, routers=routers),
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


def write_docker(project_dir: Path, ordered: list[str],
                 manifests: dict[str, ModuleManifest]) -> None:
    """[2.5] docker-compose.yml + Dockerfile. docker 모듈 선택 시에만 호출."""
    env = _env()
    services: list[tuple[str, object]] = []
    for name in ordered:
        for svc_name, svc in sorted(manifests[name].docker_services.items()):
            services.append((svc_name, svc))
    (project_dir / "docker-compose.yml").write_text(
        env.get_template("docker-compose.yml.j2").render(services=services),
        encoding="utf-8")
    (project_dir / "Dockerfile").write_text(
        env.get_template("Dockerfile.j2").render(), encoding="utf-8")


def generate(project_dir: Path, project_name: str, ordered: list[str],
             manifests: dict[str, ModuleManifest], modules_dir: Path,
             env_pairs: list[tuple[str, EnvVar]]) -> None:
    """전체 생성 파이프라인 실행. cli.run_init_flow[4.1.4]가 호출한다."""
    create_skeleton(project_dir, project_name, ordered, manifests)
    copy_module_files(project_dir, ordered, manifests, modules_dir)
    write_env_file(project_dir, env_pairs)
    if "docker" in ordered:
        write_docker(project_dir, ordered, manifests)
