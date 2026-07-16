"""[4.2] 인터랙티브 선택 UI / [4.3] 진행 표시 / [4.4] 메시지 출력.

D 파트 소유. 흐름 로직(2.1)은 cli.py에 있고, 여기는 화면만 담당한다.
"""
import typer

try:
    import questionary                      # [4.2.1] 라이브러리 통합
except ImportError:                          # 테스트 환경 등 미설치 대비
    questionary = None


def select_modules(recommended: list[str], all_modules: list[str],
                   reasons: dict[str, str]) -> list[str]:
    """[4.2.2~4.2.4] 화살표 키 + 스페이스 체크박스. 추천 모듈은 기본 체크."""
    choices = [
        questionary.Choice(
            title=f"{m} — {reasons.get(m, '')}" if m in reasons else m,
            value=m,
            checked=m in recommended,        # [2.1.2] 추천 사전 체크
        )
        for m in all_modules
    ]
    answer = questionary.checkbox("포함할 모듈을 선택하세요:", choices=choices).ask()
    return answer or []


def confirm(message: str) -> bool:
    return bool(questionary.confirm(message).ask())


def step(msg: str) -> None:
    """[4.3.3] 현재 단계 안내. TODO [4.3.1~4.3.2] 프로그레스 바·스피너."""
    typer.secho(f"▸ {msg}", fg=typer.colors.CYAN)


def ok(msg: str) -> None:
    typer.secho(f"✔ {msg}", fg=typer.colors.GREEN)


def warn(msg: str) -> None:
    typer.secho(f"⚠ {msg}", fg=typer.colors.YELLOW)      # [4.4.3] 색상 구분


def err(msg: str, hint: str = "") -> None:
    typer.secho(f"✘ {msg}", fg=typer.colors.RED, err=True)
    if hint:
        typer.secho(f"  → {hint}", fg=typer.colors.RED, err=True)
