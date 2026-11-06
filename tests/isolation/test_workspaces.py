import builtins
import json
import sqlite3
from pathlib import Path

import pytest
from fixtures.scenarios import payments_cutover as payments
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env

from librarian import cli

NOW = str(payments.NOW)


def import_into(workspace, tmp_path, home, scenario):
    """Import a fixture scenario into one Workspace (config is shared, so it is rewritten per scenario)."""
    env, _ = make_env(tmp_path / workspace, home, scenario)
    env["LIBRARIAN_NOW"] = NOW
    folder = home / "workspaces" / workspace
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = finish_tty(popen_librarian_tty(["--workspace", workspace, "import"], home, env))
    assert code == 0, out
    return env


@pytest.fixture
def two_workspaces(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    monkeypatch.setenv("LIBRARIAN_NOW", NOW)
    import_into("work", tmp_path, home, "payments-cutover")
    import_into("other", tmp_path, home, "project-slack-only")
    return home


def evidence(home, workspace, query):
    out = run_librarian(["--workspace", workspace, "search", query], home, env={"LIBRARIAN_NOW": NOW})
    return json.loads(out.stdout)["evidence"]


def test_a_second_workspace_shares_no_results(two_workspaces):
    home = two_workspaces
    assert evidence(home, "work", "Payments") and evidence(home, "other", "Helios")
    assert evidence(home, "other", "Payments") == []
    assert evidence(home, "work", "Helios") == []


COMMANDS = (["search", "Payments"], ["open-items"], ["project", "payments"], ["show", "1"])


def touched_paths(monkeypatch, capsys, argv):
    """Run the CLI in-process and return every path it opened as a file or a SQLite database."""
    seen = []
    real_open, real_connect = builtins.open, sqlite3.connect

    def spy_open(file, *a, **kw):
        seen.append(Path(str(file)).resolve())
        return real_open(file, *a, **kw)

    def spy_connect(database, *a, **kw):
        text = str(database)
        seen.append(Path(text.removeprefix("file:").split("?")[0]).resolve())
        return real_connect(database, *a, **kw)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    cli.main(argv)
    return seen, capsys.readouterr().out


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c[0])
def test_answers_for_another_workspace_never_open_the_work_file(command, tmp_path, home, monkeypatch, capsys):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    import_into("work", tmp_path, home, "payments-cutover")
    work_db = (home / "workspaces" / "work" / "librarian.db").resolve()

    control, _ = touched_paths(monkeypatch, capsys, ["--workspace", "work", *command])
    assert work_db in control

    seen, out = touched_paths(monkeypatch, capsys, ["--workspace", "other", *command])
    assert work_db not in seen
    assert list(json.loads(out)) == ["error"]
    assert payments.PROJECT not in out
