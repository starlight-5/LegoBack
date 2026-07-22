"""[4.1] CLI 진입점과 전체 흐름 관리. D 파트 소유.

흐름: 입력(1.1) → AI 분석(1.2) → 추천 출력(1.3.4) → 선택·확인(2.1)
      → 해석(2.2) → 충돌 검사(3.x) → 생성(2.3~2.5) → 성공 안내(4.4.2)
"""
import logging
import re
import shutil
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

from scaffold import ui
from scaffold.ai.recommender import analyze
from scaffold.ai.schema import AnalysisResult
from scaffold.engine import conflicts as cf
from scaffold.engine.errors import AIConnectionError, ScaffoldError
from scaffold.engine.generator import generate
from scaffold.engine.loader import load_manifests
from scaffold.engine.resolver import collect_env, resolve

load_dotenv()  # GEMINI_API_KEY 등을 .env에서 자동 로드

# git-bash(mintty) 등 진짜 Win32 콘솔이 아닌 터미널에서는 PEP 528의 콘솔 전용 유니코드
# 경로를 못 타고 시스템 코드페이지(cp949 등)로 인코딩을 시도하다 ui.py의 아이콘(▸✔⚠✘)에서
# UnicodeEncodeError로 죽는다. 인코딩은 그대로 두고 에러 시 대체 문자로 넘어가게만 한다.
if sys.platform == "win32":
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

app = typer.Typer(add_completion=False)


# 입력: 없음
# 출력: 없음 (Typer 콜백 — 앱 설명용, 로직 없음)
@app.callback()
def main():
    """AI 기반 FastAPI 초기 환경 설정 도구."""


NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")  # [1.1.1] 이름 규칙
# parents[2]: cli.py -> scaffold -> src -> 저장소 루트. 그 아래의 modules/를 가리킨다.
MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


# 입력: text(str) - 원본 텍스트
# 출력: str - 공백 정리 + 500자 제한한 텍스트
def _normalize(text: str) -> str:
    """[1.1.2] 공백 정리 + 길이 제한."""
    return " ".join(text.split())[:500]


