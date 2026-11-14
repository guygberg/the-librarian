from playwright.sync_api import expect
from test_review import ATLAS, suggest

from fixtures.scenarios import payments_cutover as payments
from fixtures.scenarios import projects_stable_ids as stable
from support.recordings import run_import
from support.ui_stream import person, record

API = """async (path) => {
  const token = document.querySelector('meta[name=librarian-token]').content;
  return (await fetch(path, { headers: { 'X-Librarian-Token': token } })).json();
}"""


def test_person_cards_count_the_open_items_and_open_into_items(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    raz = ui.sql("SELECT id FROM persons WHERE name = 'Raz Peretz'")[0][0]
    record(ui, "Review the budget", owner=raz)
    record(ui, "Pay the vendor", owner=raz)
    page.goto(ui.url + "/people")
    card = page.locator("[data-part=person]", has_text="Raz Peretz")
    items = page.evaluate(API, "/api/open-items?scope=all")["records"]
    owned = sum(1 for r in items if r["group"] and r.get("owner") == "Raz Peretz")
    assert owned >= 2
    expect(card.locator("[data-part=person-owned]")).to_have_text(f"{owned} own")

    card.locator("[data-part=person-name]").click()
    expect(page.locator("[data-part=person-detail]")).to_be_visible()
    expect(page.locator("[data-part=person-owned-list] [data-part=person-item]")).to_have_count(
        owned
    )
    page.locator("[data-part=person-items]").click()
    expect(page).to_have_url(ui.url + "/items?owner=Raz+Peretz")
    # Rows owned by someone else sit in a collapsed group: follow the link without a pointer.
    page.locator("[data-part=row-owner]").first.dispatch_event("click")
    expect(page).to_have_url(ui.url + "/people?person=Raz%20Peretz")


def test_project_cards_match_the_items_and_link_both_ways(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(ui.url + "/projects")
    card = page.locator("[data-part=project]", has_text=payments.PROJECT)
    items = page.evaluate(API, "/api/open-items?scope=all")["records"]
    mine = [
        r
        for r in items
        if r["group"] and any(p["title"] == payments.PROJECT for p in r["projects"])
    ]
    expect(card.locator("[data-part=project-open]")).to_have_text(f"{len(mine)} open")
    expect(card.locator("[data-part=project-basis]")).to_be_visible()

    card.locator("[data-part=project-items]").click()
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    page.locator("[data-part=row-project]").first.click()
    expect(page.locator("[data-part=project]")).to_have_count(1)
    expect(page.locator("[data-part=all-projects]")).to_be_visible()


def test_a_project_confirmed_on_the_projects_page_stays_confirmed_after_import(page, ui):
    ui = ui("projects-stable-ids", stable.NOW)
    page.goto(ui.url + "/projects")
    card = page.locator("[data-part=project]").filter(
        has=page.get_by_role("link", name=ATLAS, exact=True)
    )
    basis = card.locator("[data-part=project-basis]")
    expect(basis).to_have_text("Inferred")
    card.locator("[data-part=project-correct] > summary").click()
    with page.expect_response("**/confirm"):
        card.locator("[data-part=project-confirm]").click()
    expect(page).to_have_url(ui.url + "/projects")
    expect(basis).to_have_text("Confirmed")
    code, out = run_import(ui.home, ui.env)
    assert code == 0, out
    page.reload()
    expect(basis).to_have_text("Confirmed")


def test_review_rows_say_why_and_a_suggested_owner_is_not_needs_attention(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    person(ui, "Dani Cohen")
    rid = suggest(ui, "Send the invoice", "Dani")
    page.goto(ui.url + "/review")
    row = page.locator("[data-part=review-row]", has_text='"Dani"')
    expect(row.locator("[data-part=review-reason]")).to_contain_text(
        "nothing is assigned until you accept"
    )
    expect(row.locator("[data-part=review-basis]")).to_contain_text("Basis: inferred")
    items = page.evaluate(API, "/api/open-items?scope=all")["records"]
    assert next(r for r in items if r["id"] == rid)["group"] != "needs_attention"
    with page.expect_response("**/accept"):
        row.locator("[data-part=review-accept-new]").click()
    expect(page.locator("[data-part=review-row]", has_text='"Dani"')).to_have_count(0)
