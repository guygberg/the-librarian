from datetime import datetime

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import NOW, open_stream, record, row


def record_id(ui, title):
    return ui.sql("SELECT id FROM records WHERE title = ?", title)[0][0]


def expand(page, ui, title):
    """Open the Decisions tab (the cutover Records are decisions) and expand `title` in place."""
    open_stream(page, ui)
    page.locator("[data-part=kind-tab]", has_text="Decisions").click()
    row(page, title).locator(".t a").click()
    panel = page.locator("[data-part=item-expanded]")
    expect(panel).to_be_visible()
    return panel


def test_expanding_shows_lifecycle_basis_commitment_and_evidence(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    ui.sql("UPDATE records SET basis = 'inferred' WHERE title = ?", payments.NOV_18)
    cutover = {"id": record_id(ui, payments.NOV_18)}

    panel = expand(page, ui, payments.NOV_18)
    assert page.url == f"{ui.url}/items/{cutover['id']}?kind=decisions"
    expect(panel.locator("[data-part=lifecycle]")).to_have_text("Open")
    expect(panel.locator("[data-part=basis-text]")).to_contain_text("Inferred")
    expect(panel.locator("[data-part=commitment]")).to_have_count(0)
    expect(row(page, payments.NOV_18).locator("[data-part=basis-inferred]")).to_have_text(
        "Inferred"
    )

    evidence = panel.locator(":scope > [data-part=evidence]")
    shown = evidence.all_text_contents()
    assert shown
    stored = ui.sql(
        "SELECT locator, role, quote FROM evidence WHERE record_id = ? ORDER BY id", cutover["id"]
    )
    for (locator, role, quote), text in zip(stored, shown, strict=True):
        assert locator in text and role in text and quote in text

    expect(panel.locator("[data-part=tab-evidence]")).to_have_class("chip on")
    panel.locator("[data-part=tab-relations]").click()
    expect(panel.locator("[data-part=relations-graph]")).to_be_visible()
    assert page.url.endswith(f"/items/{cutover['id']}?kind=decisions&tab=relations")
    expect(evidence).to_have_count(0)

    row(page, payments.NOV_18).locator(".t a").click()
    expect(page.locator("[data-part=item-expanded]")).to_have_count(0)
    assert page.url == ui.url + "/?kind=decisions"


def test_action_item_shows_commitment_and_deadline(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    item = record(ui, "Run a rollback drill")
    ui.sql("UPDATE records SET commitment = 'request', stated_deadline = 'Q1' WHERE id = ?", item)
    page.clock.set_fixed_time(datetime.fromisoformat(NOW))
    page.goto(f"{ui.url}/items/{item}")
    panel = page.locator("[data-part=item-expanded]")
    expect(panel.locator("[data-part=commitment]")).to_have_text("Commitment: request")
    expect(panel.locator("[data-part=deadline]")).to_have_text("Deadline: Q1")


def test_disagreement_shows_both_records_with_their_evidence(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    panel = expand(page, ui, payments.NOV_18)
    expect(panel.locator("[data-part=disagreement]")).to_contain_text("Sources disagree")
    sides = panel.locator("[data-part=side]")
    expect(sides).to_have_count(2)
    expect(sides.nth(0)).to_contain_text(payments.NOV_18)
    expect(sides.nth(1)).to_contain_text(payments.NOV_25)
    for side in (sides.nth(0), sides.nth(1)):
        assert side.locator("[data-part=evidence]").count() >= 1
    expect(sides.nth(1)).to_contain_text(payments.CUTOVER_SPEECH.split(": ")[1])


def test_stale_item_says_stale_after_the_threshold_is_lowered(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.clock.set_fixed_time(datetime.fromisoformat(NOW))
    page.goto(f"{ui.url}/items/{record_id(ui, payments.BLOCKER)}")
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()
    expect(page.locator("[data-part=flag]")).to_have_count(0)

    config = ui.home / "config.toml"
    config.write_text(config.read_text() + "stale_days_blocker = 1\n")
    page.reload()
    expect(page.locator("[data-part=flag]")).to_contain_text(
        "Stale: not mentioned in any source since"
    )


def test_expanded_url_reloads_to_the_same_item_even_when_filtered_out(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    expand(page, ui, payments.NOV_18)
    url = page.url
    page.reload()
    assert page.url == url
    expect(page.locator("[data-part=item-expanded]")).to_have_count(1)
    expect(
        page.locator("[data-part=item]", has=page.locator("[data-part=item-expanded]")).locator(
            ".t"
        )
    ).to_have_text(payments.NOV_18)

    page.goto(url + "?kind=done")
    expect(page.locator("[data-part=item-expanded]")).to_have_count(1)
