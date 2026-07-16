"""[2.2.2] 의존성 그래프: 자동 포함 · 순환 감지 · 위상 정렬.
[2.2.3] 설정값 추출: 환경 변수 수집 (파일 쓰기는 generator 소관).
"""
from graphlib import CycleError, TopologicalSorter

from .errors import CircularDependencyError, ScaffoldError
from .manifest import EnvVar, ModuleManifest


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
