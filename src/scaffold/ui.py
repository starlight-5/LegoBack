"""[4.2] 인터랙티브 선택 UI / [4.3] 진행 표시 / [4.4] 메시지 출력.

D 파트 소유. 흐름 로직(2.1)은 cli.py에 있고, 여기는 화면만 담당한다.
"""
import itertools
import shutil
import sys
import threading
import time

import typer

try:
    import questionary                      # [4.2.1] 라이브러리 통합
except ImportError:                          # 테스트 환경 등 미설치 대비
    questionary = None


# 입력: 없음
# 출력: 없음 (questionary 미설치 시 RuntimeError 발생)
def _ensure_questionary() -> None:
    if questionary is None:
        raise RuntimeError(
            "questionary 패키지가 설치되어 있지 않습니다. `pip install questionary`로 설치하세요."
        )


# 입력: text(str) - 원본 텍스트, limit(int) - 최대 길이 (기본 30자, AI 프롬프트의 근거 길이 지침과 동일)
# 출력: str - limit 이하면 그대로, 넘으면 잘라서 끝에 … 붙인 텍스트
def truncate(text: str, limit: int = 30) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# 입력: module(str) - 모듈명, reasons(dict[str, str]) - 모듈명→추천 근거
# 출력: str - 근거가 있으면 "모듈명 — 근거(30자 요약, AI가 짧게 생성 — truncate는 안전장치)", 없으면 모듈명 그대로
def _choice_title(module: str, reasons: dict[str, str]) -> str:
    if module not in reasons:
        return module
    return f"{module} — {truncate(reasons[module])}"


# 입력: recommended(list[str]) - 기본 체크될 추천 모듈, all_modules(list[str]) - 전체 모듈 목록,
#       reasons(dict[str, str]) - 모듈명→추천 근거, descriptions(dict[str, str]) - 모듈명→기능 설명,
#       locked(list[str]) - 체크 해제 불가능하게 고정할 필수 모듈
# 출력: list[str] - 사용자가 체크박스로 선택한 모듈 목록 (취소 시 KeyboardInterrupt 전파)
def select_modules(recommended: list[str], all_modules: list[str],
                   reasons: dict[str, str],
                   descriptions: dict[str, str] | None = None,
                   locked: list[str] | None = None) -> list[str]:
    """[4.2.2~4.2.4] 화살표 키 + 스페이스 체크박스. 추천 모듈은 기본 체크."""
    _ensure_questionary()
    descriptions = descriptions or {}
    locked = set(locked or [])
    choices = [
        questionary.Choice(
            title=_choice_title(m, reasons),
            value=m,
            checked=m in recommended or m in locked,  # [2.1.2] 추천 사전 체크
            description=descriptions.get(m) or None,  # 커서 위치한 항목의 모듈 기능을 하단에 표시
            disabled="필수 모듈" if m in locked else None,  # 체크 해제 못 하게 잠금
        )
        for m in all_modules
    ]
    style = questionary.Style([("text", "fg:#808080 italic")])
    # questionary의 ask()는 Ctrl+C를 내부에서 삼키고 None을 반환해 취소가 안 되는 것처럼 보인다.
    # unsafe_ask()로 KeyboardInterrupt를 그대로 전파해 cli.py의 취소 처리로 넘긴다.
    answer = questionary.checkbox("포함할 모듈을 선택하세요:", choices=choices, style=style).unsafe_ask()
    return answer or []


# 입력: message(str) - 확인 메시지
# 출력: bool - 사용자의 Y/N 응답 (기본값 Y)
def confirm(message: str) -> bool:
    """Y/N 확인, 기본값은 Y."""
    _ensure_questionary()
    return bool(questionary.confirm(message).unsafe_ask())


# [4.3.1~4.3.2] 작업 중 회전 스피너. with 블록으로 감싼 구간이 끝날 때까지 돈다.
class _Spinner:
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _INTERVAL = 0.08

    def __init__(self, msg: str) -> None:
        self._msg = msg
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            typer.secho(f"\r{frame} {self._msg}", fg=typer.colors.CYAN, nl=False)
            time.sleep(self._INTERVAL)

    def __enter__(self) -> "_Spinner":
        # 터미널이 아니면(리다이렉션·테스트 환경) 스피너 없이 메시지만 한 번 출력
        if sys.stdout.isatty():
            self._thread.start()
        else:
            typer.secho(f"▸ {self._msg}", fg=typer.colors.CYAN)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._thread.is_alive():
            self._stop.set()
            self._thread.join()
            width = shutil.get_terminal_size((80, 20)).columns
            typer.echo("\r" + " " * width + "\r", nl=False)  # 스피너 줄 지우기
            if exc_type is None:
                typer.secho(f"▸ {self._msg}", fg=typer.colors.CYAN)
        return False  # 예외는 그대로 전파


# 입력: msg(str) - 표시할 단계 메시지
# 출력: _Spinner - with 블록으로 감싸면 작업 중 회전 스피너를 보여주는 컨텍스트 매니저
def step(msg: str) -> "_Spinner":
    """[4.3.1~4.3.3] 현재 단계 안내 + 진행 중 스피너 (with 블록으로 사용)."""
    return _Spinner(msg)


# 입력: msg(str) - 성공 메시지
# 출력: 없음 (콘솔에 초록색으로 출력)
def ok(msg: str) -> None:
    typer.secho(f"✔ {msg}", fg=typer.colors.GREEN)


# 입력: msg(str) - 경고 메시지
# 출력: 없음 (콘솔에 노란색으로 출력)
def warn(msg: str) -> None:
    typer.secho(f"⚠ {msg}", fg=typer.colors.YELLOW)      # [4.4.3] 색상 구분


# 입력: msg(str) - 오류 메시지, hint(str) - 선택적 해결 힌트
# 출력: 없음 (콘솔(stderr)에 빨간색으로 출력, hint 있으면 추가 줄 출력)
def err(msg: str, hint: str = "") -> None:
    typer.secho(f"✘ {msg}", fg=typer.colors.RED, err=True)
    if hint:
        typer.secho(f"  → {hint}", fg=typer.colors.RED, err=True)
