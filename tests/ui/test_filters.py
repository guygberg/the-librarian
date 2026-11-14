import re
from datetime import datetime

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import NOW, STAMP, open_stream, person, record, row

KICKOFF = "Plan the kickoff"


def link(ui, kind, from_id, to_type, to_id):
    ui.sql(
        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
        " VALUES ('work', ?, 'record', ?, ?, ?, ?)",
        kind,
        from_id,
        to_type,
        to_id,
        STAMP,
    )


def second_project(ui):
    """An Onboarding project with one open item, next to the scenario's Payments project."""
    project = record(ui, "Onboarding revamp", kind="project")
    link(ui, "belongs_to", record(ui, KICKOFF), "record", project)


TITLES = "[data-part=item] [data-part=item-title]"


def titles(page):
    return page.locator(TITLES).all_text_contents()


def test_project_filter_narrows_the_list_and_shows_the_status_header(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    second_project(ui)
    open_stream(page, ui)

    projects = page.locator("[data-part=project-filter]")
    expect(projects.locator("option")).to_have_text(
        ["Projects", payments.PROJECT, "Onboarding revamp"]
    )
    expect(projects).to_have_value("")
    expect(page.locator("[data-part=status-header]")).to_have_count(0)
    expect(page.locator("[data-part=filter-banner]")).to_have_count(0)
    expect(row(page, KICKOFF)).to_be_visible()

    projects.select_option(payments.PROJECT)
    header = page.locator("[data-part=status-header]")
    expect(header).to_contain_text(payments.PROJECT)
    expect(header).to_contain_text(payments.BLOCKER)
    expect(header).to_contain_text(payments.NOV_25)
    expect(header.locator("[data-part=project-tools]")).to_be_visible()
    expect(page.locator("[data-part=changes]")).to_contain_text("changed")
    expect(page.locator("#view h1")).to_have_text(payments.PROJECT)
    expect(page.locator("[data-part=filter-banner]")).to_contain_text(
        re.compile(rf"^\d+ matching items? · {payments.PROJECT}")
    )
    expect(row(page, KICKOFF)).to_have_count(0)
    expect(row(page, payments.BLOCKER)).to_have_count(1)
    expect(projects).to_have_value(payments.PROJECT)
    assert page.url == ui.url + "/items?project=Payments+migration"

    projects.select_option("")
    expect(header).to_have_count(0)
    expect(row(page, KICKOFF)).to_have_count(1)
    expect(page.locator("#view h1")).to_have_text("Items")
    assert page.url == ui.url + "/items"

    # The banner's own button clears the project too.
    projects.select_option("Onboarding revamp")
    expect(page.locator(TITLES)).to_have_text([KICKOFF])
    page.locator("[data-part=clear-filters]").click()
    expect(row(page, payments.BLOCKER)).to_have_count(1)
    assert page.url == ui.url + "/items"


def test_kind_filter_switches_in_place_and_completed_lists_evidence(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    shipped = record(ui, "Ship the report", lifecycle="done")
    [(blocker,)] = ui.sql("SELECT id FROM records WHERE title = ?", payments.BLOCKER)
    ui.sql(
        "INSERT INTO evidence"
        " (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
        " SELECT workspace, ?, revision_id, locator, 'sent it on Monday', 'completes',"
        " retrieved_at FROM evidence WHERE record_id = ?",
        shipped,
        blocker,
    )
    open_stream(page, ui)
    kinds = page.locator("[data-part=kind-filter]")
    expect(kinds.locator("option")).to_have_text(
        ["Open items", "Decisions", "Blockers", "Questions", "Completed"]
    )
    expect(kinds).to_have_value("items")

    kinds.select_option("decisions")
    expect(page.locator(TITLES)).to_have_text([payments.NOV_18, payments.NOV_25, payments.WEBHOOK])
    assert page.url == ui.url + "/items?kind=decisions"
    kinds.select_option("blockers")
    expect(page.locator(TITLES)).to_have_text([payments.BLOCKER])
    kinds.select_option("questions")
    expect(page.locator("[data-part=empty] h2")).to_have_text("Nothing here.")
    expect(page.locator("[data-part=empty] p")).to_have_text(
        "Try another filter or clear your filters."
    )
    kinds.select_option("done")
    expect(page.locator(TITLES)).to_have_text(["Ship the report"])
    expect(page.locator("[data-part=item] [data-part=evidence]")).to_contain_text(
        "sent it on Monday"
    )
    expect(page.locator("[data-part=item] [data-part=row-lifecycle]")).to_have_text("Completed")
    expect(page.locator("[data-part=kind-tab].active")).to_have_text("Completed")
    assert page.url == ui.url + "/items?kind=done"
    kinds.select_option("items")
    expect(page.locator("[data-part=kind-tab].active")).to_have_text(re.compile("^All items"))
    expect(row(page, payments.BLOCKER)).to_have_count(1)
    expect(page.locator(TITLES, has_text="Ship the report")).to_have_count(0)
    assert page.url == ui.url + "/items"

    # The Completed tab is the same list as the Completed kind.
    page.locator("[data-part=kind-tab]", has_text="Completed").click()
    expect(page.locator(TITLES)).to_have_text(["Ship the report"])
    expect(kinds).to_have_value("done")
    assert page.url == ui.url + "/items?kind=done"


def test_person_filter_narrows_owner_and_waiting_on_and_there_is_no_person_route(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    raz = ui.sql("SELECT id FROM people WHERE name = 'Raz Peretz'")[0][0]
    me = person(ui, "Dana Levi", me=True)
    record(ui, "Review the budget", owner=raz)
    link(
        ui,
        "waiting_on",
        record(ui, "Chase the vendor", lifecycle="pending", owner=me),
        "person",
        raz,
    )
    open_stream(page, ui)

    people = page.locator("[data-part=person-filter]")
    people.select_option("owner:Raz Peretz")
    expect(page.locator(TITLES)).to_have_text(["Review the budget"])
    expect(people).to_have_value("owner:Raz Peretz")
    assert page.url == ui.url + "/items?owner=Raz+Peretz"
    people.select_option("")
    assert page.url == ui.url + "/items"
    people.select_option("waiting:Raz Peretz")
    expect(page.locator(TITLES)).to_have_text(["Chase the vendor"])
    expect(people).to_have_value("waiting:Raz Peretz")
    assert page.url == ui.url + "/items?waiting=Raz+Peretz"

    page.goto(ui.url + "/person/raz-peretz")
    expect(page.get_by_text("Nothing here.")).to_be_visible()
    expect(page.locator("[data-part=headline]")).to_have_count(0)


def test_reload_returns_to_the_same_filtered_state(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    second_project(ui)
    page.clock.set_fixed_time(datetime.fromisoformat(NOW))
    page.goto(ui.url + "/items?project=Payments+migration&kind=decisions")
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    before = titles(page)
    assert before == [payments.NOV_18, payments.NOV_25, payments.WEBHOOK]

    page.reload()
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    expect(page.locator("[data-part=kind-filter]")).to_have_value("decisions")
    expect(page.locator("[data-part=project-filter]")).to_have_value(payments.PROJECT)
    assert titles(page) == before
