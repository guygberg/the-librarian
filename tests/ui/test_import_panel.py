import os
import re
import signal
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from librarian.fakes.calllog import CallLog
from support.cli import finish_tty, popen_librarian_tty, run_librarian
from support.recordings import make_env, run_import
from support.serve import spawn

STUBS = str(Path(__file__).parents[1] / "importer")
COUNTS = re.compile(r"^(\w+): fetched \d+, transcribed \d+, extracted \d+, failed \d+$", re.M)
PART = "[data-part={}]"


class Served:
    def __init__(self, url, home, env):
        self.url, self.home, self.env = url, home, env


@pytest.fixture
def serve(home, monkeypatch):
    """`librarian serve` over a Workspace nothing was imported into yet."""
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    started = []

    def start(env):
        proc, served = spawn(home, "--port", "0", env=env)
        started.append(proc)
        return Served(f"http://127.0.0.1:{served.port}", home, env)

    yield start
    for proc in started:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()


def pick(home, ids):
    ws = home / "workspaces" / "work"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "channels.json").write_text('{"picked": ' + str(ids).replace("'", '"') + "}")


@pytest.fixture
def stub_env(tmp_path, home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    (tmp_path / "items.txt").write_text("slack/a slack/b slack/c")
    return {
        "LIBRARIAN_STAGES": "stub_stages",
        "PYTHONPATH": os.pathsep.join([STUBS, os.environ.get("PYTHONPATH", "")]),
        "STUB_ITEMS": str(tmp_path / "items.txt"),
        "STUB_LOG": str(tmp_path / "log.txt"),
        "STUB_BLOCK": str(tmp_path / "block"),
        "STUB_FAIL": "",
    }


def extraction_calls(home):
    return len(
        [c for c in CallLog(home / "workspaces" / "work").read() if c["engine"] == "extractor"]
    )


def test_panel_lists_every_part_and_an_import_shows_the_counts_a_cli_import_prints(
    page, tmp_path, home, serve
):
    env, _ = make_env(tmp_path, home, "payments-cutover")
    pick(home, ["C001"])
    cli_home = tmp_path / "cli-home"
    cli_env, _ = make_env(tmp_path / "cli", cli_home, "payments-cutover")
    pick(cli_home, ["C001"])
    code, out = run_import(cli_home, cli_env)
    assert code == 0, out
    served = serve(env)

    page.goto(served.url)
    page.locator(PART.format("open-import")).click()
    for part in (
        "import-sources",
        "import-button",
        "dry-run-button",
        "slack-picker",
        "failed-items",
        "picked-note",
    ):
        expect(page.locator(PART.format(part))).to_be_visible()
    expect(page.locator(PART.format("import-source"))).to_have_count(3)
    expect(page.locator(PART.format("picked-note"))).to_contain_text("Only picked conversations")

    # No dry run first: it fetches and transcribes too, which would leave those counters at 0
    # for the Import.
    page.locator(PART.format("import-button")).click()
    expect(page.locator(PART.format("import-progress"))).to_contain_text(
        "Last import finished", timeout=60_000
    )
    shown = page.locator(PART.format("import-counts")).all_inner_texts()
    last = {
        m[1]: m[0] for m in COUNTS.finditer(out.replace("\r", ""))
    }  # the CLI reprints a line per update
    assert sorted(shown) == sorted(last.values())
    assert extraction_calls(home) == extraction_calls(cli_home)


def test_a_second_start_is_refused_with_the_running_progress_and_the_stream_still_loads(
    page, home, stub_env, serve
):
    block = Path(stub_env["STUB_BLOCK"])
    block.touch()
    first = popen_librarian_tty(["import"], home, stub_env)
    try:
        deadline = time.time() + 30
        while not Path(str(block) + ".started").exists():
            assert time.time() < deadline, "the CLI import never blocked"
            time.sleep(0.05)
        served = serve(stub_env)
        before = Path(stub_env["STUB_LOG"]).read_text()

        page.goto(f"{served.url}/import")
        expect(page.locator(PART.format("import-progress"))).to_contain_text("Import running")
        page.locator(PART.format("import-button")).click()
        expect(page.locator(PART.format("panel-message"))).to_contain_text("already running")
        expect(page.locator(PART.format("import-progress"))).to_contain_text("Import running")
        assert Path(stub_env["STUB_LOG"]).read_text() == before

        page.goto(served.url)
        expect(page.locator(PART.format("headline"))).to_be_visible()
    finally:
        first.send_signal(signal.SIGKILL)
        finish_tty(first)


def test_a_failed_item_shows_stage_and_error_and_the_next_import_retries_only_it(
    page, home, stub_env, serve
):
    served = serve({**stub_env, "STUB_FAIL": "transcribe:b"})
    page.goto(f"{served.url}/import")
    page.locator(PART.format("import-button")).click()

    failed = page.locator(PART.format("failed-item"))
    expect(failed).to_have_count(1, timeout=30_000)
    expect(failed).to_contain_text("slack/b")
    expect(failed.locator(PART.format("failed-stage"))).to_have_text("transcribe")
    expect(failed).to_contain_text("boom")

    Path(stub_env["STUB_LOG"]).unlink()
    code, _ = run_import(home, stub_env)
    assert code == 0
    assert sorted(
        set(Path(stub_env["STUB_LOG"]).read_text().split())
        - {"transcribe", "normalise", "extract", "link"}
    ) == ["b"]
    page.reload()
    expect(page.locator(PART.format("failed-item"))).to_have_count(0)


def test_picking_in_the_panel_reaches_the_cli_and_forgetting_needs_the_typed_name(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(f"{ui.url}/import")
    rows = page.locator(PART.format("pick-row"))
    expect(rows.first).to_be_visible()
    calls = extraction_calls(ui.home)
    page.locator(PART.format("dry-run-button")).click()
    expect(page.locator(PART.format("panel-message"))).to_contain_text("Claude calls would be made")
    assert extraction_calls(ui.home) == calls
    picked = page.locator(f"{PART.format('pick-row')}:has(input:checked)")
    name = picked.locator("span").first.inner_text()

    picked.locator("input").uncheck()
    expect(page.locator(f"{PART.format('pick-row')}:has(input:checked)")).to_have_count(0)
    assert f"[ ] {name}" in run_librarian(["slack", "pick", "--list"], ui.home, env=ui.env).stdout
    rows.filter(has_text=name).locator("input").check()
    expect(picked).to_have_count(1)
    assert f"[x] {name}" in run_librarian(["slack", "pick", "--list"], ui.home, env=ui.env).stdout

    stored = ui.sql("SELECT COUNT(*) FROM source_items WHERE source = 'slack'")[0][0]
    assert stored > 0
    picked.locator(PART.format("forget")).click()
    confirm = page.locator(PART.format("forget-confirm"))
    expect(confirm).to_be_disabled()
    page.locator(PART.format("forget-text")).fill("wrong")
    expect(confirm).to_be_disabled()
    assert ui.sql("SELECT COUNT(*) FROM source_items WHERE source = 'slack'")[0][0] == stored
    page.locator(PART.format("forget-text")).fill(name)
    confirm.click()
    expect(page.locator(PART.format("panel-message"))).to_contain_text(f"Forgot {name}")
    assert ui.sql("SELECT COUNT(*) FROM source_items WHERE source = 'slack'")[0][0] == 0
