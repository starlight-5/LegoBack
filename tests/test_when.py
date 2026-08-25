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
    """when 절이 없으면(None 또는 빈 dict) 항상 매칭된다."""
    # Act & Assert
    assert when_matches(None, {}) is True
    assert when_matches({}, {"db_type": "mysql"}) is True


def test_when_matches_or_within_same_key():
    """같은 키에 여러 값이 있으면 그중 하나만 맞아도 매칭된다(OR)."""
    # Arrange
    when = {"db_type": ["mysql", "supabase"]}

    # Act & Assert
    assert when_matches(when, {"db_type": "supabase"})
    assert not when_matches(when, {"db_type": "mongodb"})


def test_when_matches_and_across_keys():
    """서로 다른 키는 전부 맞아야 매칭된다(AND)."""
    # Arrange
    when = {"db_type": ["mongodb"], "auth_type": ["oauth"]}

    # Act & Assert
    assert when_matches(when, {"db_type": "mongodb", "auth_type": "oauth"})
    assert not when_matches(when, {"db_type": "mongodb", "auth_type": "jwt"})


def test_package_requirement_normalizes_bare_string_and_spec():
    """문자열 그대로인 패키지와 PackageSpec 둘 다 같은 요구사항 문자열로 정규화된다."""
    # Arrange
    spec = PackageSpec(spec="motor>=3.3", when={"db_type": ["mongodb"]})

    # Act & Assert
    assert package_requirement("redis>=5.0") == "redis>=5.0"
    assert package_requirement(spec) == "motor>=3.3"


def test_module_option_default_must_be_in_choices():
    """default 값이 choices 목록에 없으면 검증 에러를 던진다."""
    # Act & Assert
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


@pytest.mark.parametrize(
    "db_type, expected_files, expected_routers, expected_env_vars, expected_packages, expected_docker_services",
    [
        pytest.param(
            "mongodb", ["auth.py", "db_mongo.py"], ["y"], ["JWT_SECRET_KEY", "MONGO_URL"],
            ["python-jose>=3.3", "motor>=3.3"], {"mongo"}, id="mongodb",
        ),
        pytest.param(
            "mysql", ["auth.py", "db_sql.py"], ["x"], ["JWT_SECRET_KEY"],
            ["python-jose>=3.3"], {"db"}, id="mysql",
        ),
    ],
)
def test_filter_manifest_keeps_only_matching_variant(
    db_type, expected_files, expected_routers, expected_env_vars, expected_packages, expected_docker_services,
):
    """when 조건에 안 맞는 files/routers/env_vars/pip_packages/docker_services는 제거되고, 선택한 db_type용 변형만 남는다."""
    # Arrange
    manifest = _sample_manifest()

    # Act
    filtered = filter_manifest(manifest, {"db_type": db_type})

    # Assert
    assert [f.src for f in filtered.files] == expected_files
    assert [r.module for r in filtered.routers] == expected_routers
    assert [e.name for e in filtered.env_vars] == expected_env_vars
    assert [package_requirement(p) for p in filtered.pip_packages] == expected_packages
    assert set(filtered.docker_services) == expected_docker_services


def test_collect_options_merges_same_name_across_modules():
    """여러 모듈이 같은 이름의 옵션을 선언해도 질문은 하나로 합쳐진다."""
    # Arrange
    opt = ModuleOption(question="DB 종류?", choices=["mysql", "mongodb"], default="mysql")
    a = ModuleManifest(name="database", options={"db_type": opt})
    b = ModuleManifest(name="jwt-auth", options={"db_type": opt})

    # Act
    collected = collect_options(["database", "jwt-auth"], {"database": a, "jwt-auth": b})

    # Assert
    assert list(collected) == ["db_type"]


def test_check_routes_self_conflicts_without_when_filtering():
    """필터링 없이 넘기면 jwt-auth가 자기 자신과 라우트 충돌 판정을 받는 버그 재현."""
    # Arrange
    manifest = _sample_manifest()

    # Act
    raw_conflicts = check_routes(["jwt-auth"], {"jwt-auth": manifest})

    # Assert
    assert raw_conflicts, "필터링 없이는 mysql용/mongo용 라우터가 같은 prefix로 자기충돌해야 한다"


def test_when_filtering_resolves_the_self_conflict():
    """when 필터링을 거치면 위 자기충돌이 사라지는지 확인."""
    # Arrange
    manifest = _sample_manifest()

    # Act
    filtered = filter_manifest(manifest, {"db_type": "mysql"})
    conflicts = check_routes(["jwt-auth"], {"jwt-auth": filtered})

    # Assert
    assert conflicts == []


def test_option_choices_mismatch_across_modules_raises(tmp_path):
    """같은 옵션 이름인데 모듈마다 choices가 다르면 OptionMismatchError를 던진다."""
    # Arrange
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

    # Act & Assert
    with pytest.raises(OptionMismatchError):
        load_manifests(modules_dir)


def test_unknown_when_key_raises(tmp_path):
    """when이 참조하는 옵션 이름이 어느 모듈에도 선언돼 있지 않으면 UnknownWhenKeyError를 던진다(오타 방지)."""
    # Arrange
    modules_dir = tmp_path / "modules"
    (modules_dir / "a").mkdir(parents=True)
    (modules_dir / "a" / "manifest.yaml").write_text(
        "name: a\n"
        "env_vars:\n"
        "  - name: X\n"
        "    when: {db_typ: [mongodb]}\n",  # 오타: db_type이 아니라 db_typ
        encoding="utf-8",
    )

    # Act & Assert
    with pytest.raises(UnknownWhenKeyError):
        load_manifests(modules_dir)


def test_unused_option_raises(tmp_path):
    """options로 선언만 하고 참조하는 when 절이 없으면 UnusedOptionError를 던진다(죽은 옵션 방지)."""
    # Arrange
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

    # Act & Assert
    with pytest.raises(UnusedOptionError):
        load_manifests(modules_dir)
