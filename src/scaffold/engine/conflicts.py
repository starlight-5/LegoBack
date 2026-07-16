"""[3.1] 버전 충돌 검사 / [3.2] 기능 충돌 감지.

원칙: 여기는 '판정'만 한다. 통과한 조합만 병합(2.4)으로 넘어간다.
"""
from dataclasses import dataclass, field

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from .manifest import EnvVar, ModuleManifest


@dataclass
class Conflict:
    kind: str          # version | env | route | schema
    subject: str       # 패키지명 / 변수명 / 경로
    detail: str
    modules: list[str] = field(default_factory=list)


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
        # 각 명세의 기준 버전이 교집합을 만족하는지로 근사 판정.
        # TODO [3.1.3]: PyPI 배포 버전 목록과 대조해 최적 버전을 계산·제시
        pins = [s.version for _, spec in entries for s in spec if s.version]
        if pins and not any(merged.contains(v, prereleases=True) for v in pins):
            conflicts.append(Conflict(
                kind="version", subject=pkg,
                detail=" vs ".join(f"{m}({s or '*'})" for m, s in entries),
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
                    detail=f"{first_mod}='{first_default}' vs {module}='{var.default}'",
                    modules=[first_mod, module],
                ))
        else:
            seen[var.name] = (module, var.default)
    return conflicts


def check_routes(ordered: list[str], manifests: dict[str, ModuleManifest]) -> list[Conflict]:
    """[3.2.1] 같은 prefix 중복 감지. TODO: 라우터 파일 파싱으로 경로 단위 확장."""
    seen: dict[str, str] = {}
    conflicts: list[Conflict] = []
    for name in ordered:
        for r in manifests[name].routers:
            if r.prefix and r.prefix in seen:
                conflicts.append(Conflict(
                    kind="route", subject=r.prefix,
                    detail=f"{seen[r.prefix]}와(과) {name}이(가) 같은 prefix 사용",
                    modules=[seen[r.prefix], name],
                ))
            else:
                seen[r.prefix] = name
    return conflicts


# TODO [3.2.3] DB 스키마 충돌 감지 — 모델 파일의 테이블명 수집 후 중복 검사
# TODO [3.3]   해결안 제시(prefix 변경, 변수 접두사 등) — CLI 파트와 협의 후 구현
