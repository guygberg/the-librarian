from datetime import datetime

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import NOW, open_item, open_stream, record, row


def record_id(ui, title):
    return ui.sql("SELECT id FROM records WHERE title = ?", title)[0][0]


def expand(page, ui, title):
    """Show the Decisions on the Items page (the cutover Records are decisions) and open `title`'s
    own page from its row."""
    open_stream(page, ui)
    page.locator("[data-part=kind-filter]").select_option("decisions")
    expect(page).to_have_url(f"{ui.url}/items?kind=decisions")
    return open_item(page, title)


def test_expanding_shows_lifecycle_basis_commitment_and_evidence(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    ui.sql("UPDATE records SET basis = 'inferred' WHERE title = ?", payments.NOV_18)
    cutover = {"id": record_id(ui, payments.NOV_18)}

    panel = expand(page, ui, payments.NOV_18)
    assert page.url == f"{ui.url}/items/{cutover['id']}?kind=decisions"
    expect(panel.locator("[data-part=lifecycle]")).to_have_text("Open")
    expect(panel.locator("[data-part=basis-text]")).to_contain_text("Inferred")
    expect(panel.locator("[data-part=commitment]")).to_have_count(0)
    expect(panel.locator("[data-part=details] [data-part=basis-inferred]")).to_have_text("Inferred")

    expect(panel.locator("[data-part=tab-overview]")).to_have_class("tab active")
    expect(panel.locator("[data-part=next-move]")).to_contain_text("Settle which source is right")
    latest = panel.locator("[data-part=body-overview] [data-part=evidence]")
    expect(latest).to_have_count(1)

    panel.locator("[data-part=tab-sources]").click()
    assert page.url.endswith(f"/items/{cutover['id']}?kind=decisions&tab=sources")
    evidence = panel.locator("[data-part^=sources-] > [data-part=evidence]")
    stored = ui.sql(
        "SELECT locator, role, quote FROM evidence WHERE record_id = ? ORDER BY id", cutover["id"]
    )
    expect(evidence).to_have_count(len(stored))
    for locator, role, quote in stored:
        group = panel.locator(f"[data-part=sources-{role}]")
        expect(group).to_contain_text(locator)
        expect(group).to_contain_text(quote)

    panel.locator("[data-part=tab-activity]").click()
    assert page.url.endswith(f"/items/{cutover['id']}?kind=decisions&tab=activity")
    expect(panel.locator("[data-part=tab-activity]")).to_have_class("tab active")
    expect(evidence).to_have_count(0)

    panel.locator("[data-part=tab-relations]").click()
    expect(panel.locator("[data-part=relations-graph]")).to_be_visible()
    assert page.url.endswith(f"/items/{cutover['id']}?kind=decisions&tab=relations")
    expect(evidence).to_have_count(0)

    # Back to the list it was opened from, where the row carries the same Basis mark.
    panel.locator("[data-part=back-to-items]").click()
    expect(page.locator("[data-part=item-expanded]")).to_have_count(0)
    assert page.url == ui.url + "/items?kind=decisions"
    expect(row(page, payments.NOV_18).locator("[data-part=basis-inferred]")).to_have_text(
        "Inferred"
    )


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
    expect(page.locator("[data-part=item-expanded] [data-part=detail-title]")).to_have_text(
        payments.NOV_18
    )

    page.goto(url.split("?")[0] + "?kind=done")
    expect(page.locator("[data-part=item-expanded]")).to_have_count(1)
    expect(page.locator("[data-part=item-expanded] [data-part=detail-title]")).to_have_text(
        payments.NOV_18
    )
