from datetime import datetime

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import NOW, STAMP, open_stream, person, record, row

KICKOFF = "Plan the kickoff"


def link(ui, kind, from_id, to_type, to_id):
    ui.sql(
        "INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
        " VALUES ('work', ?, 'record', ?, ?, ?, ?)", kind, from_id, to_type, to_id, STAMP,
    )


def second_project(ui):
    """An Onboarding project with one open item, next to the scenario's Payments project."""
    project = record(ui, "Onboarding revamp", kind="project")
    link(ui, "belongs_to", record(ui, KICKOFF), "record", project)


def titles(page):
    return page.locator("[data-part=item] .t").all_text_contents()


def test_project_chip_filters_the_stream_and_shows_the_status_header(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    second_project(ui)
    open_stream(page, ui)

    chips = page.locator("[data-part=project-chip]")
    expect(chips).to_have_text(["All work", payments.PROJECT, "Onboarding revamp"])
    expect(page.locator("[data-part=status-header]")).to_have_count(0)
    expect(row(page, KICKOFF)).to_be_visible()

    chips.get_by_text(payments.PROJECT).click()
    header = page.locator("[data-part=status-header]")
    expect(header).to_contain_text(payments.PROJECT)
    expect(header).to_contain_text(payments.BLOCKER)
    expect(header).to_contain_text(payments.NOV_25)
    expect(page.locator("[data-part=changes]")).to_contain_text("changed")
    expect(row(page, KICKOFF)).to_have_count(0)
    expect(row(page, payments.BLOCKER)).to_have_count(1)
    assert page.url == ui.url + "/?project=Payments+migration"

    chips.get_by_text("All work").click()
    expect(header).to_have_count(0)
    expect(row(page, KICKOFF)).to_have_count(1)
    assert page.url == ui.url + "/"


def test_kind_tabs_switch_in_place_and_done_lists_evidence(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    shipped = record(ui, "Ship the report", lifecycle="done")
    [(blocker,)] = ui.sql("SELECT id FROM records WHERE title = ?", payments.BLOCKER)
    ui.sql(
        "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
        " SELECT workspace, ?, revision_id, locator, 'sent it on Monday', 'completes', retrieved_at FROM evidence WHERE record_id = ?",
        shipped, blocker,
    )
    open_stream(page, ui)
    tabs = page.locator("[data-part=kind-tab]")
    expect(tabs).to_have_text(["Items", "Decisions", "Blockers", "Questions", "Done"])

    tabs.get_by_text("Decisions").click()
    expect(page.locator("[data-part=item] .t")).to_have_text([payments.NOV_18, payments.NOV_25, payments.WEBHOOK])
    tabs.get_by_text("Blockers").click()
    expect(page.locator("[data-part=item] .t")).to_have_text([payments.BLOCKER])
    tabs.get_by_text("Questions").click()
    expect(page.locator("[data-part=empty]")).to_have_text("Nothing here.")
    tabs.get_by_text("Done").click()
    expect(page.locator("[data-part=item] .t")).to_have_text(["Ship the report"])
    expect(page.locator("[data-part=item] [data-part=evidence]")).to_contain_text("sent it on Monday")
    assert page.url == ui.url + "/?kind=done"
    tabs.get_by_text("Items").click()
    assert "Ship the report" not in titles(page)


def test_person_filters_narrow_owner_and_waiting_on_and_there_is_no_person_route(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    raz = ui.sql("SELECT id FROM persons WHERE name = 'Raz Peretz'")[0][0]
    me = person(ui, "Dana Levi", me=True)
    record(ui, "Review the budget", owner=raz)
    link(ui, "waiting_on", record(ui, "Chase the vendor", lifecycle="pending", owner=me), "person", raz)
    open_stream(page, ui)

    page.locator("[data-part=owner-filter]").select_option("Raz Peretz")
    expect(page.locator("[data-part=item] .t")).to_have_text(["Review the budget"])
    page.locator("[data-part=owner-filter]").select_option("")
    page.locator("[data-part=waiting-filter]").select_option("Raz Peretz")
    expect(page.locator("[data-part=item] .t")).to_have_text(["Chase the vendor"])
    assert page.url == ui.url + "/?waiting=Raz+Peretz"

    page.goto(ui.url + "/person/raz-peretz")
    expect(page.get_by_text("Nothing here.")).to_be_visible()
    expect(page.locator("[data-part=headline]")).to_have_count(0)


def test_reload_returns_to_the_same_filtered_state(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    second_project(ui)
    page.clock.set_fixed_time(datetime.fromisoformat(NOW))
    page.goto(ui.url + "/?project=Payments+migration&kind=decisions")
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    before = titles(page)
    assert before == [payments.NOV_18, payments.NOV_25, payments.WEBHOOK]

    page.reload()
    expect(page.locator("[data-part=status-header]")).to_be_visible()
    expect(page.locator("[data-part=kind-tab].on")).to_have_text("Decisions")
    expect(page.locator("[data-part=project-chip].on")).to_have_text(payments.PROJECT)
    assert titles(page) == before
