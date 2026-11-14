from urllib.parse import quote, quote_plus

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


def open_items(page):
    return [r for r in page.evaluate(API, "/api/open-items?scope=all")["records"] if r["group"]]


def test_person_cards_count_the_open_items_and_open_into_items(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    raz = ui.sql("SELECT id FROM people WHERE name = 'Raz Peretz'")[0][0]
    record(ui, "Review the budget", owner=raz)
    record(ui, "Pay the vendor", owner=raz)
    page.goto(ui.url + "/people")
    card = page.locator("[data-part=person]", has_text="Raz Peretz")
    items = open_items(page)
    owned = [r for r in items if r.get("owner") == "Raz Peretz"]
    related = [
        r
        for r in items
        if r.get("owner") == "Raz Peretz" or any(link["to"] == "Raz Peretz" for link in r["links"])
    ]
    assert len(owned) >= 2
    expect(card.locator("[data-part=person-name]")).to_have_text("Raz Peretz")
    expect(card.locator("[data-part=person-owned]")).to_have_text(f"{len(owned)} open items owned")

    # A person's items open as the Items list narrowed to them: every open item they own or
    # are linked to, and nothing else.
    card.locator("[data-part=person-items]").click()
    expect(page).to_have_url(ui.url + "/items?person=Raz+Peretz")
    expect(page.locator("main h1")).to_have_text("Raz Peretz")
    titles = page.locator("[data-part=item] [data-part=item-title]")
    expect(titles).to_have_count(len(related))
    assert sorted(titles.all_inner_texts()) == sorted(r["title"] for r in related)

    # The owner of a row leads back to that person on the People page.
    page.locator("button[data-part=row-owner]").first.click()
    expect(page).to_have_url(ui.url + "/people?person=Raz%20Peretz")
    expect(page.locator("[data-part=person-find]")).to_have_value("Raz Peretz")
    expect(page.locator("[data-part=person] [data-part=person-name]")).to_have_text(["Raz Peretz"])

    # The first related item on the card opens that item.
    page.locator("[data-part=person] [data-part=person-item]").click()
    expect(page.locator("[data-part=item-expanded]")).to_be_visible()


def test_project_cards_match_the_items_and_link_both_ways(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(ui.url + "/projects")
    cards = page.locator("[data-part=project]")
    card = cards.filter(has_text=payments.PROJECT)
    mine = [
        r for r in open_items(page) if any(p["title"] == payments.PROJECT for p in r["projects"])
    ]
    noun = "item" if len(mine) == 1 else "items"
    expect(card.locator("[data-part=project-open]")).to_have_text(f"{len(mine)} open {noun}")
    expect(card.locator("[data-part=project-basis]")).to_be_visible()
    everything = cards.count()

    card.locator("[data-part=project-items]").click()
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    expect(page.locator("main h1")).to_have_text(payments.PROJECT)
    expect(page.locator("[data-part=item]")).to_have_count(len(mine))

    # From the whole Items list, a row's project narrows the list to that project.
    page.goto(ui.url + "/items")
    page.locator("button[data-part=row-project]", has_text=payments.PROJECT).first.click()
    expect(page).to_have_url(f"{ui.url}/items?project={quote_plus(payments.PROJECT)}")
    expect(page.locator("[data-part=status-header]")).to_be_visible()

    # An item names its project, which opens that one project on the Projects page.
    page.locator("[data-part=item-title]").first.click()
    page.locator("[data-part=detail-project]", has_text=payments.PROJECT).click()
    expect(page).to_have_url(f"{ui.url}/projects?project={quote(payments.PROJECT)}")
    expect(cards).to_have_count(1)
    expect(cards.locator("[data-part=project-name]")).to_have_text(payments.PROJECT)
    page.locator("[data-part=all-projects]").click()
    expect(page).to_have_url(ui.url + "/projects")
    expect(cards).to_have_count(everything)


def test_a_project_confirmed_on_the_projects_page_stays_confirmed_after_import(page, ui):
    ui = ui("projects-stable-ids", stable.NOW)
    page.goto(ui.url + "/projects")
    card = page.locator("[data-part=project]").filter(has=page.get_by_text(ATLAS, exact=True))
    basis = card.locator("[data-part=project-basis]")
    expect(basis).to_have_text("Inferred")
    card.locator("[data-part=project-correct]").click()
    tools = page.locator("dialog[open] [data-part=project-tools]")
    with page.expect_response("**/confirm"):
        tools.locator("[data-part=project-confirm]").click()
    expect(page.locator("dialog[open]")).to_have_count(0)
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