# 입력: project_name(str) - 생성할 프로젝트 이름(CLI 인자), verbose(bool) - 상세 로그 여부(--verbose)
# 출력: 없음 (성공 시 프로젝트 폴더 생성, 실패 시 typer.Exit으로 종료)
@app.command()
def new(
    project_name: str = typer.Argument(..., help="영소문자·숫자·하이픈"),
    verbose: bool = typer.Option(False, "--verbose", help="[4.4.4] 상세 로그"),
):
    """[4.1.2] 새 프로젝트 생성을 시작합니다."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)
    if not NAME_RE.match(project_name):
        ui.err(f"프로젝트 이름 규칙 위반: '{project_name}'",
               "영소문자로 시작, 영소문자·숫자·하이픈만 가능합니다. 예: my-blog")
        raise typer.Exit(1)

    project_dir = Path.cwd() / project_name
    if project_dir.exists():                            # [4.1.3] 이름 중복 처리
        ui.err(f"'{project_name}' 폴더가 이미 존재합니다.",
               "다른 이름을 쓰거나 기존 폴더를 정리해 주세요.")
        raise typer.Exit(1)

    try:
        run_init_flow(project_name, project_dir, verbose)
    except KeyboardInterrupt:                            # [1.1.4] 안전 취소 Ctrl+C
        ui.warn("취소되었습니다. 생성 중이던 파일을 정리합니다.")
        shutil.rmtree(project_dir, ignore_errors=True)
        raise typer.Exit(130)
    except ScaffoldError as e:                           # [4.4.1] 공통 오류 형식
        ui.err(f"[{e.code}] {e}", e.hint)
        shutil.rmtree(project_dir, ignore_errors=True)
        raise typer.Exit(1)


# 입력: desc(str) - 현재까지의 설명, result(AnalysisResult) - 1차 분석 결과,
#       manifests(dict) - 모듈 매니페스트
# 출력: tuple[str, AnalysisResult] - (질문·답변이 합쳐진 설명, 재분석된 결과)
#       result.sufficient가 True거나 질문이 없으면 원본 그대로 반환
def _ask_clarifying_round(desc: str, result: AnalysisResult,
                           manifests: dict) -> tuple[str, AnalysisResult]:
    """[1.1.3] 정보 부족 시 1라운드 보완 질문 → 답변을 설명에 합쳐 재분석."""
    if result.sufficient or not result.clarifying_questions:
        return desc, result

    ui.warn("추천 정확도를 높이기 위해 몇 가지만 여쭤볼게요.")
    answers = [typer.prompt(q, default="미정") for q in result.clarifying_questions]
    # 질문 텍스트를 답과 함께 묶어야 함: 답만 이어붙이면(예: "네 네 네") 어떤 질문에
    # 대한 답인지 문맥이 사라져 분석기가 사실상 무시하게 된다.
    qa_pairs = " ".join(f"{q} {a}" for q, a in zip(result.clarifying_questions, answers))
    desc = _normalize(desc + " " + qa_pairs)
    result = analyze(desc, manifests)        # 2차 분석 — 재질문 없음
    return desc, result


# 입력: result(AnalysisResult) - 추천 모듈·근거가 담긴 분석 결과
# 출력: 없음 (콘솔에 추천 모듈 목록 출력)
def _print_recommendations(result: AnalysisResult) -> None:
    """[1.3.4] 추천 모듈 + 근거 출력."""
    typer.echo("\n추천 모듈:")
    for m in result.recommended_modules:
        typer.echo(f"  • {m} — {ui.truncate(result.reasons.get(m, ''))}")


# 입력: result(AnalysisResult) - 추천 모듈 정보, manifests(dict) - 전체 모듈 매니페스트
# 출력: list[str] - 사용자가 최종 확인한 선택 모듈 목록 (1개 미만이면 재선택 반복)
def _choose_modules(result: AnalysisResult, manifests: dict) -> list[str]:
    """[2.1] 체크박스 선택 → 확인. N이면 재선택, 0개 선택은 거부."""
    while True:
        descriptions = {name: m.description for name, m in manifests.items()}
        locked = [name for name, m in manifests.items() if m.required]
        selected = ui.select_modules(result.recommended_modules, sorted(manifests), result.reasons,
                                      descriptions, locked)
        if not selected:                                 # [2.1.3] 0개 검증
            ui.warn("모듈을 1개 이상 선택해 주세요. (없이 만들려면 Ctrl+C 후 --bare 예정)")
            continue
        typer.echo("선택: " + ", ".join(selected))
        if ui.confirm("이대로 진행할까요?"):
            return selected


# 입력: selected(list[str]) - 사용자가 선택한 모듈 목록, manifests(dict) - 모듈 매니페스트
# 출력: tuple(ordered, env_pairs) - 의존성까지 포함해 정렬된 모듈 목록, 수집된 환경변수 목록
def _resolve_dependencies(selected: list[str], manifests: dict):
    """[2.2.2~2.2.3] 의존성 확장·정렬 + 환경 변수 수집."""
    ordered = resolve(selected, manifests)
    added = [m for m in ordered if m not in selected]
    if added:
        typer.echo("  의존성으로 자동 포함: " + ", ".join(added))
    env_pairs = collect_env(ordered, manifests)
    return ordered, env_pairs


# 입력: ordered(list[str]) - 정렬된 모듈 목록, env_pairs - 수집된 환경변수,
#       manifests(dict) - 모듈 매니페스트
# 출력: 없음 (충돌 발견 시 경고 출력 후 typer.Exit(1)로 중단)
def _check_conflicts(ordered: list[str], env_pairs, manifests: dict) -> None:
    """[3.x] 버전·환경변수·라우트 충돌 검사. 발견되면 안내 후 중단."""
    found = (
        cf.check_versions(ordered, manifests)
        + cf.check_env(env_pairs)
        + cf.check_routes(ordered, manifests)
    )
    if not found:
        return
    for c in found:
        ui.warn(f"[{c.kind}] {c.subject}: {c.detail}")
    ui.err("충돌이 해결되지 않아 중단합니다.", "TODO [3.3]: 해결안 제시 기능 구현 예정")
    raise typer.Exit(1)


# 입력: project_name(str) - 생성된 프로젝트 이름, ordered(list[str]) - 포함된 모듈 목록
# 출력: 없음 (완료 안내와 다음 실행 명령 출력)
def _print_success(project_name: str, ordered: list[str]) -> None:
    """[4.4.2] 완료 안내 + 다음 명령."""
    ui.ok("완료! 다음 명령으로 시작하세요:")
    typer.echo(f"\n  cd {project_name}")
    typer.echo(
        "  docker compose up   # docker 모듈 선택 시"
        if "docker" in ordered else
        "  uvicorn src.main:app --reload"
    )


# 입력: project_name(str) - 프로젝트 이름, project_dir(Path) - 생성 대상 경로,
#       verbose(bool) - 상세 로그 여부
# 출력: 없음 (전체 흐름을 순서대로 실행해 프로젝트 파일을 생성)
def run_init_flow(project_name: str, project_dir: Path, verbose: bool) -> None:
    """[4.1.4] 전체 여정의 지휘자. 각 단계 구현은 해당 파트 몫."""
    manifests = load_manifests(MODULES_DIR)

    desc = _normalize(typer.prompt(
        "어떤 프로젝트인가요? (민감 정보는 입력하지 마세요)"))  # [1.1.1~1.1.2]

    try:
        with ui.step("자연어 분석 중..."):
            result = analyze(desc, manifests)                             # [1.2]
        desc, result = _ask_clarifying_round(desc, result, manifests)    # [1.1.3]
        _print_recommendations(result)                                   # [1.3.4]
    except AIConnectionError:
        ui.warn("AI 연결에 실패하여 전체 모듈 선택 목록으로 이동합니다.")
        result = AnalysisResult()                                        # 추천 없이 빈 결과로 선택 화면 진행

    selected = _choose_modules(result, manifests)                    # [2.1]

    with ui.step("의존성 해석 중..."):
        ordered, env_pairs = _resolve_dependencies(selected, manifests)  # [2.2]

    with ui.step("충돌 검사 중..."):
        _check_conflicts(ordered, env_pairs, manifests)                  # [3.x]

    with ui.step("프로젝트 생성 중..."):
        generate(project_dir, project_name, ordered, manifests, MODULES_DIR, env_pairs)

    _print_success(project_name, ordered)                            # [4.4.2]


if __name__ == "__main__":
    app()
