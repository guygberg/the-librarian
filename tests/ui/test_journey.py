"""The acceptance journey through the production `librarian serve` route, on desktop and phone.

Set `LIBRARIAN_SHOTS=<dir>` to also save a PNG of each screen the review package shows.
"""

import os
from pathlib import Path
from urllib.parse import quote

import pytest
from playwright.sync_api import expect
from test_recording_sheet import SHEET, open_thursday

from fixtures.scenarios import onboarding_hebrew as hebrew
from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP, person, record

SIZES = {"desktop": {"width": 1280, "height": 900}, "phone": {"width": 390, "height": 800}}
SHOTS = os.environ.get("LIBRARIAN_SHOTS")


def shot(page, size, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"{SHOTS}/{size}-{name}.png", full_page=name != "source-sheet")


def seed(ui):
    me = person(ui, "Dana Levi", me=True)
    [(raz,)] = ui.sql("SELECT id FROM people WHERE name = 'Raz Peretz'")
    dani = person(ui, "Dani Cohen")
    ui.sql(
        "UPDATE people SET aliases = json_insert(aliases, '$[#]', 'Dani')"
        " WHERE workspace = 'work' AND id = ?",
        dani,
    )
    record(ui, "Mine open", owner=me)
    record(ui, "Raz decision", owner=raz, basis="confirmed")
    suggested = record(ui, "Send the invoice")
    ui.sql(
        "INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at)"
        " VALUES ('work', 'unconfirmed_person', ?, 'owner', 'Dani', ?)",
        suggested,
        STAMP,
    )


@pytest.mark.parametrize("size", SIZES)
def test_acceptance_journey(page, ui, size):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.set_viewport_size(SIZES[size])
    base = ui.url

    # Today: real counts, and the recommended item opens.
    page.goto(base)
    expect(page.locator("[data-part=counts]")).to_be_visible()
    page.wait_for_function("document.querySelector('[data-part=count-open] b')")
    shot(page, size, "today")
    page.locator("[data-part=next-open]").click()
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()
    rid_url = page.url

    # Items: List and Board share the filtered set; filters live in the URL.
    page.goto(base + "/items")
    expect(page.locator("[data-part=view-tab].active")).to_have_text("List")
    shot(page, size, "items-list")
    page.get_by_text("Board", exact=True).click()
    expect(page.locator("[data-part=board]")).to_be_visible()
    shot(page, size, "items-board")
    page.goto(f"{base}/items?project={quote(payments.PROJECT)}&kind=decisions")
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    page.goto(f"{base}/items?owner=Raz+Peretz&lifecycle=open")
    expect(page.locator("[data-part=item] [data-part=item-title]")).to_have_text(["Raz decision"])
    page.goto(base + "/items")

    # Item detail: all four tabs, then Evidence in the source sheet.
    page.goto(rid_url)
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()
    shot(page, size, "item-detail")
    for tab in ("activity", "sources", "relations"):
        page.goto(f"{rid_url.split('?')[0]}?tab={tab}")
        expect(page.locator("[data-part=item-expanded]")).to_be_visible()
    expect(page.locator("[data-part=relations-graph]")).to_be_visible()
    shot(page, size, "relations")
    page.goto(f"{rid_url.split('?')[0]}?tab=sources")
    page.locator("[data-part=item-expanded] [data-part=evidence-quote]").first.click()
    expect(page.locator(SHEET)).to_be_visible()
    shot(page, size, "source-sheet")

    # Complete from Today, and take it back with the confirmation's Undo.
    page.goto(base)
    done = page.locator("[data-part=today-done]").first
    done.click()
    expect(page.locator("[data-part=completed-item]")).to_have_count(1)
    page.locator("#toast [data-part=undo]").click()
    expect(page.locator("[data-part=completed-item]")).to_have_count(0)

    # People and Projects.
    page.goto(base + "/people")
    expect(page.locator("[data-part=person]", has_text="Raz Peretz")).to_be_visible()
    shot(page, size, "people")
    page.goto(base + "/projects")
    expect(page.locator("[data-part=project]", has_text=payments.PROJECT)).to_be_visible()
    shot(page, size, "projects")

    # Review: accept one suggestion, reject another.
    page.goto(base + "/review")
    rows = page.locator("[data-part=review-row]", has_text='"Dani"')
    expect(rows.first).to_be_visible()
    shot(page, size, "review")
    with page.expect_response("**/accept"):
        rows.first.locator("[data-part=review-accept]").click()

    # Import: open the panel and run a dry run, then reload a deep URL.
    page.goto(base + "/import")
    expect(page.locator("[data-part=import-sources]")).to_be_visible()
    page.locator("[data-part=dry-run-button]").click()
    expect(page.locator("[data-part=import-progress]")).to_be_visible()
    shot(page, size, "import")
    deep = f"{base}/items?project={quote(payments.PROJECT)}&view=board"
    page.goto(deep)
    page.reload()
    assert page.url == deep
    expect(page.locator("[data-part=board]")).to_be_visible()


@pytest.mark.parametrize("size", SIZES)
def test_recording_plays_at_its_timestamp(page, ui, size):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    page.set_viewport_size(SIZES[size])
    open_thursday(page, ui)
    assert (
        page.evaluate("document.querySelector('[data-part=player]').currentTime")
        == hebrew.UNCERTAIN_START
    )
