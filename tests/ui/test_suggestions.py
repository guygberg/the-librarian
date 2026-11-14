import json
import os
from pathlib import Path

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP

CARD = "[data-part=suggestion]"
SHEET = "[data-part=source-sheet]"
NAV = "[data-part=nav-review-count]"


def seed(ui):
    """Three graded Suggestions over a real quote: tag (high), item (medium) and link (low)."""
    [(revision, locator, quote)] = ui.sql(
        "SELECT revision_id, locator, quote FROM evidence WHERE locator LIKE 'slack:%' LIMIT 1"
    )
    ui.sql(
        "INSERT INTO extraction_runs (workspace, unit_key, model, claude_code_version, prompt_hash,"
        " schema_hash, envelope, accepted, created_at, purpose)"
        " VALUES ('work', 'u', 'm', 'v', 'p', 's', '{}', 1, ?, 'suggestions')",
        STAMP,
    )
    [(run,)] = ui.sql("SELECT max(id) FROM extraction_runs")
    tag = {"kind": "new_tag", "title": "Refund Edge Cases"}
    item = {"kind": "new_item", "title": "Chase the vendor"}
    rows = [
        ("new_tag", None, {"title": tag["title"]}, 92, "high", "stated", "Named outright."),
        ("new_item", None, {"title": item["title"]}, 61, "medium", "inferred", "Implied."),
        ("link", "belongs_to", {"from": item, "to": tag}, 45, "low", "inferred", "Maybe."),
    ]
    for n, (kind, link_type, payload, confidence, band, basis, why) in enumerate(rows):
        ui.sql(
            "INSERT INTO suggestions (workspace, kind, link_type, payload, run_id, confidence,"
            " band, basis, reasoning, dedupe_key, created_at)"
            " VALUES ('work', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            *(kind, link_type, json.dumps(payload), run, confidence, band, basis, why),
            f"k{n}",
            f"2025-10-{10 + n}T00:00:00Z",
        )
    ui.sql(
        "INSERT INTO suggestion_evidence (workspace, suggestion_id, revision_id, locator, quote)"
        " SELECT 'work', id, ?, ?, ? FROM suggestions",
        revision,
        locator,
        quote,
    )
    return locator, quote


def start(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed_result = seed(ui)
    page.goto(ui.url + "/review")
    return ui, seed_result


def entries(ui):
    """Review entries the scenario already holds: the count adds them to the Suggestions."""
    return ui.sql("SELECT count(*) FROM review_entries WHERE resolved_at IS NULL")[0][0]


def test_cards_show_label_grade_reasoning_and_both_ends_of_a_link(page, ui):
    ui, _ = start(page, ui)
    cards = page.locator(CARD)
    expect(cards).to_have_count(3)
    expect(cards.nth(0).locator("[data-part=suggestion-label]")).to_have_text("Suggested new tag")
    expect(cards.nth(0).locator("[data-part=suggestion-confidence]")).to_have_text("92% confident")
    expect(cards.nth(0).locator("[data-part=suggestion-reasoning]")).to_have_text("Named outright.")
    expect(cards.nth(1)).to_have_attribute("data-band", "medium")
    low = cards.nth(2)
    expect(low.locator("[data-part=suggestion-label]")).to_have_text("Suggested link")
    expect(low.locator("[data-part=suggestion-end]")).to_have_text(
        ["Chase the vendor (new item)", "Refund Edge Cases (new tag)"]
    )
    expect(low.locator("[data-part=suggestion-band]")).to_contain_text("may well be wrong")
    expect(page.locator("[data-part=review-count]")).to_have_text(f"{3 + entries(ui)} to review")


def test_band_filter_and_sort_follow_the_url(page, ui):
    start(page, ui)
    page.locator("[data-part=band-chip]", has_text="Medium").click()
    expect(page.locator(CARD)).to_have_count(1)
    assert "band=medium" in page.url
    page.locator("[data-part=band-chip]", has_text="All").click()
    expect(page.locator(CARD)).to_have_count(3)
    page.locator("[data-part=sort-chip]", has_text="Newest").click()
    expect(page.locator(CARD).first.locator("[data-part=suggestion-label]")).to_have_text(
        "Suggested link"
    )
    page.locator("[data-part=sort-chip]", has_text="Confidence").click()
    expect(page.locator(CARD).first.locator("[data-part=suggestion-label]")).to_have_text(
        "Suggested new tag"
    )


def test_screens_at_desktop_and_phone_widths(page, ui, tmp_path):
    """Captures the product for comparison with docs/review/canonical; LIBRARIAN_SHOTS keeps it."""
    out = Path(os.environ.get("LIBRARIAN_SHOTS", tmp_path))
    ui, _ = start(page, ui)
    for name, width, height in (("desktop", 1280, 1074), ("phone", 390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        page.goto(ui.url + "/review")
        expect(page.locator(CARD)).to_have_count(3)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=out / f"{name}-suggestions.png", full_page=name == "desktop")


def test_the_evidence_quote_opens_its_source(page, ui):
    _, (locator, quote) = start(page, ui)
    first = page.locator(CARD).first.locator("[data-part=evidence-quote]")
    expect(first).to_have_text(quote)
    first.click()
    expect(page.locator(SHEET)).to_be_visible()
    assert locator.split(":", 1)[0] in page.url or "source=" in page.url


def test_accept_and_dismiss_settle_cards_and_every_counter_agrees(page, ui):
    ui, _ = start(page, ui)
    base = entries(ui)
    expect(page.locator(NAV)).to_have_text(str(3 + base))
    with page.expect_response("**/suggestions/*/accept"):
        page.locator(CARD).first.locator("[data-part=suggestion-accept]").click()
    expect(page.locator(CARD)).to_have_count(2)
    expect(page.locator(NAV)).to_have_text(str(2 + base))
    assert ui.sql("SELECT status FROM suggestions ORDER BY id")[0] == ("accepted",)
    with page.expect_response("**/suggestions/*/reject"):
        page.locator(CARD).first.locator("[data-part=suggestion-dismiss]").click()
    expect(page.locator(CARD)).to_have_count(1)
    expect(page.locator(NAV)).to_have_text(str(1 + base))
    page.goto(ui.url + "/")
    expect(page.locator("[data-part=count-review] b")).to_have_text(str(1 + base))
    expect(page.locator("[data-part=today-suggestion]")).to_have_count(1)
    expect(page.locator(NAV)).to_have_text(str(1 + base))
