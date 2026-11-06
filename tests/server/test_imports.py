import os
import re
import signal
import time
from pathlib import Path

import pytest

from fixtures.scenarios import payments_cutover as payments  # noqa: F401
from librarian.fakes.calllog import CallLog
from support.api import Api
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

STUBS = str(Path(__file__).parents[1] / "importer")
COUNTERS = ("fetched", "transcribed", "extracted", "failed")


@pytest.fixture
def serve(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    started = []

    def _serve(env):
        proc, served = spawn(home, "--port", "0", env=env)
        started.append(proc)
        return Api(served, home, env)

    yield _serve
    for proc in started:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()


@pytest.fixture
def stub_env(tmp_path, home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    items = tmp_path / "items.txt"
    items.write_text("slack/a slack/b slack/c")
    return {
        "LIBRARIAN_STAGES": "stub_stages",
        "PYTHONPATH": os.pathsep.join([STUBS, os.environ.get("PYTHONPATH", "")]),
        "STUB_ITEMS": str(items),
        "STUB_LOG": str(tmp_path / "log.txt"),
        "STUB_BLOCK": str(tmp_path / "block"),
        "STUB_FAIL": "",
    }


def seed_picks(home, ids):
    ws = home / "workspaces" / "work"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "channels.json").write_text('{"picked": ' + str(ids).replace("'", '"') + "}")


def wait_for(check, what):
    deadline = time.time() + 30
    while time.time() < deadline:
        if value := check():
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def wait_done(api):
    return wait_for(
        lambda: (
            (p := api.call("GET", "/api/import")[1])["run"]
            and p["run"]["status"] == "finished"
            and p
        ),
        "the import to finish",
    )


def cli_counts(out):
    last = {}
    for line in out.splitlines():
        if m := re.match(
            r"(\w+): fetched (\d+), transcribed (\d+), extracted (\d+), failed (\d+)", line
        ):
            last[m[1]] = dict(zip(COUNTERS, map(int, m.groups()[1:]), strict=True))
    return last


def test_started_import_shows_the_same_counts_as_the_cli(tmp_path, home, serve):
    env, _ = make_env(tmp_path, home, "payments-cutover")
    seed_picks(home, ["C001"])
    home2 = tmp_path / "home2"
    env2, _ = make_env(tmp_path / "two", home2, "payments-cutover")
    seed_picks(home2, ["C001"])
    code, out = run_import(home2, env2)
    assert code == 0, out

    api = serve(env)
    status, started = api.post("/api/import/start")
    assert status == 202
    done = wait_done(api)

    assert done["run"]["status"] == "finished" and done["failed"] == []
    assert done["sources"] == cli_counts(out)
    assert done["calls"] == len(
        [c for c in CallLog(home2 / "workspaces" / "work").read() if c["engine"] == "extractor"]
    )
    assert set(done["freshness"]["sources"]) == {"slack", "drive", "session"}
    assert done["freshness"]["last_import_finished_at"]


def test_dry_run_returns_the_count_and_makes_no_extraction_call(tmp_path, home, serve):
    env, _ = make_env(tmp_path, home, "payments-cutover")
    seed_picks(home, ["C001"])
    api = serve(env)
    status, body = api.post("/api/import/dry-run")
    assert status == 200 and body["calls"] > 0 and body["sent"] == 0
    assert [
        c for c in CallLog(home / "workspaces" / "work").read() if c["engine"] == "extractor"
    ] == []


def test_second_start_refused_with_progress_reads_answer_and_kill_frees_the_lock(
    home, stub_env, serve
):
    block = Path(stub_env["STUB_BLOCK"])
    block.touch()
    first = popen_librarian_tty(["import"], home, stub_env)
    wait_for(lambda: Path(str(block) + ".started").exists(), "the CLI import to block")
    api = serve(stub_env)
    try:
        status, refused = api.post("/api/import/start")
        assert status == 409 and refused["running"] and refused["run"]["pid"] == first.pid
        assert api.call("POST", "/api/import/dry-run")[0] == 409
        assert api.call("GET", "/api/status")[0] == 200
        assert not Path(stub_env["STUB_LOG"]).read_text().count("transcribe")
    finally:
        first.send_signal(signal.SIGKILL)
        finish_tty(first)
    block.unlink()

    status, after_kill = api.call("GET", "/api/import")
    assert (
        status == 200 and not after_kill["running"] and after_kill["run"]["status"] == "interrupted"
    )
    assert api.post("/api/import/start")[0] == 202
    done = wait_done(api)
    assert done["run"]["status"] == "finished" and done["sources"]["slack"]["fetched"] == 3


def test_failed_item_shows_stage_and_error_and_the_next_import_retries_only_it(
    home, stub_env, serve
):
    api = serve({**stub_env, "STUB_FAIL": "transcribe:b"})
    assert api.post("/api/import/start")[0] == 202
    done = wait_done(api)
    assert done["failed"] == [
        {"source": "slack", "item": "b", "stage": "transcribe", "error": "RuntimeError: boom"}
    ]
    assert done["sources"]["slack"]["failed"] == 1

    Path(stub_env["STUB_LOG"]).unlink()
    code, _ = run_import(home, stub_env)
    assert code == 0
    assert sorted(
        set(Path(stub_env["STUB_LOG"]).read_text().split())
        - {"transcribe", "normalise", "extract", "link"}
    ) == ["b"]
    assert api.call("GET", "/api/import")[1]["failed"] == []


def test_pick_list_is_shared_with_the_cli_and_says_only_picked_reach_claude(tmp_path, home, serve):
    env, _ = make_env(tmp_path, home, "slack-conversation-list")
    api = serve(env)
    status, listed = api.call("GET", "/api/slack/picks")
    assert status == 200 and "Only picked conversations" in listed["note"]
    by_name = {c["name"]: c for c in listed["conversations"]}
    assert {"kind": "private", "members": 4}.items() <= by_name["atlas-leads"].items()

    ids = [by_name["atlas-dev"]["id"]]
    status, saved = api.post("/api/slack/picks", {"pick": ids})
    assert status == 200 and [c["name"] for c in saved["conversations"] if c["picked"]] == [
        "atlas-dev"
    ]
    out = run_librarian(["slack", "pick", "--list"], home, env=env).stdout
    assert "[x] atlas-dev" in out

    master = popen_librarian_tty(["slack", "pick"], home, env)
    os.write(master.pty_master, b"1 2\n\n")
    finish_tty(master)
    cli_picked = {
        c["name"] for c in api.call("GET", "/api/slack/picks")[1]["conversations"] if c["picked"]
    }
    assert cli_picked == {"atlas-dev"} ^ {c["name"] for c in listed["conversations"][:2]}
    assert api.post("/api/slack/picks", {"pick": "x"})[0] == 400
