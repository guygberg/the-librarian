import re

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import person, record

API = """async (path) => {
  const token = document.querySelector('meta[name=librarian-token]').content;
  return (await fetch(path, { headers: { 'X-Librarian-Token': token } })).json();
}"""


def seed(ui):
    me = person(ui, "Dana Levi", me=True)
    raz = person(ui, "Raz Peretz")
    record(ui, "Mine open", owner=me)
    record(ui, "Chase vendor", lifecycle="pending", owner=me)
    record(ui, "Raz task", owner=raz, basis="confirmed")
    shipped = record(ui, "Shipped it", lifecycle="done", owner=me)
    [(blocker,)] = ui.sql("SELECT id FROM records WHERE title = ?", payments.BLOCKER)
    # A done Record only counts as done when some Evidence completes it.
    ui.sql(
        "INSERT INTO evidence"
        " (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
        " SELECT workspace, ?, revision_id, locator, 'sent it', 'completes',"
        " retrieved_at FROM evidence WHERE record_id = ?",
        shipped,
        blocker,
    )


LIST_TITLES = "[data-part=item] [data-part=item-title]"
CARD_TITLES = "[data-part=item] strong"


def cards(page, scope=""):
    return page.locator(f"{scope} {CARD_TITLES}").all_text_contents()


def listed_on_every_page(page):
    """The titles of the whole table, walked seven rows at a time."""
    out = []
    pages = page.locator("[data-part=page]")
    for n in range(pages.count()):
        pages.nth(n).click()
        expect(page.locator("[data-part=page].active")).to_have_text(str(n + 1))
        out += page.locator(LIST_TITLES).all_text_contents()
    return out


def test_list_and_board_hold_the_same_records_and_board_columns_follow_the_groups(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url + "/items")
    expect(page.locator("[data-part=view-tab].active")).to_have_text("List")
    expect(page.locator("[data-part=item]").first).to_be_visible()
    answer = page.evaluate(API, "/api/open-items?scope=all")
    open_titles = {r["title"] for r in answer["records"] if r["group"]}
    listed = listed_on_every_page(page)
    assert len(listed) == len(set(listed))
    assert set(listed) == open_titles
    assert "Shipped it" not in listed
    page.locator("[data-part=page]").first.click()
    assert page.url == ui.url + "/items"

    page.locator("[data-part=view-tab]", has_text="Board").click()
    expect(page.locator("[data-part=board]")).to_be_visible()
    assert page.url == ui.url + "/items?view=board"
    headings = page.locator("[data-part=board] [data-part=group]").all_text_contents()
    assert [re.sub(r"\s*\d+$", "", h) for h in headings] == ["Needs you", "Waiting", "Open"]
    assert cards(page, "[data-part=col-needs]") == [payments.BLOCKER, "Mine open"]
    assert cards(page, "[data-part=col-waiting]") == ["Chase vendor"]
    assert cards(page, "[data-part=col-other]") == ["Raz task"]
    for part, group in (
        ("col-needs", "needs_attention"),
        ("col-waiting", "waiting_on_others"),
        ("col-other", "other_open"),
    ):
        in_group = {r["title"] for r in answer["records"] if r["group"] == group}
        assert set(cards(page, f"[data-part={part}]")) == in_group
    assert set(cards(page)) == set(listed)
    expect(page.locator("[data-part=col-done]")).to_have_count(0)

    # Finished work has its own column, on the Completed tab.
    page.locator("[data-part=kind-tab]", has_text="Completed").click()
    assert page.url == ui.url + "/items?view=board&kind=done"
    done = {r["title"] for r in answer["records"] if r["lifecycle"] == "done"}
    expect(page.locator(f"[data-part=col-done] {CARD_TITLES}")).to_have_text(["Shipped it"])
    assert set(cards(page)) == done == {"Shipped it"}
    page.locator("[data-part=view-tab]", has_text="List").click()
    expect(page.locator(LIST_TITLES)).to_have_text(["Shipped it"])


def test_row_shows_kind_lifecycle_and_filters_live_in_the_url(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url + "/items?basis=confirmed")
    expect(page.locator("[data-part=basis-filter]")).to_have_value("confirmed")
    expect(page.locator(LIST_TITLES)).to_have_text(["Raz task"])
    expect(page.locator("[data-part=row-kind]")).to_have_text("Action item")
    lifecycle = page.locator("[data-part=row-lifecycle]")
    expect(lifecycle).to_have_text("Open")
    expect(lifecycle).to_have_attribute("data-lifecycle", "open")

    # The board keeps the filter: the banner names it and clears it.
    page.locator("[data-part=view-tab]", has_text="Board").click()
    assert page.url == ui.url + "/items?view=board&basis=confirmed"
    expect(page.locator(CARD_TITLES)).to_have_text(["Raz task"])
    expect(page.locator("[data-part=filter-banner]")).to_contain_text("1 matching item · confirmed")
    page.locator("[data-part=clear-filters]").click()
    assert page.url == ui.url + "/items?view=board"
    page.locator("[data-part=lifecycle-filter]").select_option("pending")
    assert page.url == ui.url + "/items?view=board&lifecycle=pending"
    expect(page.locator(CARD_TITLES)).to_have_text(["Chase vendor"])

    page.reload()
    expect(page.locator(CARD_TITLES)).to_have_text(["Chase vendor"])
    expect(page.locator("[data-part=lifecycle-filter]")).to_have_value("pending")
    expect(page.locator("[data-part=view-tab].active")).to_have_text("Board")

    page.locator("[data-part=view-tab]", has_text="List").click()
    assert page.url == ui.url + "/items?lifecycle=pending"
    expect(page.locator(LIST_TITLES)).to_have_text(["Chase vendor"])
    expect(page.locator("[data-part=row-lifecycle]")).to_have_text("Waiting")
    expect(page.locator("[data-part=row-lifecycle]")).to_have_attribute("data-lifecycle", "pending")


def test_phone_width_has_no_page_overflow_in_either_view(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.set_viewport_size({"width": 390, "height": 800})
    for query in ("", "?view=board"):
        page.goto(ui.url + "/items" + query)
        expect(page.locator("[data-part=item]").first).to_be_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
