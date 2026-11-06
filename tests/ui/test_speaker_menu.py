import json

from fixtures.scenarios import people_aliases as p
from playwright.sync_api import expect
from support.ui_stream import open_stream, row

SHEET = "[data-part=source-sheet]"
MARK = "[data-part=warning]"


def start(page, ui):
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    ui = ui("people-aliases", p.NOW, f"me_names = [{me_names}]\n")
    open_stream(page, ui)
    unknown = row(page, "By first person")
    expect(unknown.locator(MARK)).to_have_text(["unknown speaker"])
    unknown.locator(".t a").click()
    page.locator("[data-part=item-expanded] [data-part=evidence-quote]").first.click()
    expect(page.locator(SHEET)).to_be_visible()
    return ui


def owner_of(ui):
    return ui.sql("SELECT p.name FROM records r JOIN persons p ON p.id = r.owner_person_id WHERE r.title = 'By first person'")


def test_pick_a_person_from_the_line_sets_the_owner_and_clears_the_mark_after_reload(page, ui):
    ui = start(page, ui)

    page.locator(f"{SHEET} [data-part=evidence-line] [data-part=speaker-pick]").select_option(label="Dana Cohen")

    expect(row(page, "By first person").locator(MARK)).to_have_count(0)
    assert owner_of(ui) == [("Dana Cohen",)]
    page.reload()
    expect(row(page, "By first person")).to_contain_text("Dana Cohen")
    expect(row(page, "By first person").locator(MARK)).to_have_count(0)


def test_a_typed_name_becomes_a_new_person_with_that_alias(page, ui):
    ui = start(page, ui)

    typed = page.locator(f"{SHEET} [data-part=evidence-line] [data-part=speaker-name]")
    typed.fill("Noa Bar")
    typed.press("Enter")

    expect(row(page, "By first person")).to_contain_text("Noa Bar")
    assert owner_of(ui) == [("Noa Bar",)]
    assert ui.sql("SELECT alias FROM aliases WHERE alias = 'Noa Bar'") == [("Noa Bar",)]
