import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from extract.results import UNIT_TEXT
from extract.test_stage import NOW, THREAD_KEY, canned, make_env, run_import, show, thread_result
from librarian import config, db
from librarian.extract import claude_runner, runs, schema
from librarian.extract.claude_runner import ClaudeExtractor, ExtractionFailed
from support.cli import run_librarian

STUB = Path(__file__).parent / "stubs" / "claude"


def envelope(**over):
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "total_cost_usd": 0.01,
            "structured_output": {"records": []},
            **over,
        }
    )


@pytest.fixture
def stub(tmp_path, monkeypatch):
    """The stub `claude` first on PATH; `reply(*texts)` scripts its answers, one per call."""
    bin_dir, state = tmp_path / "bin", tmp_path / "stub"
    bin_dir.mkdir()
    state.mkdir()
    shutil.copy(STUB, bin_dir / "claude")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_DIR", str(state))

    def reply(*texts):
        for n, text in enumerate(texts, 1):
            (state / f"response.{n}").write_text(text)

    def calls():
        return sorted(state.glob("call.*.argv"))

    reply(envelope())
    return reply, calls, state


def extractor(**over):
    return ClaudeExtractor({**config.DEFAULTS, **over})


def test_every_required_flag_goes_out_with_the_unit_on_stdin_and_telemetry_off(stub):
    _, calls, _ = stub

    out = extractor(claude_model="claude-sonnet-5-5").extract("u1", UNIT_TEXT, [])

    assert json.loads(out) == {"records": []}
    [argv_file] = calls()
    argv = argv_file.read_text().split("\0")[:-1]  # NUL-separated: the schema argument has newlines
    assert argv[0] == "-p"  # the stub sees $@, so no program name
    flag = lambda name: argv[argv.index(name) + 1]  # noqa: E731
    assert flag("--output-format") == "json"
    assert json.loads(flag("--json-schema")) == schema.SCHEMA
    assert flag("--tools") == ""
    assert flag("--model") == "claude-sonnet-5-5"
    assert flag("--max-turns") == "3" and flag("--max-budget-usd") == "1.0"
    for lone in ("--strict-mcp-config", "--safe-mode", "--no-session-persistence"):
        assert lone in argv
    assert "--bare" not in argv
    assert (
        UNIT_TEXT not in argv
        and Path(str(argv_file).replace(".argv", ".stdin")).read_text() == UNIT_TEXT
    )
    env = Path(str(argv_file).replace(".argv", ".env")).read_text().splitlines()
    for line in (
        "DISABLE_TELEMETRY=1",
        "DISABLE_ERROR_REPORTING=1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
    ):
        assert line in env


def test_version_is_read_and_a_pin_that_does_not_match_fails(stub, monkeypatch):
    assert extractor().meta.claude_code_version == "2.1.0 (Claude Code)"
    assert extractor().meta.model == config.DEFAULTS["claude_model"]
    with pytest.raises(ExtractionFailed, match="pins claude_code_version 9.9"):
        _ = extractor(claude_code_version="9.9").meta


@pytest.mark.parametrize(
    ("answer", "stage", "needle"),
    [
        (
            envelope(subtype="error_max_turns", is_error=True, result="ran out of turns"),
            "result",
            "error_max_turns",
        ),
        (envelope(structured_output=None), "result", "structured_output"),
        ("Sorry, something broke", "envelope", "not JSON"),
    ],
)
def test_a_bad_envelope_fails_the_unit_with_stage_and_error_and_keeps_the_envelope(
    stub, home, monkeypatch, answer, stage, needle
):
    reply, _, _ = stub
    reply(answer)
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    conn = db.connect_rw("work")

    with pytest.raises(ExtractionFailed) as err:
        runs.extract_and_record(
            conn, "work", extractor(), extractor().meta, "u1", UNIT_TEXT, [], set()
        )

    assert err.value.stage == stage and needle in err.value.error
    [run] = json.loads(run_librarian(["runs", "--json"], home).stdout)
    assert run["envelope"] == answer
    assert run["accepted_records"] == 0
    assert (
        run["rejected"][0]["piece"] == stage and run["rejected"][0]["reason"] == "extraction_failed"
    )
    assert needle in run["rejected"][0]["detail"]


