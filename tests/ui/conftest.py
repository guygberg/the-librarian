"""Browser test harness for the Librarian UI (pytest-playwright, Chromium).

Fixtures:
- `ui(scenario, now=None, config="")`: builds the fixture scenario, imports it with fake engines into a temp
  Workspace, starts `librarian serve` on a free port and returns a `Ui` (`url`, `home`, `env`, `sql`, `answer`).
  Call it once per test; the server stops at teardown.
- `page` and friends come from pytest-playwright.

Chromium: set `LIBRARIAN_CHROMIUM` to a browser binary (this Linux machine has `/snap/bin/chromium`); without it
a `chromium` on PATH is used, else Playwright's own download (`playwright install chromium`), so use whichever
works offline.
"""

import json
import os
import shutil
import sqlite3
import subprocess

import pytest

from support.cli import run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn


class Ui:
    def __init__(self, served, home, env):
        self.served, self.home, self.env = served, home, env

    @property
    def url(self):
        return f"http://127.0.0.1:{self.served.port}"

    def sql(self, query, *params):
        conn = sqlite3.connect(next(self.home.rglob("*.db")))
        with conn:
            return conn.execute(query, params).fetchall()

    def answer(self, command):
        """The JSON `librarian <command>` prints for this Workspace (the CLI the UI must agree with)."""
        out = run_librarian([command], self.home, env=self.env)
        assert out.returncode == 0, out.stdout
        return json.loads(out.stdout)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    if path := os.environ.get("LIBRARIAN_CHROMIUM") or shutil.which("chromium"):
        return {**browser_type_launch_args, "executable_path": path, "args": ["--no-sandbox"]}
    return browser_type_launch_args


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """The server and the browser agree on UTC, so clock times in the page match the Workspace's."""
    return {**browser_context_args, "timezone_id": "UTC", "locale": "en-GB", "viewport": {"width": 1100, "height": 900}}


@pytest.fixture
def ui(tmp_path, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    started: list[subprocess.Popen] = []

    def start(scenario, now=None, config=""):
        env, _ = make_env(tmp_path, home, scenario, config)
        env["TZ"] = "UTC"
        if now:
            env["LIBRARIAN_NOW"] = str(now)
        (home / "workspaces" / "work").mkdir(parents=True, exist_ok=True)
        (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
        code, out = run_import(home, env)
        assert code == 0, out
        proc, served = spawn(home, "--port", "0", env=env)
        started.append(proc)
        return Ui(served, home, env)

    yield start
    for proc in started:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
