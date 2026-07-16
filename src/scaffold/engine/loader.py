"""[1.3.1] modules/ 폴더가 곧 모듈 데이터베이스다."""
from pathlib import Path

import yaml

from .errors import ScaffoldError
from .manifest import ModuleManifest


def load_manifests(modules_dir: Path) -> dict[str, ModuleManifest]:
    """modules/*/manifest.yaml 을 전부 읽어 {이름: manifest} 로 반환. [2.2.1]"""
    manifests: dict[str, ModuleManifest] = {}
    for path in sorted(modules_dir.glob("*/manifest.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        m = ModuleManifest.model_validate(data)
        manifests[m.name] = m
    if not manifests:
        raise ScaffoldError("E-NOMOD", f"모듈을 찾지 못했습니다: {modules_dir}")
    return manifests
