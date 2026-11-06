import json
import shutil

import pytest

from fixtures.build import build
from librarian.importer import sessions
from support.cli import finish_tty, popen_librarian_tty, run_librarian

ECHO_SESSION = "33333333-aaaa-4bbb-8ccc-000000000003"


def make_env(tmp_path, home, scenario):
    fixtures = tmp_path / "fixtures"
    build(fixtures, scenario)
    home.mkdir(parents=True, exist_ok=True)
    projects = fixtures / "claude" / "projects"
    (home / "config.toml").write_text(
        f'account_type = "team"\nusage_rules_confirmed = true\nclaude_projects_dir = "{projects}"\n'
    )
    return {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures)}, projects


def run_import(home, env):
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    return code, out.replace("\r", "")


def search(home, query):
    return json.loads(run_librarian(["search", query], home).stdout)["evidence"]


def show(home, locator):
    answer = json.loads(run_librarian(["show", locator], home).stdout)
    answer.pop("freshness", None)  # moves with every Import; the item itself must not
    return answer


def test_copy_survives_deleting_the_original(tmp_path, home):
    env, projects = make_env(tmp_path, home, "base")
    code, out = run_import(home, env)
    assert code == 0 and "session: fetched" in out
    shutil.rmtree(projects)
    [hit] = search(home, "importer re-read")
    assert (
        hit["source"] == "session"
        and hit["locator"] == "session:11111111-aaaa-4bbb-8ccc-000000000001/1"
    )
    item = show(home, hit["locator"])
    content = json.loads(item["revisions"][0]["content"])
    assert content["text"] == "Why does the Atlas importer re-read old pages?"
    assert (content["line"], content["timestamp"], content["role"]) == (
        1,
        "2026-10-11T09:01:00.000Z",
        "user",
    )
    assert item["origin_name"] == "-home-dana-projects-atlas"
    assert search(home, "גינה")


def test_reimport_changes_nothing(tmp_path, home):
    env, _ = make_env(tmp_path, home, "base")
    run_import(home, env)
    before = show(home, "session:11111111-aaaa-4bbb-8ccc-000000000001/1")
    _, out = run_import(home, env)
    assert "session: fetched" not in out
    assert show(home, "session:11111111-aaaa-4bbb-8ccc-000000000001/1") == before


def test_librarian_echo_is_not_evidence(tmp_path, home):
    env, _ = make_env(tmp_path, home, "session_librarian_echo")
    assert run_import(home, env)[0] == 0
    [hit] = search(home, "cutover")
    assert hit["locator"] == f"session:{ECHO_SESSION}/4"
    assert search(home, "zephyr") == []
    assert [r["locator"] for r in search(home, "checking")] == [f"session:{ECHO_SESSION}/2"]
    assert run_librarian(["show", f"session:{ECHO_SESSION}/5"], home).returncode == 1
    assert run_librarian(["show", f"session:{ECHO_SESSION}/3"], home).returncode == 1


def test_librarian_clone_project_folder_is_skipped(tmp_path, home):
    env, projects = make_env(tmp_path, home, "session_librarian_echo")
    own = projects / sessions.own_project_name()
    own.mkdir()
    shutil.copy(
        projects / "-home-dana-projects-atlas" / f"{ECHO_SESSION}.jsonl", own / "44444444.jsonl"
    )
    assert run_import(home, env)[0] == 0
    assert run_librarian(["show", "session:44444444/4"], home).returncode == 1
    assert run_librarian(["show", f"session:{ECHO_SESSION}/4"], home).returncode == 0


def test_malformed_line_fails_that_item_only(tmp_path, home):
    env, projects = make_env(tmp_path, home, "base")
    path = projects / "-home-dana-projects-garden" / "22222222-aaaa-4bbb-8ccc-000000000002.jsonl"
    bad = {
        "type": "user",
        "timestamp": "2026-10-15T09:00:00.000Z",
        "message": {"content": "no role here"},
    }
    path.write_text(json.dumps(bad) + "\n" + path.read_text())
    code, out = run_import(home, env)
    assert code == 1 and "1 failed" in out
    assert (
        run_librarian(["show", "session:22222222-aaaa-4bbb-8ccc-000000000002/1"], home).returncode
        == 1
    )
    assert search(home, "גינה")
    assert search(home, "importer")


@pytest.mark.parametrize(
    ("suffix", "own"), [("", True), ("--worktrees-item-1", True), ("-other", False)]
)
def test_own_project_covers_its_worktrees_only(suffix, own):
    assert sessions._is_own(sessions.own_project_name() + suffix) is own
