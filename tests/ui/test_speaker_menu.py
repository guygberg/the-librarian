import json

from playwright.sync_api import expect

from fixtures.scenarios import people_aliases as p
from support.ui_stream import open_item, open_stream, row

SHEET = "[data-part=source-sheet]"
MARK = "[data-part=warning]"


def start(page, ui):
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    ui = ui("people-aliases", p.NOW, f"me_names = [{me_names}]\n")
    open_stream(page, ui)
    unknown = row(page, "By first person")
    expect(unknown.locator(MARK)).to_have_text(["unknown speaker"])
    panel = open_item(page, "By first person")
    expect(panel.locator(MARK)).to_have_text(["unknown speaker"])
    panel.locator("[data-part=evidence-quote]").first.click()
    expect(page.locator(SHEET)).to_be_visible()
    return ui


def owner_of(ui):
    return ui.sql(
        "SELECT p.name FROM records r JOIN people p ON p.id = r.owner_person_id"
        " WHERE r.title = 'By first person'"
    )


def test_pick_a_person_from_the_line_sets_the_owner_and_clears_the_mark_after_reload(page, ui):
    ui = start(page, ui)

    page.locator(f"{SHEET} [data-part=evidence-line] [data-part=speaker-pick]").select_option(
        label="Dana Cohen"
    )

    # The item's page under the sheet is drawn again: the mark is gone and the owner is named.
    panel = page.locator("[data-part=item-expanded]")
    expect(panel.locator("[data-part=owner]")).to_have_text("Dana Cohen")
    expect(panel.locator(MARK)).to_have_count(0)
    assert owner_of(ui) == [("Dana Cohen",)]
    page.reload()
    expect(panel.locator("[data-part=owner]")).to_have_text("Dana Cohen")
    expect(panel.locator(MARK)).to_have_count(0)
    # The row in the list agrees (it shows the owner's first name, the full one as its title).
    page.locator(f"{SHEET} [data-part=close-sheet]").click()
    panel.locator("[data-part=back-to-items]").click()
    listed = row(page, "By first person")
    expect(listed.locator("[data-part=row-owner]")).to_have_attribute("title", "Dana Cohen")
    expect(listed.locator(MARK)).to_have_count(0)


def test_a_typed_name_becomes_a_new_person_with_that_alias(page, ui):
    ui = start(page, ui)

    typed = page.locator(f"{SHEET} [data-part=evidence-line] [data-part=speaker-name]")
    typed.fill("Noa Bar")
    typed.press("Enter")

    expect(page.locator("[data-part=item-expanded] [data-part=owner]")).to_have_text("Noa Bar")
    assert owner_of(ui) == [("Noa Bar",)]
    assert ui.sql(
        "SELECT a.value FROM people p, json_each(p.aliases) a WHERE a.value = 'Noa Bar'"
    ) == [("Noa Bar",)]
