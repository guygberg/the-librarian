import os
import tomllib
from pathlib import Path

import pytest

from support.cli import finish_tty, popen_librarian_tty, run_librarian

STUB_DIR = str(Path(__file__).parents[1] / "importer")


def run_setup(home, answers):
    proc = popen_librarian_tty(["setup"], home)
    os.write(proc.pty_master, "".join(a + "\n" for a in answers).encode())
    return finish_tty(proc)


def saved(home):
    return tomllib.loads((home / "config.toml").read_text())


def test_answers_saved_and_shown_on_rerun(home):
    code, out = run_setup(home, ["Team", "yes", "גיא, Guy G"])
    assert code == 0
    assert saved(home) == {
        "account_type": "team",
        "usage_rules_confirmed": True,
        "me_names": ["גיא", "Guy G"],
    }
    code, out = run_setup(home, ["", "", ""])
    assert code == 0
    assert "[team]" in out and "[yes]" in out and "[גיא, Guy G]" in out
    assert "me names: גיא, Guy G" in out
    assert saved(home)["me_names"] == ["גיא", "Guy G"]


def test_invalid_account_type_asks_again(home):
    code, out = run_setup(home, ["gold", "pro", "no", ""])
    assert code == 0
    assert "not a valid answer" in out
    assert saved(home)["account_type"] == "pro"


def test_setup_refuses_without_terminal(home):
    result = run_librarian(["setup"], home)
    assert result.returncode != 0
    assert not (home / "config.toml").exists()


def stubbed(tmp_path):
    items = tmp_path / "items.txt"
    items.write_text("slack/a")
    return {
        "LIBRARIAN_STAGES": "stub_stages",
        "PYTHONPATH": os.pathsep.join([STUB_DIR, os.environ.get("PYTHONPATH", "")]),
        "STUB_ITEMS": str(items),
        "STUB_LOG": str(tmp_path / "log.txt"),
        "STUB_BLOCK": str(tmp_path / "block"),
        "STUB_FAIL": "",
    }


@pytest.mark.parametrize(
    "config, blocked",
    [
        ("", True),
        ('account_type = "pro"\nusage_rules_confirmed = true\n', True),
        ('account_type = "team"\nusage_rules_confirmed = false\n', True),
        ('account_type = "team"\nusage_rules_confirmed = true\n', False),
        ('account_type = "enterprise"\nusage_rules_confirmed = true\n', False),
    ],
)
def test_extraction_gate(home, tmp_path, config, blocked):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(config)
    env = stubbed(tmp_path)
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    ran = Path(env["STUB_LOG"]).read_text().split("\n")
    assert "fetch a" in ran and "transcribe a" in ran
    if blocked:
        assert code != 0
        assert "extract a" not in ran and "link a" not in ran
        assert "librarian setup" in out
    else:
        assert code == 0
        assert "extract a" in ran
