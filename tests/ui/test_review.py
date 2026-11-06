from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from fixtures.scenarios import projects_stable_ids as stable
from support.recordings import run_import
from support.ui_stream import STAMP, open_stream, person, record, row

ROW = "[data-part=review-row]"
MARK = "[data-part=warning]"
COUNT = "[data-part=open-review]"
ATLAS, ATLASES = "Atlas Migration", "Atlas Migrations"
OPEN = "SELECT count(*) FROM review_entries WHERE resolved_at IS NULL"


def suggest(ui, title, raw_name, kind="unconfirmed_person"):
    rid = record(ui, title)
    ui.sql("INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at)"
           " VALUES ('work', ?, ?, 'owner', ?, ?)", kind, rid, raw_name, STAMP)
    return rid


def people(ui):
    dani = person(ui, "Dani Cohen")
    ui.sql("INSERT INTO aliases (workspace, person_id, alias) VALUES ('work', ?, 'Dani')", dani)
    return dani, person(ui, "Dana Levi")


def start(page, ui, scenario="payments-cutover", now=payments.NOW):
    ui = ui(scenario, now)
    open_stream(page, ui)
    return ui


def dani_rows(page):
    return page.locator(ROW, has_text='"Dani"')


def test_count_matches_rows_and_accept_and_reject_settle_the_suggestions(page, ui):
    ui = start(page, ui)
    dani, _ = people(ui)
    suggest(ui, "Send the invoice", "Dani")
    suggest(ui, "Chase the vendor", "Dani")
    [(open_now,)] = ui.sql(OPEN)
    page.goto(ui.url)
    expect(row(page, "Send the invoice").locator(MARK)).to_have_text(["unconfirmed person"])

    expect(page.locator(COUNT)).to_have_text(f"{open_now} to review")
    page.locator(COUNT).click()
    expect(page.locator(ROW)).to_have_count(open_now)
    expect(page.locator("[data-part=review-count]")).to_have_text(f"{open_now} to review")

    with page.expect_response("**/accept"):
        dani_rows(page).first.locator("[data-part=review-accept]").click()
    expect(page.locator(ROW)).to_have_count(open_now - 1)
    with page.expect_response("**/reject"):
        dani_rows(page).first.locator("[data-part=review-reject]").click()
    expect(page.locator(ROW)).to_have_count(open_now - 2)
    assert ui.sql("SELECT person_id FROM aliases WHERE alias = 'Dani'") == [(dani,)]
    assert ui.sql("SELECT resolution FROM review_entries WHERE raw_name = 'Dani' ORDER BY id") == [("accepted",), ("rejected",)]

    page.goto(ui.url)
    expect(row(page, "Send the invoice").locator(MARK)).to_have_count(0)


def test_a_review_row_moves_or_splits_the_alias(page, ui):
    ui = start(page, ui)
    dani, dana = people(ui)
    suggest(ui, "Send the invoice", "Dani")
    page.goto(ui.url + "/review")

    with page.expect_response("**/aliases/move"):
        dani_rows(page).locator("[data-part=alias-move]").select_option(label="Dana Levi")
    assert ui.sql("SELECT person_id FROM aliases WHERE alias = 'Dani'") == [(dana,)]
    expect(dani_rows(page).locator("[data-part=candidate]")).to_contain_text("Dana Levi")

    with page.expect_response("**/aliases/split"):
        dani_rows(page).locator("[data-part=alias-split]").click()
    [(new,)] = ui.sql("SELECT person_id FROM aliases WHERE alias = 'Dani'")
    assert new not in (dani, dana)


