"""Shared setup for tests that import fixture recordings through the CLI."""

import json

from fixtures.build import build
from librarian.fakes.calllog import CallLog
from support.cli import finish_tty, popen_librarian_tty, run_librarian


def make_env(tmp_path, home, scenario, extra_config=""):
    fixtures = tmp_path / "fixtures"
    build(fixtures, scenario)
    home.mkdir(parents=True, exist_ok=True)
    projects = fixtures / "claude" / "projects"
    (home / "config.toml").write_text(
        f'account_type = "team"\nusage_rules_confirmed = true\nclaude_projects_dir = "{projects}"\n'
        f'drive_dir = "{fixtures}"\n{extra_config}'
    )
    return {"LIBRARIAN_ENGINES": "fake", "LIBRARIAN_FIXTURES": str(fixtures)}, fixtures


def run_import(home, env, *args):
    code, out = finish_tty(popen_librarian_tty(["import", *args], home, env))
    return code, out.replace("\r", "")


def search(home, query):
    return json.loads(run_librarian(["search", query], home).stdout)["evidence"]


def engine_calls(home, method):
    calls = CallLog(home / "workspaces" / "work").read()
    return [c["args"] for c in calls if c["engine"] == "transcriber" and c["method"] == method]


def transcriber_calls(home):
    return [a["file"] for a in engine_calls(home, "transcribe")]
