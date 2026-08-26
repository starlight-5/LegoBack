"""[4.1] CLI 진입점과 전체 흐름 관리. D 파트 소유.

흐름: 입력(1.1) → AI 분석(1.2) → 추천 출력(1.3.4) → 선택·확인(2.1)
      → 해석(2.2) → 충돌 검사(3.x) → 생성(2.3~2.5) → 성공 안내(4.4.2)
"""
import logging
import os
import re
import shutil
import subprocess
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
from scaffold.engine.resolver import collect_env, collect_options, filter_manifests, resolve

load_dotenv()  # GEMINI_API_KEY 등을 .env에서 자동 로드

# git-bash(mintty) 등 진짜 Win32 콘솔이 아닌 터미널에서는 PEP 528의 콘솔 전용 유니코드
# 경로를 못 타고 시스템 코드페이지(cp949 등)로 인코딩을 시도하다 ui.py의 아이콘(▸✔⚠✘)에서
# UnicodeEncodeError로 죽는다. 인코딩은 그대로 두고 에러 시 대체 문자로 넘어가게만 한다.
if sys.platform == "win32":
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")

app = typer.Typer(add_completion=False)


@app.callback()
def main():
    """AI 기반 FastAPI 초기 환경 설정 도구."""


NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")  # [1.1.1] 이름 규칙
# parents[2]: cli.py -> scaffold -> src -> 저장소 루트. 그 아래의 modules/를 가리킨다.
MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"


def _normalize(text: str) -> str:
    """[1.1.2] 사용자 입력을 정리한다. 연속된 공백/줄바꿈을 하나로 합치고,
    500자를 넘으면 잘라낸다.

    Args:
        text: 정리할 원본 텍스트.

    Returns:
        공백이 정리되고 500자로 제한된 텍스트.
    """
    return " ".join(text.split())[:500]


