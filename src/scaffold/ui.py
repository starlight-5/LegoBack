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


def _ensure_questionary() -> None:
    """questionary 패키지가 설치돼 있는지 확인한다. 안 깔려 있으면(테스트 환경 등)
    화면을 그리려다 애매하게 죽는 대신, 여기서 바로 명확한 에러를 던진다.

    Raises:
        RuntimeError: questionary가 설치되어 있지 않은 경우.
    """
    if questionary is None:
        raise RuntimeError(
            "questionary 패키지가 설치되어 있지 않습니다. `pip install questionary`로 설치하세요."
        )


def truncate(text: str, limit: int = 30) -> str:
    """긴 텍스트를 정해진 길이로 잘라서 화면에 깔끔하게 보이게 한다.

    Args:
        text: 원본 텍스트.
        limit: 최대 길이 (기본 30자, AI 프롬프트의 근거 길이 지침과 동일).

    Returns:
        limit 이하면 그대로, 넘으면 잘라서 끝에 "…"을 붙인 텍스트.
    """
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _choice_title(module: str, reasons: dict[str, str]) -> str:
    """체크박스 목록에 보여줄 모듈 한 줄을 만든다.

    Args:
        module: 모듈명.
        reasons: 모듈명→추천 근거 매핑.

    Returns:
        추천 근거가 있으면 "모듈명 — 근거"(근거는 truncate로 요약됨),
        없으면 모듈명 그대로.
    """
    if module not in reasons:
        return module
    return f"{module} — {truncate(reasons[module])}"


def select_modules(recommended: list[str], all_modules: list[str],
                   reasons: dict[str, str],
                   descriptions: dict[str, str] | None = None,
                   locked: list[str] | None = None) -> list[str]:
    """[4.2.2~4.2.4] 화살표 키와 스페이스바로 여러 개를 고르는 체크박스 화면을
    보여준다. 추천 모듈은 미리 체크돼 있고, 필수 모듈은 체크 해제가 안 되게
    잠긴다.

    Args:
        recommended: 기본으로 체크할 추천 모듈 목록.
        all_modules: 전체 모듈 목록.
        reasons: 모듈명→추천 근거 매핑.
        descriptions: 모듈명→기능 설명 매핑.
        locked: 체크 해제가 불가능하게 고정할 필수 모듈 목록.

    Returns:
        사용자가 체크박스로 선택한 모듈 목록. 취소하면 KeyboardInterrupt가
        그대로 전파된다.
    """
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


def select_option(question: str, choices: list[str], default: str | None = None) -> str:
    """[신규] 화살표 키로 여러 선택지 중 하나만 고르는 단일 선택 화면을 보여준다
    (모듈 옵션용, 예: DB 종류 고르기).

    Args:
        question: 질문 문구.
        choices: 선택지 목록.
        default: 기본으로 선택돼 있을 값.

    Returns:
        사용자가 고른 선택지. 취소하면 KeyboardInterrupt가 그대로 전파된다.
    """
    _ensure_questionary()
    return questionary.select(question, choices=choices, default=default).unsafe_ask()


def confirm(message: str) -> bool:
    """예/아니오로 답하는 확인 질문을 보여준다. 기본값은 "예"다.

    Args:
        message: 확인 메시지.

    Returns:
        사용자의 응답 (Y면 True). 취소하면 KeyboardInterrupt가 그대로 전파된다.
    """
    _ensure_questionary()
    return bool(questionary.confirm(message).unsafe_ask())


class _Spinner:
    """[4.3.1~4.3.2] 작업이 진행되는 동안 콘솔에 회전하는 스피너를 보여준다.
    `with` 블록으로 감싼 구간이 끝날 때까지 계속 돈다.
    """
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


def step(msg: str) -> "_Spinner":
    """[4.3.1~4.3.3] "지금 뭘 하고 있는지" 메시지를 보여주면서, 그 작업이 끝날
    때까지 스피너를 돌린다. `with ui.step("..."):` 형태로 쓴다.

    Args:
        msg: 표시할 단계 메시지.

    Returns:
        with 블록으로 쓸 수 있는 스피너 컨텍스트 매니저.
    """
    return _Spinner(msg)


def ok(msg: str) -> None:
    """성공 메시지를 초록색으로 출력한다.

    Args:
        msg: 표시할 메시지.
    """
    typer.secho(f"✔ {msg}", fg=typer.colors.GREEN)


def warn(msg: str) -> None:
    """경고 메시지를 노란색으로 출력한다.

    Args:
        msg: 표시할 메시지.
    """
    typer.secho(f"⚠ {msg}", fg=typer.colors.YELLOW)


def err(msg: str, hint: str = "") -> None:
    """에러 메시지를 빨간색으로 출력한다(stderr로). hint를 주면 "이렇게
    해결하세요" 줄도 같이 보여준다.

    Args:
        msg: 표시할 오류 메시지.
        hint: 해결 방법 안내 (선택).
    """
    typer.secho(f"✘ {msg}", fg=typer.colors.RED, err=True)
    if hint:
        typer.secho(f"  → {hint}", fg=typer.colors.RED, err=True)


def highlight(msg: str) -> None:
    """URL처럼 눈에 띄어야 하는 메시지를 굵고 밑줄 친 청록색으로 출력한다.

    Args:
        msg: 강조해서 표시할 메시지.
    """
    typer.secho(msg, fg=typer.colors.CYAN, bold=True, underline=True)
