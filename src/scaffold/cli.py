"""[4.1] CLI 진입점과 전체 흐름 관리. D 파트 소유.

흐름: 입력(1.1) → AI 분석(1.2) → 추천 출력(1.3.4) → 선택·확인(2.1)
      → 해석(2.2) → 충돌 검사(3.x) → 생성(2.3~2.5) → 성공 안내(4.4.2)
"""
import re
import shutil
from pathlib import Path

import typer

from scaffold import ui
from scaffold.ai.recommender import analyze
from scaffold.engine import conflicts as cf
from scaffold.engine.errors import ScaffoldError
from scaffold.engine.generator import generate
from scaffold.engine.loader import load_manifests
from scaffold.engine.resolver import collect_env, resolve

app = typer.Typer(help="AI 기반 FastAPI 초기 환경 설정 도구")

NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")            # [1.1.1] 이름 규칙
MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


def _normalize(text: str) -> str:
    """[1.1.2] 공백 정리 + 길이 제한."""
    return " ".join(text.split())[:500]


@app.command()
def new(
    project_name: str = typer.Argument(..., help="영소문자·숫자·하이픈"),
    verbose: bool = typer.Option(False, "--verbose", help="[4.4.4] 상세 로그"),
):
    """[4.1.2] 새 프로젝트 생성을 시작합니다."""
    if not NAME_RE.match(project_name):
        ui.err(f"프로젝트 이름 규칙 위반: '{project_name}'",
               "영소문자로 시작, 영소문자·숫자·하이픈만 가능합니다. 예: my-blog")
        raise typer.Exit(1)

    project_dir = Path.cwd() / project_name            # [4.1.3]
    if project_dir.exists():
        ui.err(f"'{project_name}' 폴더가 이미 존재합니다.",
               "다른 이름을 쓰거나 기존 폴더를 정리해 주세요.")
        raise typer.Exit(1)

    try:
        run_init_flow(project_name, project_dir, verbose)
    except KeyboardInterrupt:                          # [1.1.4] 안전 취소
        ui.warn("취소되었습니다. 생성 중이던 파일을 정리합니다.")
        shutil.rmtree(project_dir, ignore_errors=True)
        raise typer.Exit(130)
    except ScaffoldError as e:                         # [4.4.1] 공통 오류 형식
        ui.err(f"[{e.code}] {e}", e.hint)
        shutil.rmtree(project_dir, ignore_errors=True)
        raise typer.Exit(1)


def run_init_flow(project_name: str, project_dir: Path, verbose: bool) -> None:
    """[4.1.4] 전체 여정의 지휘자. 각 단계 구현은 해당 파트 몫."""
    manifests = load_manifests(MODULES_DIR)

    desc = _normalize(typer.prompt(
        "어떤 프로젝트인가요? (민감 정보는 입력하지 마세요)"))    # [1.1.1~1.1.2]

    ui.step("자연어 분석 중...")
    result = analyze(desc, manifests)                  # [1.2]

    if not result.sufficient and result.clarifying_questions:   # [1.1.3] 1라운드
        ui.warn("추천 정확도를 높이기 위해 몇 가지만 여쭤볼게요.")
        answers = [typer.prompt(q, default="미정") for q in result.clarifying_questions]
        desc = _normalize(desc + " " + " ".join(answers))
        result = analyze(desc, manifests)              # 2차 분석 — 재질문 없음

    typer.echo("\n추천 모듈:")                          # [1.3.4]
    for m in result.recommended_modules:
        typer.echo(f"  • {m} — {result.reasons.get(m, '')}")

    while True:                                        # [2.1] 선택·확인 루프
        selected = ui.select_modules(
            result.recommended_modules, sorted(manifests), result.reasons)
        if not selected:                               # [2.1.3] 0개 검증
            ui.warn("모듈을 1개 이상 선택해 주세요. (없이 만들려면 Ctrl+C 후 --bare 예정)")
            continue
        typer.echo("선택: " + ", ".join(selected))
        if ui.confirm("이대로 진행할까요?"):
            break                                      # '수정'이면 상태 유지 재진입

    ui.step("의존성 해석 중...")
    ordered = resolve(selected, manifests)             # [2.2.2]
    added = [m for m in ordered if m not in selected]
    if added:
        typer.echo("  의존성으로 자동 포함: " + ", ".join(added))
    env_pairs = collect_env(ordered, manifests)        # [2.2.3]

    ui.step("충돌 검사 중...")                          # [3.x]
    found = (cf.check_versions(ordered, manifests)
             + cf.check_env(env_pairs)
             + cf.check_routes(ordered, manifests))
    if found:
        for c in found:
            ui.warn(f"[{c.kind}] {c.subject}: {c.detail}")
        ui.err("충돌이 해결되지 않아 중단합니다.",
               "TODO [3.3]: 해결안 제시 기능 구현 예정")
        raise typer.Exit(1)

    ui.step("프로젝트 생성 중...")
    generate(project_dir, project_name, ordered, manifests, MODULES_DIR, env_pairs)

    ui.ok(f"완료! 다음 명령으로 시작하세요:")            # [4.4.2]
    typer.echo(f"\n  cd {project_name}")
    typer.echo("  docker compose up   # docker 모듈 선택 시"
               if "docker" in ordered else
               "  uvicorn src.main:app --reload")


if __name__ == "__main__":
    app()
