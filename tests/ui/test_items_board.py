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


def titles(page, scope=""):
    return page.locator(f"{scope} [data-part=item] .t").all_text_contents()


def test_list_and_board_hold_the_same_records_and_board_columns_follow_the_groups(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url + "/items")
    expect(page.locator("[data-part=view-tab].on")).to_have_text("List")
    listed = titles(page)
    assert "Shipped it" not in listed

    page.get_by_text("Board", exact=True).click()
    expect(page.locator("[data-part=board]")).to_be_visible()
    assert page.url == ui.url + "/items?view=board"
    headings = page.locator("[data-part=board] [data-part=group]").all_text_contents()
    assert [h.split(" (")[0] for h in headings] == [
        "Needs attention",
        "Waiting on others",
        "Other open",
        "Done",
    ]
    assert titles(page, "[data-part=col-done]") == ["Shipped it"]
    assert titles(page, "[data-part=col-waiting]") == ["Chase vendor"]
    assert titles(page, "[data-part=col-other]") == ["Raz task"]

    answer = page.evaluate(API, "/api/open-items?scope=all")
    expected = {r["title"] for r in answer["records"] if r["group"] or r["lifecycle"] == "done"}
    assert set(titles(page)) == expected
    assert set(listed) == expected - {"Shipped it"}


def test_row_shows_kind_lifecycle_and_filters_live_in_the_url(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url + "/items?view=board&basis=confirmed")
    expect(page.locator("[data-part=basis-filter]")).to_have_value("confirmed")
    assert titles(page) == ["Raz task"]
    expect(page.locator("[data-part=row-kind]")).to_have_text("action item")
    expect(page.locator("[data-part=row-lifecycle]")).to_have_text("open")

    page.locator("[data-part=basis-filter]").select_option("")
    page.locator("[data-part=lifecycle-filter]").select_option("pending")
    assert page.url == ui.url + "/items?view=board&lifecycle=pending"
    expect(page.locator("[data-part=item] .t")).to_have_text(["Chase vendor"])

    page.reload()
    expect(page.locator("[data-part=item] .t")).to_have_text(["Chase vendor"])
    expect(page.locator("[data-part=lifecycle-filter]")).to_have_value("pending")
    expect(page.locator("[data-part=view-tab].on")).to_have_text("Board")


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
