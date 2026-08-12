"""[신규] when 조건부 포함: when_matches / package_requirement / collect_options / filter_manifest / 옵션 검증."""
import pytest
from pydantic import ValidationError

from scaffold.engine.conflicts import check_routes
from scaffold.engine.errors import OptionMismatchError, UnknownWhenKeyError, UnusedOptionError
from scaffold.engine.loader import load_manifests
from scaffold.engine.manifest import (
    DockerService, EnvVar, FileMapping, ModuleManifest, ModuleOption,
    PackageSpec, RouterSpec, package_requirement, when_matches,
)
from scaffold.engine.resolver import collect_options, filter_manifest


def test_when_matches_none_is_always_included():
    assert when_matches(None, {}) is True
    assert when_matches({}, {"db_type": "mysql"}) is True


def test_when_matches_or_within_same_key():
    when = {"db_type": ["mysql", "supabase"]}
    assert when_matches(when, {"db_type": "supabase"})
    assert not when_matches(when, {"db_type": "mongodb"})


def test_when_matches_and_across_keys():
    when = {"db_type": ["mongodb"], "auth_type": ["oauth"]}
    assert when_matches(when, {"db_type": "mongodb", "auth_type": "oauth"})
    assert not when_matches(when, {"db_type": "mongodb", "auth_type": "jwt"})


def test_package_requirement_normalizes_bare_string_and_spec():
    assert package_requirement("redis>=5.0") == "redis>=5.0"
    spec = PackageSpec(spec="motor>=3.3", when={"db_type": ["mongodb"]})
    assert package_requirement(spec) == "motor>=3.3"


def test_module_option_default_must_be_in_choices():
    with pytest.raises(ValidationError):
        ModuleOption(question="q", choices=["mysql", "mongodb"], default="postgresql")


def _sample_manifest() -> ModuleManifest:
    """DB 종류에 따라 파일/라우터/env/패키지/도커서비스가 갈리는 jwt-auth 유사 매니페스트."""
    return ModuleManifest(
        name="jwt-auth",
        files=[
            FileMapping(src="auth.py", dest="src/routers/auth.py"),
            FileMapping(src="db_sql.py", dest="src/core/db.py", when={"db_type": ["mysql", "supabase"]}),
            FileMapping(src="db_mongo.py", dest="src/core/db.py", when={"db_type": ["mongodb"]}),
        ],
        routers=[
            RouterSpec(module="x", prefix="/auth", when={"db_type": ["mysql", "supabase"]}),
            RouterSpec(module="y", prefix="/auth", when={"db_type": ["mongodb"]}),
        ],
        env_vars=[
            EnvVar(name="JWT_SECRET_KEY", default=""),
            EnvVar(name="MONGO_URL", when={"db_type": ["mongodb"]}),
        ],
        pip_packages=[
            "python-jose>=3.3",
            PackageSpec(spec="motor>=3.3", when={"db_type": ["mongodb"]}),
        ],
        docker_services={
            "db": DockerService(image="postgres:16", when={"db_type": ["mysql", "supabase"]}),
            "mongo": DockerService(image="mongo:7", when={"db_type": ["mongodb"]}),
        },
    )


def test_filter_manifest_mongodb_keeps_only_mongo_variant():
    filtered = filter_manifest(_sample_manifest(), {"db_type": "mongodb"})
    assert [f.src for f in filtered.files] == ["auth.py", "db_mongo.py"]
    assert [r.module for r in filtered.routers] == ["y"]
    assert [e.name for e in filtered.env_vars] == ["JWT_SECRET_KEY", "MONGO_URL"]
    assert [package_requirement(p) for p in filtered.pip_packages] == ["python-jose>=3.3", "motor>=3.3"]
    assert set(filtered.docker_services) == {"mongo"}


def test_filter_manifest_mysql_keeps_only_sql_variant():
    filtered = filter_manifest(_sample_manifest(), {"db_type": "mysql"})
    assert [f.src for f in filtered.files] == ["auth.py", "db_sql.py"]
    assert [r.module for r in filtered.routers] == ["x"]
    assert [e.name for e in filtered.env_vars] == ["JWT_SECRET_KEY"]
    assert [package_requirement(p) for p in filtered.pip_packages] == ["python-jose>=3.3"]
    assert set(filtered.docker_services) == {"db"}


def test_collect_options_merges_same_name_across_modules():
    opt = ModuleOption(question="DB 종류?", choices=["mysql", "mongodb"], default="mysql")
    a = ModuleManifest(name="database", options={"db_type": opt})
    b = ModuleManifest(name="jwt-auth", options={"db_type": opt})
    collected = collect_options(["database", "jwt-auth"], {"database": a, "jwt-auth": b})
    assert list(collected) == ["db_type"]


def test_filtering_fixes_the_self_conflict_bug_in_check_routes():
    """필터링 없이 넘기면 jwt-auth가 자기 자신과 라우트 충돌 판정을 받는 버그 재현 + when 필터링으로 해결됨을 확인."""
    manifest = _sample_manifest()

    raw_conflicts = check_routes(["jwt-auth"], {"jwt-auth": manifest})
    assert raw_conflicts, "필터링 없이는 mysql용/mongo용 라우터가 같은 prefix로 자기충돌해야 한다"

    filtered = filter_manifest(manifest, {"db_type": "mysql"})
    assert check_routes(["jwt-auth"], {"jwt-auth": filtered}) == []


def test_option_choices_mismatch_across_modules_raises(tmp_path):
    modules_dir = tmp_path / "modules"
    (modules_dir / "a").mkdir(parents=True)
    (modules_dir / "b").mkdir(parents=True)
    (modules_dir / "a" / "manifest.yaml").write_text(
        "name: a\n"
        "options:\n"
        "  db_type:\n"
        "    question: q\n"
        "    choices: [mysql, mongodb]\n",
        encoding="utf-8",
    )
    (modules_dir / "b" / "manifest.yaml").write_text(
        "name: b\n"
        "options:\n"
        "  db_type:\n"
        "    question: q\n"
        "    choices: [mysql]\n",
        encoding="utf-8",
    )
    with pytest.raises(OptionMismatchError):
        load_manifests(modules_dir)


def test_unknown_when_key_raises(tmp_path):
    modules_dir = tmp_path / "modules"
    (modules_dir / "a").mkdir(parents=True)
    (modules_dir / "a" / "manifest.yaml").write_text(
        "name: a\n"
        "env_vars:\n"
        "  - name: X\n"
        "    when: {db_typ: [mongodb]}\n",  # 오타: db_type이 아니라 db_typ
        encoding="utf-8",
    )
    with pytest.raises(UnknownWhenKeyError):
        load_manifests(modules_dir)


def test_unused_option_raises(tmp_path):
    modules_dir = tmp_path / "modules"
    (modules_dir / "a").mkdir(parents=True)
    (modules_dir / "a" / "manifest.yaml").write_text(
        "name: a\n"
        "options:\n"
        "  db_type:\n"
        "    question: q\n"
        "    choices: [postgresql]\n",  # 이 옵션을 참조하는 when이 어디에도 없음
        encoding="utf-8",
    )
    with pytest.raises(UnusedOptionError):
        load_manifests(modules_dir)
