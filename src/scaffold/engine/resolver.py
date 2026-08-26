"""[2.2.2] 의존성 그래프: 자동 포함 · 순환 감지 · 위상 정렬.
[2.2.3] 설정값 추출: 환경 변수 수집 (파일 쓰기는 generator 소관).
"""
from graphlib import CycleError, TopologicalSorter

from .errors import CircularDependencyError, ScaffoldError
from .manifest import EnvVar, ModuleManifest, ModuleOption, when_matches


def resolve(selected: list[str], manifests: dict[str, ModuleManifest]) -> list[str]:
    """사용자가 고른 모듈들을 보고, 그 모듈들이 depends_on으로 필요로 하는 다른
    모듈까지 자동으로 끌어모아서 설치 순서를 정한다.

    순서는 항상 "의존받는 쪽이 먼저" 온다 (예: settings → database → jwt-auth).
    이래야 나중 모듈이 앞선 모듈의 코드를 문제없이 쓸 수 있다.

    Args:
        selected: 사용자가 선택한 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        의존성까지 포함해 처리 순서대로 정렬된 모듈 목록.

    Raises:
        ScaffoldError: 선택한 모듈이 manifests에 없는 경우.
        CircularDependencyError: 의존성 그래프에 순환이 있는 경우.
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
    """[2.2.3] 설치 순서대로 각 모듈이 필요로 하는 환경변수를 (모듈명, 환경변수)
    쌍으로 쭉 모아온다. 이 결과가 나중에 환경변수 충돌 검사(3.2.2)의 입력이 된다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        (모듈명, EnvVar) 쌍 목록.
    """
    out: list[tuple[str, EnvVar]] = []
    for name in ordered:
        for var in manifests[name].env_vars:
            out.append((name, var))
    return out


def collect_options(ordered: list[str], manifests: dict[str, ModuleManifest]) -> dict[str, ModuleOption]:
    """설치될 모듈들이 각자 선언한 옵션(예: db_type)을 이름 기준으로 모아서,
    사용자에게 물어볼 질문 목록을 만든다.

    같은 이름의 옵션은 load_manifests()에서 이미 선택지가 같은지 검증됐기 때문에,
    여기서는 처음 발견된 선언 하나만 쓰면 된다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        옵션명→ModuleOption 매핑.
    """
    out: dict[str, ModuleOption] = {}
    for name in ordered:
        for opt_name, opt in manifests[name].options.items():
            out.setdefault(opt_name, opt)
    return out


def filter_manifest(manifest: ModuleManifest, option_answers: dict[str, str]) -> ModuleManifest:
    """사용자의 옵션 답변에 맞지 않는 files/routers/env_vars/pip_packages/
    docker_services 항목을 걸러내고, 맞는 것만 남긴 매니페스트 사본을 만든다.

    Args:
        manifest: 필터링할 모듈 매니페스트.
        option_answers: 옵션명→사용자 답변 매핑.

    Returns:
        when 조건에 맞는 항목만 남은 매니페스트 사본.
    """
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
    """모듈 전체 딕셔너리에 filter_manifest를 하나씩 적용해서, 전부 필터링된
    사본으로 만든다.

    Args:
        manifests: 모듈명→매니페스트 매핑.
        option_answers: 옵션명→사용자 답변 매핑.

    Returns:
        모듈명→필터링된 매니페스트 매핑.
    """
    return {name: filter_manifest(m, option_answers) for name, m in manifests.items()}
