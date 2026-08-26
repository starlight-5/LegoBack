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

from scaffold.engine.manifest import EnvVar, ModuleManifest, RouterSpec, package_requirement

@dataclass
class Conflict:
    kind: str          # version | env | route | schema
    subject: str       # 패키지명 / 변수명 / 경로
    detail: str        # 상세 설명
    modules: list[str] = field(default_factory=list) # 충돌이 발생한 모듈 목록
    suggestion: str | None = None # 해결 제안


def check_versions(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[Conflict]:
    """[3.1.1~3.1.2] 여러 모듈이 같은 패키지를 서로 다른 버전 범위로 요구할 때,
    그 범위들이 겹치는 부분(교집합)이 있는지 확인한다.

    예: A는 pydantic>=2.0을, B는 pydantic<2.0을 요구하면 겹치는 버전이 하나도
    없으니 충돌로 판정한다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        패키지 버전 범위가 교집합을 이루지 못한 충돌 목록.
    """
    wanted: dict[str, list[tuple[str, SpecifierSet]]] = {} #패키지를 사용하는 모듈명과 버전
    for name in ordered:
        for raw in manifests[name].pip_packages:
            req = Requirement(package_requirement(raw))
            wanted.setdefault(req.name, []).append((name, req.specifier))
    conflicts: list[Conflict] = []
    for pkg, entries in wanted.items():
        if len(entries) < 2:
            continue
        merged = SpecifierSet()
        for _, spec in entries:
            merged &= spec
        pins = [s.version for _, spec in entries for s in spec]
        #교집합 없시 충돌시
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
    """[3.2.2] 두 모듈이 같은 이름의 환경변수를 쓰는데 기본값이 서로 다르면 충돌로 판정한다.

    예: A는 PORT의 기본값을 8000으로, B는 9000으로 두면 어느 값을 써야 할지
    알 수 없으므로 충돌로 잡는다.

    Args:
        pairs: (모듈명, 환경변수) 쌍 목록.

    Returns:
        같은 변수명에 기본값이 다른 충돌 목록.
    """
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
    """prefix와 path를 이어붙여 하나의 URL 경로로 만든다.

    예: prefix="/api/v1", path="users" → "/api/v1/users".

    Args:
        prefix: 라우터 prefix.
        path: 개별 라우트 경로.

    Returns:
        prefix와 path를 이어붙인 전체 경로.
    """
    normalized_prefix = prefix.rstrip("/") if prefix else ""
    normalized_path = path if path.startswith("/") else f"/{path}"
    #파싱 작업.
    if not normalized_prefix:
        return normalized_path
    return f"{normalized_prefix}{normalized_path}"


def _resolve_imported_module(module_name: str, router_file: Path, module_base_dir: Path | None) -> Path | None:
    """코드에서 import한 모듈 이름(예: src.routers.inner)이 실제로 디스크의 어느
    파일을 가리키는지 찾아낸다.

    모듈 기준 디렉터리에서 먼저 찾아보고, 못 찾으면 라우터 파일과 같은 폴더에서도
    찾아본다.

    Args:
        module_name: import된 모듈명.
        router_file: 이를 import한 라우터 파일 경로.
        module_base_dir: 모듈 파일들의 기준 디렉터리.

    Returns:
        실제로 존재하는 모듈 파일 경로 (찾지 못하면 None).
    """
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


def _extract_imports(tree: ast.AST) -> dict[str, str]:
    """코드 안의 import 구문을 전부 훑어서, 코드에서 쓰는 이름(alias)이 실제로
    어느 모듈을 가리키는지 표로 만든다.

    예: `from src.routers.inner import router as inner_router`가 있으면
    {"inner_router": "src.routers.inner"}가 된다.

    Args:
        tree: 파싱된 모듈 AST.

    Returns:
        import alias(또는 이름) 대 모듈 경로 매핑.
    """
    #import는 특정 모듈을 가져오는게 아니기에 importfrom과 나누어서 등록.
    #해당 파일의 import한 모듈을 저장한다. 키: asname 또는 name, 값: 모듈명.
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
    return imports


def _extract_router_prefix(tree: ast.AST) -> str:
    """코드에서 `router = APIRouter(prefix="...")`처럼 선언할 때 준 prefix 값을 찾아낸다.

    이렇게 prefix를 안 줬으면 빈 문자열을 반환한다.

    Args:
        tree: 파싱된 모듈 AST.

    Returns:
        추출한 prefix (없으면 빈 문자열).
    """
    # ast.walk는 BFS(레벨 순회)라 모듈 최상위 Assign이 @router.get(...) 데코레이터(더 깊은 노드)보다
    # 항상 먼저 방문된다. 그래서 이 전체 순회 결과(마지막으로 매칭된 할당값)는 기존의 인라인 처리와 동일하다.
    router_prefix = ""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets: #node.targets의 원소는 node.targets.name이다.
            if isinstance(target, ast.Name) and target.id == "router":
                if isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            router_prefix = kw.value.value
                            break
    return router_prefix


def _parse_api_route(node: ast.Call) -> str | None:
    """코드의 함수 호출 하나를 보고, `router.get("/users")`처럼 라우트를 등록하는
    호출이면 그 경로 문자열을 꺼내온다. 그런 호출이 아니면 None을 반환한다.

    Args:
        node: router.get/post/put/patch/delete 호출 후보 노드.

    Returns:
        등록된 raw 경로 (해당 호출이 아니면 None).
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    if func.value.id != "router" or func.attr not in {"get", "post", "put", "patch", "delete"}:
        return None
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _parse_include_router(node: ast.Call, imports: dict[str, str], default_prefix: str) -> tuple[str, str] | None:
    """코드의 함수 호출 하나를 보고, `router.include_router(...)`처럼 다른 라우터를
    통째로 가져다 붙이는 호출이면 어느 모듈을 가져왔는지와 적용될 prefix를 함께
    꺼내온다. 그런 호출이 아니면 None을 반환한다.

    Args:
        node: router.include_router 호출 후보 노드.
        imports: alias 대 모듈 경로 매핑.
        default_prefix: kwarg로 prefix가 없을 때 사용할 기본값(router_prefix).

    Returns:
        (하위 라우터 모듈 경로, include prefix). 해당 호출이 아니면 None.
    """
    func = node.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    if func.value.id != "router" or func.attr != "include_router":
        return None

    include_prefix = default_prefix
    for kw in node.keywords:
        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            include_prefix = kw.value.value
            break

    if not node.args or not isinstance(node.args[0], ast.Name):
        return None
    imported_module = imports.get(node.args[0].id)
    if not imported_module:
        return None
    return imported_module, include_prefix


def _collect_router_paths(router_file: Path, module_base_dir: Path | None = None, prefix: str = "") -> list[str]:
    """라우터 파일 하나를 읽어서 거기에 등록된 모든 경로를 찾아낸다.

    `include_router`로 연결된 하위 라우터가 있으면 그 안까지 따라 들어가서
    경로를 전부 모은다.

    Args:
        router_file: 파싱할 라우터 파일.
        module_base_dir: 하위 모듈 탐색 기준 디렉터리.
        prefix: 상위에서 내려온 경로 prefix.

    Returns:
        이 라우터(및 include_router로 연결된 하위 라우터 포함)에 등록된 전체 경로 목록.
    """
    if not router_file.exists():
        return []

    try:
        tree = ast.parse(router_file.read_text(encoding="utf-8"), filename=str(router_file))
    except SyntaxError:
        return []

    imports = _extract_imports(tree)
    router_prefix = _extract_router_prefix(tree)

    paths: list[str] = []
    for node in ast.walk(tree):
        #@router.get("/path"),하위 라우터 연결@router.include_router("modules.module_name")은 call 속성이 있다.
        #call이 아니면 패스한다.
        if not isinstance(node, ast.Call):
            continue

        route_path = _parse_api_route(node)
        if route_path is not None:
            paths.append(_join_route_path(_join_route_path(prefix, router_prefix), route_path)) # 예시auth/login

            # !!경고:코드와 매니페스트에 둘다 prefix를 작성하면 경로가 중첩됩니다.
            if prefix and router_prefix:
                print(f"[경고] {router_file.name}: 매니페스트 prefix({prefix})와 코드 prefix({router_prefix})가 둘다 기재되어 경로가 {prefix}{router_prefix}로 등록됩니다.")
            continue

        included = _parse_include_router(node, imports, router_prefix)
        if included is not None:
            imported_module, include_prefix = included
            resolved = _resolve_imported_module(imported_module, router_file, module_base_dir)
            if resolved:
                paths.extend(_collect_router_paths(resolved, module_base_dir=module_base_dir,
                                                   prefix=_join_route_path(prefix, include_prefix)))
            continue

    return paths


def _resolve_candidate_files(name: str, r: RouterSpec, modules_dir: Path | None) -> tuple[list[Path], Path | None]:
    """manifest에 적힌 라우터 모듈 경로(예: src.routers.auth)를, 실제로 있을 법한
    파일 경로들(auth.py 또는 auth/__init__.py)로 바꿔준다.

    Args:
        name: 모듈명.
        r: 모듈의 라우터 사양.
        modules_dir: 모듈 파일들이 위치한 디렉터리.

    Returns:
        검사할 후보 파일 목록과 하위 모듈 탐색 기준 디렉터리.
    """
    module_path = r.module.replace(".", "/")
    module_base_dir = None
    #참고 : modules_dir = legoback/modules
    # module_path는 각 모듈의 manifest의 routers의 module의 경로 (예: user.router.auth.v1 -> user/router/auth/v1)
    if modules_dir is not None:
        module_base_dir = modules_dir / name / "files"
        module_root = module_base_dir / module_path
    else:
        module_root = Path(module_path)
    # candidate_files는 모듈 파일이 실제로 있는 파일들임
    # 라우터 파일인 경우 .py 파일을 candidate_files에 추가
    # module_root가 디렉터리인 경우 __init__.py 파일을 candidate_files에 추가
    candidate_files = [module_root.with_suffix(".py")]
    if not candidate_files[0].exists():
        candidate_files.append(module_root / "__init__.py")
    return candidate_files, module_base_dir


def check_routes(ordered: list[str], manifests: dict[str, ModuleManifest], modules_dir: Path | None = None) -> list[Conflict]:
    """[3.2.1] 모듈들이 등록하는 라우트 경로가 서로 겹치는지 검사한다.

    manifest에 적힌 prefix만 비교하지 않고, 실제 라우터 코드를 읽어서 최종적으로
    등록되는 전체 경로까지 비교하기 때문에 더 정확하다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.
        modules_dir: 모듈 파일들이 위치한 디렉터리.

    Returns:
        실제 등록 경로가 중복되는 라우트 충돌 목록.
    """
    seen: dict[str, str] = {}
    conflicts: list[Conflict] = []

    for name in ordered:
        for r in manifests[name].routers:
            prefix = r.prefix.rstrip("/") if r.prefix else ""
            candidate_files, module_base_dir = _resolve_candidate_files(name, r, modules_dir)

            paths: list[str] = []
            for candidate in candidate_files:
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
    return conflicts
