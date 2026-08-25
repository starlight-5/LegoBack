"""[신규] 준비 단계 자동화: _run / _run_setup / _print_success 분기."""
import subprocess

from scaffold import cli


class _FakeResult:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_run_success_returns_true(tmp_path, monkeypatch):
    """subprocess가 성공(returncode=0)하면 _run이 True를 반환한다."""
    # Arrange
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: _FakeResult(0))

    # Act
    result = cli._run(["echo", "hi"], tmp_path)

    # Assert
    assert result is True


def test_run_failure_warns_and_returns_false(tmp_path, monkeypatch, capsys):
    """subprocess가 실패하면 stderr를 출력하고 False를 반환한다."""
    # Arrange
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: _FakeResult(1, "boom"))

    # Act
    result = cli._run(["bad"], tmp_path)

    # Assert
    assert result is False
    assert "boom" in capsys.readouterr().out


def test_run_timeout_returns_false(tmp_path, monkeypatch, capsys):
    """제한 시간을 넘기면 타임아웃 메시지를 출력하고 False를 반환한다."""
    # Arrange
    def _raise(cmd, **k):
        raise subprocess.TimeoutExpired(cmd="slow", timeout=1)
    monkeypatch.setattr(cli.subprocess, "run", _raise)

    # Act
    result = cli._run(["slow"], tmp_path)

    # Assert
    assert result is False
    assert str(cli._SETUP_TIMEOUT_SEC) in capsys.readouterr().out


def test_run_setup_non_docker_calls_venv_then_pip(tmp_path, monkeypatch):
    """docker 미선택 시 venv 생성 후 pip install을 순서대로 호출한다."""
    # Arrange
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))

    # Act
    ok = cli._run_setup(tmp_path, ["database"])

    # Assert
    assert ok is True
    assert len(calls) == 2
    assert calls[0][:3] == [cli.sys.executable, "-m", "venv"]
    assert calls[0][3] == str(tmp_path / ".venv")
    assert calls[1][1:] == ["-m", "pip", "install", "-e", "."]


def test_run_setup_venv_python_path_matches_os(tmp_path, monkeypatch):
    """venv 파이썬 실행 파일 경로가 OS에 맞게(Windows: Scripts, 그 외: bin) 결정된다."""
    # Arrange
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))

    # Act
    cli._run_setup(tmp_path, [])
    venv_python = calls[1][0]

    # Assert
    if cli.os.name == "nt":
        assert venv_python.endswith("Scripts\\python.exe")
    else:
        assert venv_python.endswith("bin/python")


def test_run_setup_stops_if_venv_creation_fails(tmp_path, monkeypatch):
    """venv 생성이 실패하면 pip install은 시도하지 않고 중단한다."""
    # Arrange
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(1, "venv failed"))

    # Act
    ok = cli._run_setup(tmp_path, [])

    # Assert
    assert ok is False
    assert len(calls) == 1  # pip install까지는 안 감


def test_run_setup_docker_calls_compose_build(tmp_path, monkeypatch):
    """docker 선택 시 venv/pip 없이 docker compose build만 호출한다."""
    # Arrange
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))

    # Act
    ok = cli._run_setup(tmp_path, ["docker"])

    # Assert
    assert ok is True
    assert calls == [["docker", "compose", "build"]]


def test_run_setup_docker_missing_binary_skips(tmp_path, monkeypatch, capsys):
    """docker 명령을 찾지 못하면 아무 명령도 실행하지 않고 실패로 처리한다."""
    # Arrange
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    called: list[int] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: called.append(1) or _FakeResult(0))

    # Act
    ok = cli._run_setup(tmp_path, ["docker"])

    # Assert
    assert ok is False
    assert not called
    assert "docker" in capsys.readouterr().out


def test_print_success_setup_ok_skips_venv_and_install_but_keeps_activate(capsys):
    """준비 단계가 이미 자동 실행됐으면 venv/설치 안내는 생략하되, 활성화 안내는 유지한다."""
    # Act
    cli._print_success("demo", ["database"], setup_ok=True)
    out = capsys.readouterr().out

    # Assert
    assert "python -m venv" not in out
    assert "pip install -e ." not in out
    # 활성화는 자식 프로세스가 대신해줄 수 없는 셸 상태 변경이라 setup_ok여도 계속 안내해야 함
    assert ".venv\\Scripts\\activate" in out
    assert "uvicorn src.main:app --reload" in out


def test_print_success_setup_failed_shows_manual_steps(capsys):
    """준비 단계가 실패했으면 venv 생성부터 수동 안내를 전부 보여준다."""
    # Act
    cli._print_success("demo", ["database"], setup_ok=False)
    out = capsys.readouterr().out

    # Assert
    assert "python -m venv .venv" in out
    assert "pip install -e ." in out


def test_print_success_docker_always_prints_compose_up(capsys):
    """docker 모듈 선택 시 pip install 안내 없이 docker compose up만 안내한다."""
    # Act
    cli._print_success("demo", ["docker"], setup_ok=True)
    out = capsys.readouterr().out

    # Assert
    assert "docker compose up" in out
    assert "pip install" not in out
