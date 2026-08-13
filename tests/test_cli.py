"""[신규] 준비 단계 자동화: _run / _run_setup / _print_success 분기."""
import subprocess

from scaffold import cli


class _FakeResult:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def test_run_success_returns_true(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: _FakeResult(0))
    assert cli._run(["echo", "hi"], tmp_path) is True


def test_run_failure_warns_and_returns_false(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: _FakeResult(1, "boom"))
    assert cli._run(["bad"], tmp_path) is False
    assert "boom" in capsys.readouterr().out


def test_run_timeout_returns_false(tmp_path, monkeypatch, capsys):
    def _raise(cmd, **k):
        raise subprocess.TimeoutExpired(cmd="slow", timeout=1)
    monkeypatch.setattr(cli.subprocess, "run", _raise)
    assert cli._run(["slow"], tmp_path) is False
    assert str(cli._SETUP_TIMEOUT_SEC) in capsys.readouterr().out


def test_run_setup_non_docker_calls_venv_then_pip(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))
    ok = cli._run_setup(tmp_path, ["database"])
    assert ok is True
    assert len(calls) == 2
    assert calls[0][:3] == [cli.sys.executable, "-m", "venv"]
    assert calls[0][3] == str(tmp_path / ".venv")
    assert calls[1][1:] == ["-m", "pip", "install", "-e", "."]


def test_run_setup_venv_python_path_matches_os(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))
    cli._run_setup(tmp_path, [])
    venv_python = calls[1][0]
    if cli.os.name == "nt":
        assert venv_python.endswith("Scripts\\python.exe")
    else:
        assert venv_python.endswith("bin/python")


def test_run_setup_stops_if_venv_creation_fails(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(1, "venv failed"))
    ok = cli._run_setup(tmp_path, [])
    assert ok is False
    assert len(calls) == 1  # pip install까지는 안 감


def test_run_setup_docker_calls_compose_build(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/docker")
    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or _FakeResult(0))
    ok = cli._run_setup(tmp_path, ["docker"])
    assert ok is True
    assert calls == [["docker", "compose", "build"]]


def test_run_setup_docker_missing_binary_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    called: list[int] = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: called.append(1) or _FakeResult(0))
    ok = cli._run_setup(tmp_path, ["docker"])
    assert ok is False
    assert not called
    assert "docker" in capsys.readouterr().out


def test_print_success_setup_ok_skips_venv_and_install_but_keeps_activate(capsys):
    cli._print_success("demo", ["database"], setup_ok=True)
    out = capsys.readouterr().out
    assert "python -m venv" not in out
    assert "pip install -e ." not in out
    # 활성화는 자식 프로세스가 대신해줄 수 없는 셸 상태 변경이라 setup_ok여도 계속 안내해야 함
    assert ".venv\\Scripts\\activate" in out
    assert "uvicorn src.main:app --reload" in out


def test_print_success_setup_failed_shows_manual_steps(capsys):
    cli._print_success("demo", ["database"], setup_ok=False)
    out = capsys.readouterr().out
    assert "python -m venv .venv" in out
    assert "pip install -e ." in out


def test_print_success_docker_always_prints_compose_up(capsys):
    cli._print_success("demo", ["docker"], setup_ok=True)
    out = capsys.readouterr().out
    assert "docker compose up" in out
    assert "pip install" not in out
