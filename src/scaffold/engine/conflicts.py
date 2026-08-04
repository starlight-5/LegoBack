"""[3.1] 버전 충돌 검사 / [3.2] 기능 충돌 감지.

원칙: 여기는 '판정'만 한다. 통과한 조합만 병합(2.4)으로 넘어간다.
"""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


DEFAULT_VERSION_REASON = "교집합이 없어 자동 해결이 불가능합니다."
DEFAULT_ROUTE_REASON = "라우트 경로가 중복되어 충돌합니다."
DEFAULT_ENV_REASON = "환경변수 기본값이 서로 달라 충돌합니다."

from .manifest import EnvVar, ModuleManifest


@dataclass
class Conflict:
    kind: str          # version | env | route | schema
    subject: str       # 패키지명 / 변수명 / 경로
    detail: str
    modules: list[str] = field(default_factory=list)
    suggestion: str | None = None


def check_versions(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[Conflict]:
    """[3.1.1~3.1.2] 같은 패키지에 대한 버전 범위 교집합 검사 (SemVer 기준)."""
    wanted: dict[str, list[tuple[str, SpecifierSet]]] = {}
    for name in ordered:
        for raw in manifests[name].pip_packages:
            req = Requirement(raw)
            wanted.setdefault(req.name, []).append((name, req.specifier))

    conflicts: list[Conflict] = []
    for pkg, entries in wanted.items():
        if len(entries) < 2:
            continue
        merged = SpecifierSet()
        for _, spec in entries:
            merged &= spec

        pins = [s.version for _, spec in entries for s in spec if s.version]
        if pins and not any(merged.contains(v, prereleases=True) for v in pins):
            conflicts.append(Conflict(
                kind="version", subject=pkg,
                detail=(
                    f"{pkg}: " + " vs ".join(f"{m}({s or '*'})" for m, s in entries)
                    + f" | {DEFAULT_VERSION_REASON}"
                ),
                modules=[m for m, _ in entries],
            ))
    return conflicts


def check_env(pairs: list[tuple[str, EnvVar]]) -> list[Conflict]:
    """[3.2.2] 같은 변수명에 서로 다른 기본값 요구 감지."""
    seen: dict[str, tuple[str, str]] = {}
    conflicts: list[Conflict] = []
    for module, var in pairs:
        if var.name in seen:
            first_mod, first_default = seen[var.name]
            if first_default != var.default:
                conflicts.append(Conflict(
                    kind="env", subject=var.name,
                    detail=(
                        f"{var.name}: {first_mod}='{first_default}' vs {module}='{var.default}' | "
                        f"{DEFAULT_ENV_REASON}"
                    ),
                    modules=[first_mod, module],
                ))
        else:
            seen[var.name] = (module, var.default)
    return conflicts


def _join_route_path(prefix: str, path: str) -> str:
    normalized_prefix = prefix.rstrip("/") if prefix else ""
    normalized_path = path if path.startswith("/") else f"/{path}"
    if not normalized_prefix:
        return normalized_path
    return f"{normalized_prefix}{normalized_path}"


def _resolve_imported_module(module_name: str, router_file: Path, module_base_dir: Path | None) -> Path | None:
    if not module_name:
        return None
    if module_base_dir is not None:
        candidate = module_base_dir.joinpath(*module_name.split(".")).with_suffix(".py")
        if candidate.exists():
            return candidate
    candidate = router_file.parent / f"{module_name}.py"
    if candidate.exists():
        return candidate
    return None


def _collect_router_paths(router_file: Path, module_base_dir: Path | None = None, prefix: str = "") -> list[str]:
    """FastAPI router 파일에서 라우트와 include_router로 연결된 하위 라우터의 경로를 추출한다."""
    if not router_file.exists():
        return []

    try:
        tree = ast.parse(router_file.read_text(encoding="utf-8"), filename=str(router_file))
    except SyntaxError:
        return []

    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name

    paths: list[str] = []
    router_prefix = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "router" and isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            router_prefix = kw.value.value
                            break
            continue

        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue

        if func.value.id == "router" and func.attr in {"get", "post", "put", "patch", "delete"}:
            if node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    paths.append(_join_route_path(_join_route_path(prefix, router_prefix), arg.value))
            continue

        if func.value.id == "router" and func.attr == "include_router":
            include_prefix = router_prefix
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    include_prefix = kw.value.value
                    break
            if node.args and isinstance(node.args[0], ast.Name):
                imported_module = imports.get(node.args[0].id)
                if imported_module:
                    resolved = _resolve_imported_module(imported_module, router_file, module_base_dir)
                    if resolved:
                        paths.extend(_collect_router_paths(resolved, module_base_dir=module_base_dir,
                                                           prefix=_join_route_path(prefix, include_prefix)))
    return paths


def check_routes(ordered: list[str], manifests: dict[str, ModuleManifest], modules_dir: Path | None = None) -> list[Conflict]:
    """[3.2.1] prefix뿐 아니라 실제 등록 경로까지 비교해 충돌을 감지한다."""
    seen: dict[str, str] = {}
    conflicts: list[Conflict] = []

    for name in ordered:
        for r in manifests[name].routers:
            prefix = r.prefix.rstrip("/") if r.prefix else ""
            module_path = r.module.replace(".", "/")
            if modules_dir is not None:
                module_root = modules_dir / name / "files" / module_path
            else:
                module_root = Path(module_path)

            candidate_files = [module_root.with_suffix(".py")]
            if not candidate_files[0].exists():
                candidate_files.append(module_root / "__init__.py")

            paths: list[str] = []
            for candidate in candidate_files:
                module_base_dir = None
                if modules_dir is not None:
                    module_base_dir = modules_dir / name / "files"
                paths.extend(_collect_router_paths(candidate, module_base_dir=module_base_dir, prefix=prefix))

            if not paths and prefix:
                paths = [prefix]

            for full_path in paths:
                normalized_path = full_path if full_path.startswith("/") else f"/{full_path}"
                if normalized_path in seen:
                    existing_module = seen[normalized_path]
                    suggestion = (
                        f"{name} 모듈의 라우트 prefix를 바꾸거나, {existing_module} 모듈과 경로를 분리해 주세요."
                    )
                    conflicts.append(Conflict(
                        kind="route", subject=normalized_path,
                        detail=(
                            f"{normalized_path}: {existing_module} vs {name} | "
                            f"{DEFAULT_ROUTE_REASON}"
                        ),
                        modules=[existing_module, name],
                        suggestion=suggestion,
                    ))
                else:
                    seen[normalized_path] = name

            if not paths and prefix:
                seen[prefix] = name

    return conflicts


# TODO [3.2.3] DB 스키마 충돌 감지 — 모델 파일의 테이블명 수집 후 중복 검사
# TODO [3.3]   해결안 제시(prefix 변경, 변수 접두사 등) — CLI 파트와 협의 후 구현
