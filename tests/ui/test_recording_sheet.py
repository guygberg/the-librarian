from playwright.sync_api import expect

from fixtures.scenarios import onboarding_hebrew as hebrew
from fixtures.scenarios import recording_uncertain_hebrew as spoken
from support.ui_stream import open_stream, row

SHEET = "[data-part=source-sheet]"
THURSDAY_SEGMENT = 2  # after the intro line; starts at UNCERTAIN_START


def open_thursday(page, ui):
    """Point the signup item's Evidence at the doubtful-word segment and open its source sheet."""
    [(file_id,)] = ui.sql(
        "SELECT substr(stable_id, 1, instr(stable_id, '/') - 1) FROM source_items"
        " WHERE source = 'drive' LIMIT 1"
    )
    ui.sql(
        "UPDATE evidence SET locator = ?, quote = ?, gloss = 'Meet on Thursday morning',"
        " revision_id = (SELECT r.id FROM source_item_revisions r"
        " JOIN source_items i ON i.id = r.source_item_id WHERE i.stable_id = ?)"
        " WHERE locator = ?",
        f"drive:{file_id}/{THURSDAY_SEGMENT}",
        spoken.UNCERTAIN_TEXT,
        f"{file_id}/{THURSDAY_SEGMENT}",
        f"drive:{file_id}/1",
    )
    open_stream(page, ui)
    row(page, hebrew.SIGNUP).locator(".t a").click()
    page.locator("[data-part=item-expanded] [data-part=evidence-quote]").first.click()
    expect(page.locator(SHEET)).to_be_visible()
    return file_id


def test_recording_evidence_opens_a_player_at_the_segment_start(page, ui):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    file_id = open_thursday(page, ui)

    player = page.locator(f"{SHEET} [data-part=player]")
    expect(player).to_have_attribute("src", f"/media/drive/{file_id}")
    assert (
        page.evaluate("document.querySelector('[data-part=player]').currentTime")
        == hebrew.UNCERTAIN_START
    )
    # the cookie set by the page shell is what lets the media request through
    assert page.request.get(f"{ui.url}/media/drive/{file_id}").status == 200


def test_sheet_title_names_the_recording_with_date_and_range_and_shows_the_line_before(page, ui):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    open_thursday(page, ui)

    sheet = page.locator(SHEET)
    expect(sheet).to_contain_text("Recording · Onboarding")
    expect(sheet).not_to_contain_text("drive:")
    expect(sheet.locator("[data-part=sheet-when]")).to_have_text("Oct 20 · 00:09:14 — 00:09:19")
    before = sheet.locator("[data-part=source-line]").first
    expect(before).to_contain_text(hebrew.SIGNUP_LINE)
    assert before.evaluate("e => e.compareDocumentPosition(e.parentNode.querySelector('.hl')) & 4")


def test_hebrew_quote_is_rtl_with_a_labelled_gloss_naming_the_uncertain_word(page, ui):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    open_thursday(page, ui)

    evidence = page.locator(f"{SHEET} [data-part=evidence-line]")
    quote = evidence.locator("[data-part=quote]")
    expect(quote).to_have_attribute("dir", "rtl")
    expect(quote).to_contain_text(spoken.UNCERTAIN_TEXT)
    uncertain = quote.locator("mark.unc")
    expect(uncertain).to_have_text("Thursday")
    gloss = evidence.locator("[data-part=gloss]")
    expect(gloss).to_contain_text("Meet on Thursday morning")
    expect(gloss).to_contain_text("uncertain: “Thursday”")
    expect(gloss.locator("[data-part=gloss-label]")).to_have_text("machine translation")


def test_low_confidence_segment_says_so_in_plain_words_and_clear_ones_do_not(page, ui):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    open_thursday(page, ui)

    lines = page.locator(f"{SHEET} .ln")
    mumble = lines.filter(has_text=spoken.MUMBLE_TEXT)
    expect(mumble.locator("[data-part=low-confidence]")).to_have_text("low confidence")
    expect(page.locator(f"{SHEET} [data-part=low-confidence]")).to_have_count(1)
