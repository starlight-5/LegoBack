"""[1.3.1] modules/ 폴더가 곧 모듈 데이터베이스다."""
from pathlib import Path

import yaml

from .errors import OptionMismatchError, ScaffoldError, UnknownWhenKeyError, UnusedOptionError
from .manifest import ModuleManifest


def _whens_of(m: ModuleManifest) -> list:
    """[신규] 모듈 하나의 모든 when 절(None 포함)을 한 리스트로 모은다."""
    return (
        [f.when for f in m.files] + [r.when for r in m.routers] + [e.when for e in m.env_vars]
        + [svc.when for svc in m.docker_services.values()]
        + [p.when for p in m.pip_packages if not isinstance(p, str)]
    )


def _validate_shared_options(manifests: dict[str, ModuleManifest]) -> None:
    """[신규] 같은 이름의 옵션을 선언한 모듈끼리 choices가 일치하는지 검증."""
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
    """[신규] when 조건이 참조하는 옵션 이름이 실제로 어느 모듈에도 선언되지 않았으면 에러.

    오타(db_typ 등)로 인한 when이 항상 매칭 실패해 조용히 영구 제외되는 걸 막기 위한 안전장치.
    """
    known = {opt_name for m in manifests.values() for opt_name in m.options}
    for mod_name, m in manifests.items():
        for when in _whens_of(m):
            for key in (when or {}):
                if key not in known:
                    raise UnknownWhenKeyError(mod_name, key)


def _validate_options_used(manifests: dict[str, ModuleManifest]) -> None:
    """[신규] options로 선언된 옵션을 참조하는 when 절이 어디에도 없으면 에러.

    when 배선을 잊어 질문만 뜨고 아무것도 좌우하지 않는 죽은 옵션을 막기 위한 안전장치.
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
    """modules/*/manifest.yaml 을 전부 읽어 {이름: manifest} 로 반환. [2.2.1]"""
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