def test_the_person_node_menu_in_relations_moves_and_splits_an_alias(page, ui):
    ui = start(page, ui)
    dani, dana = people(ui)
    rid = record(ui, "Review the budget", owner=dani)
    page.goto(f"{ui.url}/items/{rid}?tab=relations")

    menu = page.locator("[data-part=person-menu]", has_text="Dani Cohen")
    menu.locator("summary").click()
    expect(menu.locator("[data-part=person-alias]")).to_have_value("Dani")
    with page.expect_response("**/aliases/move"):
        menu.locator("[data-part=alias-move]").select_option(label="Dana Levi")
    assert ui.sql("SELECT person_id FROM aliases WHERE alias = 'Dani'") == [(dana,)]

    ui.sql("UPDATE aliases SET person_id = ? WHERE alias = 'Dani'", dani)
    page.goto(f"{ui.url}/items/{rid}?tab=relations")
    menu = page.locator("[data-part=person-menu]", has_text="Dani Cohen")
    menu.locator("summary").click()
    with page.expect_response("**/aliases/split"):
        menu.locator("[data-part=alias-split]").click()
    [(new,)] = ui.sql("SELECT person_id FROM aliases WHERE alias = 'Dani'")
    assert new not in (dani, dana)


def test_project_confirm_rename_and_merge_from_the_status_header(page, ui):
    ui = start(page, ui, "projects-stable-ids", stable.NOW)
    [(open_now,)] = ui.sql(OPEN)
    page.goto(f"{ui.url}/review")
    expect(page.locator(ROW)).to_have_count(open_now)
    expect(page.locator(ROW, has_text="inferred project")).to_have_count(2)

    page.goto(f"{ui.url}/?project={ATLAS.replace(' ', '%20')}")
    tools = page.locator("[data-part=project-tools]")
    drawn = tools.locator("[data-part=project-name]").element_handle()
    with page.expect_response("**/confirm"):
        tools.locator("[data-part=project-confirm]").click()
    # The page draws again after the response, replacing the header: a fill before that is lost.
    page.wait_for_function("el => !el.isConnected", arg=drawn)
    assert ui.sql("SELECT basis FROM records WHERE title = ?", ATLAS) == [("confirmed",)]

    tools.locator("[data-part=project-name]").fill("Atlas Cloud")
    with page.expect_response("**/rename"):
        tools.locator("[data-part=project-rename]").click()
    expect(page.locator("[data-part=status-header] .t").first).to_have_text("Atlas Cloud")

    with page.expect_response("**/merge"):
        page.locator("[data-part=project-merge]").select_option(label=ATLASES)
    expect(page.locator("[data-part=status-header] .t").first).to_have_text(ATLASES)
    code, out = run_import(ui.home, ui.env)
    assert code == 0, out
    assert ui.sql("SELECT lifecycle FROM records WHERE title = 'Atlas Cloud'") == [("superseded",)]


def test_split_moves_the_ticked_items_to_a_new_project(page, ui):
    ui = start(page, ui, "projects-stable-ids", stable.NOW)
    page.goto(f"{ui.url}/?project={ATLASES}")
    tools = page.locator("[data-part=project-tools]")
    tools.locator("[data-part=project-split] summary").click()
    tools.locator("[data-part=split-name]").fill("Rollout")
    tools.locator("[data-part=split-item] input").first.check()
    with page.expect_response("**/split"):
        tools.locator("[data-part=split-go]").click()
    assert ui.sql("SELECT count(*) FROM records WHERE title = 'Rollout' AND kind = 'project'") == [(1,)]


def test_an_expired_token_shows_an_error_and_changes_nothing(page, ui):
    ui = start(page, ui)
    people(ui)
    suggest(ui, "Send the invoice", "Dani")
    [(open_now,)] = ui.sql(OPEN)
    page.goto(ui.url + "/review")
    page.route("**/api/review/*/accept", lambda route: route.continue_(headers={**route.request.headers, "x-librarian-token": "stale"}))

    dani_rows(page).locator("[data-part=review-accept-new]").click()

    expect(dani_rows(page).locator("[data-part=review-error]")).to_have_text("This page has expired. Reload it.")
    assert ui.sql(OPEN) == [(open_now,)]
