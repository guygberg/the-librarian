import json
import re
from pathlib import Path

import pytest

from fixtures.scenarios import payments_cutover as payments
from librarian import cli, db
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skill" / "SKILL.md"
ANSWER_COMMANDS = [
    "open-items",
    "project",
    "changes",
    "waiting",
    "decision",
    "blocked",
    "search",
    "show",
]
ANSWER_ARGS = [
    ["open-items"],
    ["project", "Payments"],
    ["changes"],
    ["waiting"],
    ["decision", "webhook v1"],
    ["blocked"],
    ["search", "Payments"],
    ["show", str(payments.PROJECT_ID)],
]
# Every command that writes, with arguments that would otherwise get past argument parsing.
ADMIN_ARGS = [
    ["import"],
    ["slack", "pick"],
    ["slack", "import-older", "C001"],
    ["forget", "C001"],
    ["restore", "missing.tar.gz"],
    ["setup"],
    ["install-skill"],
]
FORBIDDEN = ["import", "serve", "backup", "restore", "forget"]


def frontmatter_and_body():
    _, front, body = SKILL.read_text().split("---\n", 2)
    return dict(line.split(": ", 1) for line in front.strip().splitlines()), body


@pytest.fixture
def seeded(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env, _ = make_env(tmp_path, home, "payments-cutover")
    env["LIBRARIAN_NOW"] = str(payments.NOW)
    (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    code, out = run_import(home, env)
    assert code == 0, out
    return env


def tree(home):
    return {p.relative_to(home): p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


def test_skill_allows_exactly_the_eight_answer_commands():
    front, _ = frontmatter_and_body()
    allowed = re.findall(r"Bash\(librarian ([a-z-]+):\*\)", front["allowed-tools"])
    assert allowed == ANSWER_COMMANDS
    assert front["allowed-tools"].count("Bash(") == len(ANSWER_COMMANDS)


def test_skill_names_the_forbidden_commands_and_the_never_do_list():
    _, body = frontmatter_and_body()
    assert "## Never do" in body
    never = body.split("## Never do")[1]
    for command in FORBIDDEN:
        assert f"`{command}`" in never


@pytest.mark.parametrize("argv", ANSWER_ARGS, ids=lambda a: a[0])
def test_answer_commands_open_the_database_read_only(argv, seeded, home, monkeypatch):
    opened = []
    real = db.connect_ro

    def spy(*args, **kwargs):
        opened.append(real(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(db, "connect_ro", spy)
    monkeypatch.setattr(
        db, "connect_rw", lambda *a, **k: pytest.fail("answer command opened a writable connection")
    )
    cli.main(["--workspace", "work", *argv])
    assert opened
    for conn in opened:
        with pytest.raises(Exception, match="readonly"):
            conn.execute("DELETE FROM records")


@pytest.mark.parametrize("argv", ADMIN_ARGS, ids=lambda a: "-".join(a))
def test_writing_admin_commands_refuse_without_a_terminal_and_change_nothing(
    argv, seeded, home, tmp_path
):
    before, user_home = tree(home), tmp_path / "user-home"
    result = run_librarian(argv, home, env={**seeded, "HOME": str(user_home)})
    assert result.returncode != 0
    assert "needs a terminal" in result.stderr
    assert tree(home) == before
    assert not user_home.exists()


def test_install_skill_links_the_skill_and_adds_the_shim_and_a_second_run_is_harmless(
    tmp_path, home
):
    user_home = tmp_path / "user-home"
    user_home.mkdir()
    env = {"HOME": str(user_home)}
    link, shim = user_home / ".claude/skills/librarian", user_home / ".local/bin/librarian"

    for _ in range(2):
        code, out = finish_tty(popen_librarian_tty(["install-skill"], home, env))
        assert code == 0, out
        assert link.is_symlink() and link.resolve() == ROOT / "skill"
        assert (link / "SKILL.md").exists()
        assert shim.stat().st_mode & 0o111 and '-m librarian "$@"' in shim.read_text()
    assert "already linked" in out and "already installed" in out
