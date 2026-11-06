from urllib.parse import quote

from playwright.sync_api import expect
from test_expanded import expand

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import open_stream, record

BOX = "[data-part=search] input"
RESULTS = "[data-part=search-results]"


def press_slash_focuses(page):
    page.locator("body").click(position={"x": 5, "y": 5})
    page.keyboard.press("/")
    expect(page.locator(BOX)).to_be_focused()
    assert page.locator(BOX).input_value() == ""


def test_slash_focuses_search_on_every_view(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    press_slash_focuses(page)

    page.goto(f"{ui.url}/?project={quote(payments.PROJECT)}")
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    press_slash_focuses(page)

    expand(page, ui, payments.NOV_18)
    press_slash_focuses(page)

    page.locator("[data-part=evidence-quote]").first.click()
    expect(page.locator("[data-part=source-sheet]")).to_be_visible()
    press_slash_focuses(page)


def test_slash_is_ignored_while_typing_in_a_field(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    page.locator(BOX).fill("a")
    page.keyboard.press("/")
    assert page.locator(BOX).input_value() == "a/"


def test_hebrew_prefixed_form_finds_the_record_and_opens_it_in_place(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    meeting = record(ui, "סיכום הפגישה", kind="decision", lifecycle="open")
    open_stream(page, ui)

    page.locator(BOX).fill("פגישה")
    page.keyboard.press("Enter")
    results = page.locator(RESULTS)
    expect(results.locator("[data-part=search-record]")).to_have_count(1)
    page.locator("[data-part=search-record-link]").click()

    assert page.url.split("?")[0].endswith(f"/items/{meeting}")
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()


def test_records_come_first_and_a_passage_opens_the_source_sheet(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    page.locator(BOX).fill("cutover")
    page.keyboard.press("Enter")

    parts = page.locator(f"{RESULTS} [data-part^=search-]:not([data-part$=link])")
    expect(parts.first).to_have_attribute("data-part", "search-record")
    kinds = [parts.nth(i).get_attribute("data-part") for i in range(parts.count())]
    assert "search-passage" in kinds
    assert kinds == sorted(kinds, key=lambda k: k != "search-record")

    page.locator("[data-part=search-passage-link]").first.click()
    expect(page.locator("[data-part=source-sheet]")).to_be_visible()
    assert "q=cutover" in page.url


def test_the_url_restores_the_search(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    page.locator(BOX).fill("cutover")
    page.keyboard.press("Enter")
    expect(page.locator("[data-part=search-record]").first).to_be_visible()

    page.reload()

    expect(page.locator(BOX)).to_have_value("cutover")
    expect(page.locator("[data-part=search-record]").first).to_be_visible()
