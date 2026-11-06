import os
import signal
import sqlite3
import time
from pathlib import Path

import pytest

from support.cli import finish_tty, popen_librarian_tty, run_librarian

HERE = str(Path(__file__).parent)


@pytest.fixture
def stub_env(tmp_path, home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    items = tmp_path / "items.txt"
    items.write_text("slack/a slack/b slack/c")
    return {
        "LIBRARIAN_STAGES": "stub_stages",
        "PYTHONPATH": os.pathsep.join([HERE, os.environ.get("PYTHONPATH", "")]),
        "STUB_ITEMS": str(items),
        "STUB_LOG": str(tmp_path / "log.txt"),
        "STUB_BLOCK": str(tmp_path / "block"),
        "STUB_FAIL": "",
    }


def run_import(home, env):
    return finish_tty(popen_librarian_tty(["import"], home, env))


def executions(env):
    path = Path(env["STUB_LOG"])
    return path.read_text().split("\n") if path.exists() else []


def test_counters_printed_and_saved_and_failure_continues(home, stub_env):
    code, out = run_import(home, {**stub_env, "STUB_FAIL": "transcribe:b"})
    assert code == 1
    assert "slack: fetched 3, transcribed 2, extracted 0, failed 1" in out.replace("\r", "")
    assert "slack: fetched 3, transcribed 2, extracted 2, failed 1" in out
    db = sqlite3.connect(home / "workspaces/work/librarian.db")
    assert db.execute(
        "SELECT stage, error FROM import_item_stages WHERE status = 'failed'"
    ).fetchall() == [("transcribe", "RuntimeError: boom")]


def test_success_exits_zero(home, stub_env):
    code, out = run_import(home, stub_env)
    assert code == 0
    assert "import finished, 0 failed" in out


def test_rerun_retries_only_the_failed_item(home, stub_env):
    run_import(home, {**stub_env, "STUB_FAIL": "transcribe:b"})
    Path(stub_env["STUB_LOG"]).unlink()
    code, out = run_import(home, stub_env)
    assert code == 0
    assert sorted(e for e in executions(stub_env) if e) == [
        "extract b",
        "link b",
        "normalise b",
        "transcribe b",
    ]
    assert "slack: fetched 0, transcribed 1, extracted 1, failed 0" in out


def test_second_import_refused_with_progress_and_kill_frees_the_lock(home, stub_env, tmp_path):
    block = Path(stub_env["STUB_BLOCK"])
    block.touch()
    first = popen_librarian_tty(["import"], home, stub_env)
    started = Path(str(block) + ".started")
    deadline = time.time() + 20
    while not started.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert started.exists()
    try:
        code, out = run_import(home, stub_env)
        assert code == 1
        assert "another import is running" in out
        assert f"pid {first.pid}" in out
        assert "slack:" in out or "no items processed yet" in out
    finally:
        first.send_signal(signal.SIGKILL)
        finish_tty(first)
    block.unlink()
    code, _ = run_import(home, stub_env)
    assert code == 0


@pytest.mark.parametrize(
    "args,env",
    [
        (["import"], {}),
        (["import", "--from-serve"], {}),
        (["import"], {"LIBRARIAN_IMPORT_LAUNCH": "0:deadbeef"}),
        (["import"], {"LIBRARIAN_IMPORT_LAUNCH": "99:deadbeef"}),
        (["import"], {"LIBRARIAN_IMPORT_LAUNCH": "bogus"}),
    ],
)
def test_import_without_terminal_changes_nothing(home, args, env):
    result = run_librarian(args, home, env=env)
    assert result.returncode == 2
    if "--from-serve" not in args:
        assert "needs a terminal" in result.stderr
    assert not (home / "workspaces").exists()
