"""[2.2.2] 의존성 그래프: 자동 포함 · 순환 감지 · 위상 정렬.
[2.2.3] 설정값 추출: 환경 변수 수집 (파일 쓰기는 generator 소관).
"""
from graphlib import CycleError, TopologicalSorter

from .errors import CircularDependencyError, ScaffoldError
from .manifest import EnvVar, ModuleManifest, ModuleOption, when_matches


def resolve(selected: list[str], manifests: dict[str, ModuleManifest]) -> list[str]:
    """선택 모듈에서 depends_on을 따라 전체 집합을 모으고 처리 순서를 반환.

    반환 순서: 의존받는 쪽 먼저 (예: settings -> database -> jwt-auth).
    """
    graph: dict[str, list[str]] = {}
    stack = sorted(selected)                      # 정렬: 결정적 출력 보장
    while stack:
        name = stack.pop()
        if name in graph:
            continue
        if name not in manifests:
            raise ScaffoldError(
                "E-UNKNOWN", f"존재하지 않는 모듈: '{name}'",
                "modules/ 폴더의 모듈 이름을 확인하세요.",
            )
        deps = sorted(manifests[name].depends_on)
        graph[name] = deps
        stack.extend(deps)
    try:
        return list(TopologicalSorter(graph).static_order())
    except CycleError as e:
        raise CircularDependencyError(list(e.args[1])) from e


def collect_env(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[tuple[str, EnvVar]]:
    """[2.2.3] (모듈명, EnvVar) 목록 수집. 충돌 검사(3.2.2)의 입력이 된다."""
    out: list[tuple[str, EnvVar]] = []
    for name in ordered:
        for var in manifests[name].env_vars:
            out.append((name, var))
    return out


def collect_options(ordered: list[str], manifests: dict[str, ModuleManifest]) -> dict[str, ModuleOption]:
    """[신규] ordered 모듈들이 선언한 옵션을 이름 기준으로 모은다 (질문할 목록).

    같은 이름의 옵션은 load_manifests()에서 이미 choices 일치가 검증됐으므로,
    여기서는 처음 발견된 선언 하나만 취하면 된다.
    """
    out: dict[str, ModuleOption] = {}
    for name in ordered:
        for opt_name, opt in manifests[name].options.items():
            out.setdefault(opt_name, opt)
    return out


def filter_manifest(manifest: ModuleManifest, option_answers: dict[str, str]) -> ModuleManifest:
    """[신규] when 조건에 안 맞는 files/routers/env_vars/pip_packages/docker_services 항목을 제거한 사본."""
    return manifest.model_copy(update={
        "files": [f for f in manifest.files if when_matches(f.when, option_answers)],
        "routers": [r for r in manifest.routers if when_matches(r.when, option_answers)],
        "env_vars": [e for e in manifest.env_vars if when_matches(e.when, option_answers)],
        "pip_packages": [
            p for p in manifest.pip_packages
            if when_matches(None if isinstance(p, str) else p.when, option_answers)
        ],
        "docker_services": {
            name: svc for name, svc in manifest.docker_services.items()
            if when_matches(svc.when, option_answers)
        },
    })


def filter_manifests(manifests: dict[str, ModuleManifest],
                      option_answers: dict[str, str]) -> dict[str, ModuleManifest]:
    """[신규] 전체 매니페스트 딕셔너리에 filter_manifest를 적용한 사본."""
    return {name: filter_manifest(m, option_answers) for name, m in manifests.items()}
