import json

from playwright.sync_api import expect
from test_expanded import expand

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP

SHEET = "[data-part=source-sheet]"


def first_quote(panel):
    return panel.locator("[data-part=evidence-quote]").first


def test_slack_quote_opens_the_thread_with_the_evidence_line_and_the_permalink(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    [(locator,)] = ui.sql(
        "SELECT locator FROM evidence"
        " WHERE record_id = (SELECT id FROM records WHERE title = ?) LIMIT 1",
        payments.NOV_18,
    )
    ts = locator.split("/", 1)[1]

    first_quote(expand(page, ui, payments.NOV_18)).click()

    sheet = page.locator(SHEET)
    expect(sheet).to_be_visible()
    assert f"source={locator.replace(':', '%3A').replace('/', '%2F')}" in page.url
    marked = sheet.locator("[data-part=evidence-line]")
    expect(marked).to_have_count(1)
    stored = ui.sql("SELECT quote FROM evidence WHERE locator = ?", locator)[0][0]
    expect(marked).to_contain_text(stored.split()[0])
    link = sheet.locator("[data-part=open-original]")
    assert link.get_attribute("href").startswith(
        f"{payments.URL}archives/C001/p{ts.replace('.', '')}"
    )
    assert link.get_attribute("target") == "_blank"


def test_deleted_slack_message_says_gone_from_slack_in_evidence_and_sheet_and_keeps_the_quote(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    [(locator,)] = ui.sql("SELECT locator FROM evidence WHERE record_id = (SELECT id FROM records WHERE title = ?) LIMIT 1", payments.NOV_18)
    ui.sql("UPDATE source_items SET gone = 1 WHERE source = 'slack' AND stable_id = ?", locator.split(":", 1)[1])
    stored = ui.sql("SELECT quote FROM evidence WHERE locator = ?", locator)[0][0]

    panel = expand(page, ui, payments.NOV_18)
    expect(panel.locator("[data-part=gone-from-source]").first).to_have_text("gone from Slack")
    expect(first_quote(panel)).to_have_text(stored)

    first_quote(panel).click()
    marked = page.locator(SHEET).locator("[data-part=evidence-line]")
    expect(marked.locator("[data-part=gone-from-source]")).to_have_text("gone from Slack")
    expect(marked).to_contain_text(stored.split()[0])


def test_session_quote_opens_the_raw_jsonl_passage(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    lines = [{"role": "user", "text": f"line {n}"} for n in (1, 2, 3)]
    for n, line in enumerate(lines, 1):
        ui.sql(
            "INSERT INTO source_items (id, workspace, source, stable_id, created_at)"
            " VALUES (?, 'work', 'session', ?, ?)",
            900 + n,
            f"s1/{n}",
            STAMP,
        )
        ui.sql(
            "INSERT INTO source_item_revisions"
            " (id, workspace, source_item_id, revision, content_hash, content, fetched_at)"
            " VALUES (?, 'work', ?, 1, ?, ?, ?)",
            900 + n,
            900 + n,
            f"h{n}",
            json.dumps(line),
            STAMP,
        )
    ui.sql(
        "UPDATE evidence SET locator = 'session:s1/2', revision_id = 902, quote = 'line 2'"
        " WHERE id = ("
        " SELECT MIN(id) FROM evidence WHERE record_id = (SELECT id FROM records WHERE title = ?))",
        payments.NOV_18,
    )

    first_quote(expand(page, ui, payments.NOV_18)).click()

    sheet = page.locator(SHEET)
    expect(sheet.locator("[data-part=evidence-line]")).to_contain_text("line 2")
    raw = sheet.locator("[data-part=raw-passage]")
    expect(raw).to_be_hidden()
    sheet.locator("[data-part=open-original]").click()
    expect(raw).to_be_visible()
    for line in lines:
        assert json.dumps(line) in raw.text_content()


def test_reload_restores_the_sheet_and_closing_keeps_the_stream_position(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    panel = expand(page, ui, payments.NOV_18)
    page.evaluate("document.body.style.minHeight = '4000px'; window.scrollTo(0, 300)")
    first_quote(panel).click()
    expect(page.locator(SHEET)).to_be_visible()

    page.reload()
    expect(page.locator(SHEET)).to_be_visible()
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()

    page.evaluate("document.body.style.minHeight = '4000px'; window.scrollTo(0, 300)")
    page.locator("[data-part=close-sheet]").click()
    expect(page.locator(SHEET)).to_have_count(0)
    assert "source=" not in page.url
    assert page.evaluate("window.scrollY") == 300
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()
