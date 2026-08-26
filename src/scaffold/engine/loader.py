"""[1.3.1] modules/ 폴더가 곧 모듈 데이터베이스다."""
from pathlib import Path

import yaml

from .errors import OptionMismatchError, ScaffoldError, UnknownWhenKeyError, UnusedOptionError
from .manifest import ModuleManifest


def _whens_of(m: ModuleManifest) -> list:
    """모듈 하나가 갖고 있는 모든 when 조건(files, routers, env_vars,
    docker_services, pip_packages 안에 흩어져 있는 것 전부)을 한 리스트로 모은다.
    when이 없는 항목은 None으로 그대로 들어간다.

    Args:
        m: 대상 모듈 매니페스트.

    Returns:
        files/routers/env_vars/docker_services/pip_packages의 when 절을 모두 모은 리스트.
    """
    return (
        [f.when for f in m.files] + [r.when for r in m.routers] + [e.when for e in m.env_vars]
        + [svc.when for svc in m.docker_services.values()]
        + [p.when for p in m.pip_packages if not isinstance(p, str)]
    )


def _validate_shared_options(manifests: dict[str, ModuleManifest]) -> None:
    """여러 모듈이 같은 이름의 옵션(예: db_type)을 선언했다면, 그 모듈들이 준
    선택지(choices)가 서로 똑같은지 확인한다.

    Args:
        manifests: 모듈명→매니페스트 매핑.

    Raises:
        OptionMismatchError: 같은 옵션 이름인데 모듈마다 choices가 다른 경우.
    """
    seen: dict[str, tuple[str, list[str]]] = {}
    for mod_name, m in manifests.items():
        for opt_name, opt in m.options.items():
            if opt_name in seen:
                prev_mod, prev_choices = seen[opt_name]
                if set(prev_choices) != set(opt.choices):
                    raise OptionMismatchError(opt_name, prev_mod, prev_choices, mod_name, opt.choices)
            else:
                seen[opt_name] = (mod_name, opt.choices)


def _validate_when_keys(manifests: dict[str, ModuleManifest]) -> None:
    """when 조건이 가리키는 옵션 이름이 실제로는 어디에도 선언돼 있지 않으면 에러를 낸다.

    보통 오타(db_type을 db_typ으로 잘못 씀) 때문에 생기는 문제인데, 그냥 두면
    조건이 항상 매칭에 실패해서 파일이 조용히 계속 빠지는 버그가 되므로 미리 잡는다.

    Args:
        manifests: 모듈명→매니페스트 매핑.

    Raises:
        UnknownWhenKeyError: when이 참조하는 옵션이 어느 모듈에도 선언돼 있지 않은 경우.
    """
    known = {opt_name for m in manifests.values() for opt_name in m.options}
    for mod_name, m in manifests.items():
        for when in _whens_of(m):
            for key in (when or {}):
                if key not in known:
                    raise UnknownWhenKeyError(mod_name, key)


def _validate_options_used(manifests: dict[str, ModuleManifest]) -> None:
    """옵션은 선언해놓고, 그 옵션을 실제로 쓰는 when 절이 어디에도 없으면 에러를 낸다.

    when 연결하는 걸 깜빡해서 질문만 뜨고 아무것도 안 바뀌는 쓸모없는 옵션이
    생기는 걸 막는다.

    Args:
        manifests: 모듈명→매니페스트 매핑.

    Raises:
        UnusedOptionError: 선언된 옵션을 참조하는 when 절이 없는 경우.
    """
    used: set[str] = set()
    for m in manifests.values():
        for when in _whens_of(m):
            used.update((when or {}).keys())
    for mod_name, m in manifests.items():
        for opt_name in m.options:
            if opt_name not in used:
                raise UnusedOptionError(mod_name, opt_name)


def load_manifests(modules_dir: Path) -> dict[str, ModuleManifest]:
    """[2.2.1] modules/ 폴더 밑의 manifest.yaml을 전부 읽어서 {모듈명: 매니페스트}
    형태로 반환한다. 읽으면서 옵션/when 관련 규칙 위반도 함께 검사한다.

    Args:
        modules_dir: 모듈들이 위치한 디렉터리.

    Returns:
        모듈명→매니페스트 매핑.

    Raises:
        ScaffoldError: 디렉터리에서 모듈을 하나도 찾지 못한 경우.
    """
    manifests: dict[str, ModuleManifest] = {}
    for path in sorted(modules_dir.glob("*/manifest.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        m = ModuleManifest.model_validate(data)
        manifests[m.name] = m
    if not manifests:
        raise ScaffoldError("E-NOMOD", f"모듈을 찾지 못했습니다: {modules_dir}")
    _validate_shared_options(manifests)
    _validate_when_keys(manifests)
    _validate_options_used(manifests)
    return manifests