@app.command()
def new(
    project_name: str = typer.Argument(..., help="영소문자·숫자·하이픈"),
    verbose: bool = typer.Option(False, "--verbose", help="[4.4.4] 상세 로그"),
):
    """[4.1.2] 새 프로젝트 생성을 시작합니다."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)
    # [1.1.1] 프로젝트 이름 규칙 검증
    if not NAME_RE.match(project_name):
        ui.err(f"프로젝트 이름 규칙 위반: '{project_name}'",
               "영소문자로 시작, 영소문자·숫자·하이픈만 가능합니다. 예: my-blog")
        raise typer.Exit(1)

    project_dir = Path.cwd() / project_name #Path.cwd 현재 작업 디렉터리
    # [4.1.3] 이름 중복 처리
    if project_dir.exists():
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


def _ask_clarifying_round(desc: str, result: AnalysisResult,
                           manifests: dict) -> tuple[str, AnalysisResult]:
    """[1.1.3] AI가 정보가 부족하다고 판단하면 보완 질문을 한 라운드 물어보고,
    답변을 설명에 합쳐서 다시 분석한다. 이미 충분하거나 물어볼 질문이 없으면
    원본을 그대로 돌려준다.

    Args:
        desc: 지금까지의 프로젝트 설명.
        result: 1차 분석 결과.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        (질문·답변이 합쳐진 설명, 재분석된 결과) 쌍.
    """
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


def _print_recommendations(result: AnalysisResult) -> None:
    """[1.3.4] 추천된 모듈과 그 근거를 콘솔에 목록으로 보여준다.

    Args:
        result: 추천 모듈·근거가 담긴 분석 결과.
    """
    typer.echo("\n추천 모듈:")
    for m in result.recommended_modules:
        typer.echo(f"  • {m} — {ui.truncate(result.reasons.get(m, ''))}")


def _choose_modules(result: AnalysisResult, manifests: dict) -> list[str]:
    """[2.1] 체크박스로 모듈을 고르게 하고 확인을 받는다. 0개를 고르면 다시
    고르게 하고, 확인 질문에 "아니오"라고 답하면 처음부터 다시 선택하게 한다.

    Args:
        result: 추천 모듈 정보.
        manifests: 전체 모듈 매니페스트.

    Returns:
        사용자가 최종 확인한 선택 모듈 목록.
    """
    while True:
        descriptions = {name: m.description for name, m in manifests.items()} #모듈 이름과 설명을 딕셔너리로 저장
        locked = [name for name, m in manifests.items() if m.required] # 필수 모듈만 저장
        selected = ui.select_modules(result.recommended_modules, sorted(manifests), result.reasons,
                                      descriptions, locked) #questionary 라이브러리를 사용하여 모듈 선택
        if not selected:                                 # [2.1.3] 0개 검증
            ui.warn("모듈을 1개 이상 선택해 주세요.")
            continue
        typer.echo("선택: " + ", ".join(selected))
        if ui.confirm("이대로 진행할까요?"):
            return selected


def _resolve_dependencies(selected: list[str], manifests: dict) -> list[str]:
    """[2.2.2] 선택한 모듈의 의존성을 자동으로 채워 넣고 설치 순서대로 정렬한다.
    자동으로 추가된 모듈이 있으면 화면에 안내한다.

    Args:
        selected: 사용자가 선택한 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        의존성까지 포함해 정렬된 모듈 목록.
    """
    ordered = resolve(selected, manifests)
    added = [m for m in ordered if m not in selected]
    if added:
        typer.echo("  의존성으로 자동 포함: " + ", ".join(added))
    return ordered


def _ask_options(ordered: list[str], manifests: dict) -> dict[str, str]:
    """[신규] 설치될 모듈들이 선언한 옵션(예: db_type)을 이름 기준으로 합쳐서
    한 번씩만 물어본다.

    Args:
        ordered: 정렬된 모듈 목록.
        manifests: 모듈명→매니페스트 매핑.

    Returns:
        옵션 이름 → 사용자가 고른 값 (예: {"db_type": "mongodb"}).
    """
    options = collect_options(ordered, manifests)
    answers: dict[str, str] = {}
    for name, opt in options.items():
        answers[name] = ui.select_option(opt.question, opt.choices, opt.default)
    return answers


def _check_conflicts(ordered: list[str], env_pairs, manifests: dict) -> None:
    """[3.x] 버전·환경변수·라우트 충돌을 전부 검사한다. 하나라도 발견되면
    내용과 해결 제안을 출력하고 생성 흐름을 중단시킨다.

    Args:
        ordered: 정렬된 모듈 목록.
        env_pairs: 수집된 환경변수, (모듈명, EnvVar) 쌍 목록.
        manifests: 모듈명→매니페스트 매핑.
    """
    found = (
        cf.check_versions(ordered, manifests) # 패키지 버전 충돌
        + cf.check_env(env_pairs) # 환경변수 충돌
        + cf.check_routes(ordered, manifests) # 라우트 충돌
    )
    if not found:
        return
    for c in found:
        ui.warn(f"[{c.kind}] {c.subject}: {c.detail}")
        if c.suggestion:
            typer.echo(f"  제안: {c.suggestion}")
    ui.err("충돌이 해결되지 않아 중단합니다.", "모듈 선택을 바꾸거나, 충돌하는 항목을 수정한 뒤 다시 시도해 주세요.")
    raise typer.Exit(1)


_SETUP_TIMEOUT_SEC = 300


def _run(cmd: list[str], cwd: Path) -> bool:
    """[신규] 서브프로세스를 실행한다. 실패해도 예외를 던지지 않고 경고만
    띄운 뒤 False를 돌려줘서, 전체 생성 흐름이 죽지 않게 한다.

    Args:
        cmd: 실행할 커맨드 (리스트 형태).
        cwd: 실행할 위치.

    Returns:
        성공하면 True, 실패하거나 시간 초과되면 False.
    """
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 timeout=_SETUP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        ui.warn(f"'{' '.join(cmd)}' 실행이 {_SETUP_TIMEOUT_SEC}초를 넘겨 중단했습니다.")
        return False
    if result.returncode != 0:
        ui.warn(f"'{' '.join(cmd)}' 실패:\n{result.stderr.strip()[-500:]}")
        return False
    return True


def _run_setup(project_dir: Path, ordered: list[str]) -> bool:
    """[신규] 프로젝트 생성 직후 준비 단계를 자동으로 실행한다. docker 모듈을
    골랐으면 이미지를 빌드하고, 아니면 venv를 만들고 의존성을 설치한다.

    실패해도 흐름은 안 죽는다 — 대신 이 함수가 False를 반환하고,
    _print_success가 그만큼 수동 안내 문구를 보여준다.

    Args:
        project_dir: 생성된 프로젝트 경로.
        ordered: 포함된 모듈 목록.

    Returns:
        준비 단계(venv+install 또는 docker build)가 성공했으면 True.
    """
    if "docker" in ordered:
        if shutil.which("docker") is None:
            ui.warn("docker 명령을 찾을 수 없어 자동 빌드를 건너뜁니다.")
            return False
        return _run(["docker", "compose", "build"], project_dir)

    venv_dir = project_dir / ".venv"
    if not _run([sys.executable, "-m", "venv", str(venv_dir)], project_dir):
        return False
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    py_name = "python.exe" if os.name == "nt" else "python"
    venv_python = venv_dir / bin_dir / py_name
    return _run([str(venv_python), "-m", "pip", "install", "-e", ".[dev]"], project_dir)


def _print_success(project_name: str, ordered: list[str], setup_ok: bool) -> None:
    """[4.4.2] 완료 메시지를 보여준다. 준비 단계(venv+install)가 자동으로 안
    끝났으면 그것만 수동 안내하고, 그 다음 실행 방법은 생성된 프로젝트의
    README.md를 가리킨다 — docker 유무, db_type 등 모듈 구성별 실행법이
    거기 이미 정리되어 있어서 여기서 다시 나열할 필요가 없다.

    Args:
        project_name: 생성된 프로젝트 이름.
        ordered: 포함된 모듈 목록.
        setup_ok: 준비 단계 자동 실행이 성공했는지 여부.
    """
    ui.ok("완료!")
    if not setup_ok and "docker" not in ordered:
        # venv 생성/설치는 프로젝트 폴더 안에서 실행해야 하므로, 이 경우에만 cd가 필요하다.
        typer.echo(f"\n  cd {project_name}")
        typer.echo("  python -m venv .venv")
        typer.echo("  pip install -e \".[dev]\"")
    typer.echo("\n  다음 단계는 README.md 파일을 참고하세요.")

def run_init_flow(project_name: str, project_dir: Path, verbose: bool) -> None:
    """[4.1.4] 프로젝트 생성의 전체 흐름을 순서대로 지휘한다: 설명 입력 → AI
    분석·추천 → 모듈 선택 → 의존성 해석 → 옵션 질문 → 충돌 검사 → 생성 →
    완료 안내. 각 단계의 실제 구현은 해당 함수/파트가 담당한다.

    Args:
        project_name: 생성할 프로젝트 이름.
        project_dir: 생성할 대상 경로.
        verbose: 상세 로그 출력 여부.
    """
    #  1. 모든 모듈의 매니페스트를 불러온다.
    manifests = load_manifests(MODULES_DIR)
    # 2. 프로젝트 설명을 입력받는다.
    desc = _normalize(typer.prompt(
        "어떤 프로젝트인가요? (민감 정보는 입력하지 마세요)"))  # [1.1.1~1.1.2]

    try:
        # 3. 입력받은 프로젝트 설명으로 모듈을 분석한다.
        with ui.step("자연어 분석 중..."):
            result = analyze(desc, manifests)                             # [1.2]
        # 4. 프로젝트 설명을 보충하고, 모듈을 추천한다.
        desc, result = _ask_clarifying_round(desc, result, manifests)    # [1.1.3]
        _print_recommendations(result)                                   # [1.3.4]
    except AIConnectionError:
        ui.warn("AI 연결에 실패하여 전체 모듈 선택 목록으로 이동합니다.")
        result = AnalysisResult()                                        # 추천 없이 빈 결과로 선택 화면 진행

    # 5. 모듈을 선택한다.
    selected = _choose_modules(result, manifests)                    # [2.1]
    # 6. 모듈 의존성을 해석한다.
    with ui.step("의존성 해석 중..."):
        ordered = _resolve_dependencies(selected, manifests)          # [2.2.2]

    # 7. 모듈 옵션을 질문한다.
    option_answers = _ask_options(ordered, manifests)                 # [신규] db_type 등 옵션 질문
    selected_manifests = {name: manifests[name] for name in ordered}
    # 8. when 조건에 따라 모듈을 필터링한다.
    filtered = filter_manifests(selected_manifests, option_answers)   # [신규] when 조건 필터링
    # 9. 환경변수를 수집한다.
    env_pairs = collect_env(ordered, filtered)                        # [2.2.3]

    # 10. 충돌 검사를 한다.
    with ui.step("충돌 검사 중..."):
        _check_conflicts(ordered, env_pairs, filtered)                  # [3.x]
    # 11. 프로젝트를 생성한다.
    with ui.step("프로젝트 생성 중..."):
        generate(project_dir, project_name, ordered, filtered, MODULES_DIR, env_pairs)
    # 12. 도커가 있다면 이미지를 빌드한다. 아니면 가상환경 설치 후 패키지를 설치한다.
    with ui.step("Docker 이미지 빌드 중..." if "docker" in ordered else "패키지 설치 중..."):
        setup_ok = _run_setup(project_dir, ordered)                   # [신규] 준비 단계 자동 실행

    # 13. 완료 안내 및 다음 실행 명령을 출력한다.
    _print_success(project_name, ordered, setup_ok)                  # [4.4.2]


if __name__ == "__main__":
    app()
