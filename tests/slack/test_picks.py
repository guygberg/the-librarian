import json
import os
from pathlib import Path

import pytest

from fixtures.build import build
from librarian.fakes.calllog import CallLog
from support.cli import finish_tty, popen_librarian_tty, run_librarian

STUB_DIR = str(Path(__file__).parents[1] / "importer")


@pytest.fixture
def env(tmp_path):
    target = tmp_path / "slack-fixtures"
    build(target, "slack_conversation_list")
    return {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(target)}


def list_picks(home, env):
    return run_librarian(["slack", "pick", "--list"], home, env=env)


def pick_in_pty(home, env, answers):
    proc = popen_librarian_tty(["slack", "pick"], home, env)
    os.write(proc.pty_master, "".join(a + "\n" for a in answers).encode())
    return finish_tty(proc)


def seed(home, ids):
    ws = home / "workspaces" / "work"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "channels.json").write_text(json.dumps({"picked": ids}))


def test_list_shows_name_kind_members_and_marks(home, env):
    seed(home, ["G001"])
    out = list_picks(home, env).stdout
    lines = {line.split("]", 1)[1].strip(): line for line in out.splitlines() if "[" in line}
    assert "atlas-dev  (public, 12 members)" in lines
    assert "atlas-leads  (private, 4 members)" in lines
    assert "U001  (DM, 2 members)" in lines
    assert "mpdm-dana--omer-1  (group DM, 3 members)" in lines
    assert "[x] atlas-leads" in lines["atlas-leads  (private, 4 members)"]
    assert "[ ] atlas-dev" in lines["atlas-dev  (public, 12 members)"]


def test_pick_and_unpick_persist(home, env):
    code, _ = pick_in_pty(home, env, ["1 3", ""])
    assert code == 0
    out = list_picks(home, env).stdout
    assert "[x] atlas-dev" in out and "[x] U001" in out and "[ ] atlas-leads" in out
    code, _ = pick_in_pty(home, env, ["1", ""])
    assert code == 0
    out = list_picks(home, env).stdout
    assert "[ ] atlas-dev" in out and "[x] U001" in out


def test_pick_refuses_without_terminal_and_changes_nothing(home, env):
    result = run_librarian(["slack", "pick"], home, env=env)
    assert result.returncode != 0
    assert not (home / "workspaces").exists()


def test_seed_applies_once_and_later_edits_win(home, env):
    seed(home, ["C001"])
    assert "[x] atlas-dev" in list_picks(home, env).stdout
    pick_in_pty(home, env, ["1", ""])
    assert "[ ] atlas-dev" in list_picks(home, env).stdout
    seed(home, ["C001", "G001"])
    out = list_picks(home, env).stdout
    assert "[ ] atlas-dev" in out and "[ ] atlas-leads" in out


def test_import_with_nothing_picked_fetches_no_history(home, env, tmp_path):
    items = tmp_path / "items.txt"
    items.write_text("")
    env = {
        **env,
        "LIBRARIAN_STAGES": "stub_stages",
        "PYTHONPATH": os.pathsep.join([STUB_DIR, os.environ.get("PYTHONPATH", "")]),
        "STUB_ITEMS": str(items),
        "STUB_LOG": str(tmp_path / "log.txt"),
        "STUB_BLOCK": str(tmp_path / "block"),
        "STUB_FAIL": "",
    }
    finish_tty(popen_librarian_tty(["import"], home, env))
    ws = home / "workspaces" / "work"
    assert not [c for c in CallLog(ws).read() if c["method"] in ("history", "replies")]