def test_an_accepted_unit_keeps_the_whole_envelope_not_just_the_output(stub, home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    conn = db.connect_rw("work")

    runs.extract_and_record(conn, "work", extractor(), extractor().meta, "u1", UNIT_TEXT, [], set())

    [run] = json.loads(run_librarian(["runs", "--json"], home).stdout)
    assert run["envelope"] == envelope() and run["claude_code_version"] == "2.1.0 (Claude Code)"


def test_overload_twice_then_success_gives_one_result_after_backing_off(stub, monkeypatch):
    reply, calls, _ = stub
    overloaded = envelope(
        subtype="error_during_execution", is_error=True, result="API Error: 529 overloaded"
    )
    reply(overloaded, overloaded, envelope())
    sleeps, real_sleep = [], claude_runner.time.sleep

    def sleep(
        seconds,
    ):  # subprocess polling shares time.sleep; only the backoff waits are patched out
        sleeps.append(seconds) if seconds >= 1 else real_sleep(seconds)

    monkeypatch.setattr(claude_runner.time, "sleep", sleep)

    out = extractor(claude_backoff_seconds=5).extract("u1", UNIT_TEXT, [])

    assert json.loads(out) == {"records": []}
    assert len(calls()) == 3
    assert sleeps == [5, 10]


def test_overload_that_never_clears_fails_after_the_retry_limit(stub, monkeypatch):
    reply, calls, _ = stub
    reply(envelope(subtype="error_during_execution", is_error=True, result="rate limit reached"))
    monkeypatch.setattr(
        claude_runner, "time", type("T", (), {"sleep": staticmethod(lambda s: None)})
    )

    with pytest.raises(ExtractionFailed, match="still failing after 3 tries"):
        extractor(claude_retries=2).extract("u1", UNIT_TEXT, [])
    assert len(calls()) == 3


def test_concurrency_reaches_the_configured_workers_and_never_exceeds_them(monkeypatch):
    workers, lock, running, peak = 2, threading.Lock(), [0], [0]
    meeting = threading.Barrier(workers, timeout=5)

    def call(self, stdin):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        try:
            meeting.wait()
        except threading.BrokenBarrierError:
            pass  # the last unit has no partner
        with lock:
            running[0] -= 1
        return stdin

    monkeypatch.setattr(ClaudeExtractor, "_call", call)
    monkeypatch.setattr(ClaudeExtractor, "_claude_version", lambda self: "1")
    items = [(f"u{i}", f"text {i}", []) for i in range(6)]

    got = dict(extractor(claude_workers=workers).extract_stream(items))

    assert got == {key: text for key, text, _ in items}
    assert peak[0] == workers


def test_real_engines_import_stores_records_like_the_fake_does(tmp_path, home, stub, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    reply, calls, _ = stub
    env, fixtures = make_env(tmp_path, home, "base", NOW)
    fake_run = {**env, "LIBRARIAN_ENGINES": "fake"}
    assert (
        run_import_with(home, fake_run, "--max-calls", "0") == 0
    )  # fetch everything, extract nothing
    with db.connect_rw(
        "work"
    ) as conn:  # drop the picks so the real Slack client stays idle: no network
        conn.execute("DELETE FROM slack_picks")
    reply(envelope(structured_output=thread_result()))
    canned(
        fixtures, THREAD_KEY, result=thread_result()
    )  # unused by the real engine; proves it is not read

    code, out = run_import(home, {**env, "LIBRARIAN_ENGINES": "real"})

    assert code == 0, out
    assert [show(home, i)["title"] for i in (1, 2, 3)] == [
        "Atlas",
        "SQLite with FTS5",
        "Draft the schema",
    ]
    assert calls(), "the stub claude was never called"
    assert any(
        r["envelope"] == envelope(structured_output=thread_result())
        for r in json.loads(run_librarian(["runs", "--json"], home).stdout)
    )


def run_import_with(home, env, *args):
    from support.cli import finish_tty, popen_librarian_tty

    code, _ = finish_tty(popen_librarian_tty(["import", *args], home, env))
    return code


@pytest.mark.skipif(
    os.environ.get("LIBRARIAN_MAC_SMOKE") != "1", reason="real claude runs only on the work Mac"
)
def test_mac_smoke_real_claude_returns_a_schema_valid_result():
    cfg = config.load()
    out = ClaudeExtractor(cfg).extract("smoke", "Dana: I will send the rollout plan by Friday.", [])
    assert isinstance(json.loads(out)["records"], list)
