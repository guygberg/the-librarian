import re
from datetime import UTC, datetime

from playwright.sync_api import expect

from fixtures.scenarios import onboarding_hebrew as hebrew
from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP, open_stream, person, record, row


def test_header_groups_and_other_open_expands_in_place(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    me = person(ui, "Dana Levi", me=True)
    raz = ui.sql("SELECT id FROM persons WHERE name = 'Raz Peretz'")[0][0]
    record(ui, "Send the invoice", owner=me)
    record(ui, "Chase the vendor", lifecycle="pending", owner=me)
    record(ui, "Review the budget", owner=raz)
    answer = ui.answer("open-items")

    open_stream(page, ui)
    assert page.locator("[data-part=date-line]").text_content() == "Tue 14 Nov · work"
    assert page.locator("[data-part=headline]").text_content() == answer["headline"]["text"]
    assert answer["headline"] == {"needs_you": 2, "waiting": 1, "text": "2 things need you, 1 waiting on someone else"}
    progress = answer["progress"]
    expect(page.locator(".barl")).to_have_text(f"{progress['done_this_week']} of {progress['total']} items finished this week")

    headings = [t.strip() for t in page.locator("[data-part=group]").all_text_contents()]
    assert headings == ["Needs attention", "Waiting on others", "Other open"]
    order = page.locator("[data-part=item] .t").all_text_contents()
    assert order[:3] == [r["title"] for r in answer["records"] if r["group"] != "other_open"]

    budget = row(page, "Review the budget")
    expect(budget).to_be_hidden()
    page.get_by_text("Other open").click()
    expect(budget).to_be_visible()
    assert page.url == ui.url + "/"


def test_basis_markers_and_warnings(page, ui):
    ui = ui("onboarding-hebrew", hebrew.NOW, hebrew.CONFIG)
    ui.sql("UPDATE persons SET is_me = 1 WHERE name = 'Dana Levi'")
    ui.sql("UPDATE records SET basis = 'confirmed' WHERE title = ?", hebrew.SIGNUP)
    ui.sql("UPDATE records SET basis = 'inferred' WHERE title = ?", hebrew.LEGAL)
    signup, legal = (ui.sql("SELECT id FROM records WHERE title = ?", t)[0][0] for t in (hebrew.SIGNUP, hebrew.LEGAL))
    # The signup item's other Evidence is the doubtful "Thursday" segment.
    [(file_id,)] = ui.sql("SELECT substr(locator, 7, instr(locator, '/') - 7) FROM evidence WHERE record_id = ?", signup)
    ui.sql(
        "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role, retrieved_at)"
        " SELECT workspace, record_id, revision_id, ?, quote, role, retrieved_at FROM evidence WHERE record_id = ?",
        f"drive:{file_id}/2", signup,
    )
    ui.sql("INSERT INTO links (workspace, type, from_type, from_id, to_type, to_id, created_at)"
           " VALUES ('work', 'contradicts', 'record', ?, 'record', ?, ?)", signup, legal, STAMP)
    stranger = record(ui, "Call the landlord")
    ui.sql("INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at)"
           " VALUES ('work', 'unknown_speaker', ?, 'owner', NULL, ?)", stranger, STAMP)
    pending = record(ui, "Book the venue", owner=person(ui, "Dana Levi", me=False))
    ui.sql("INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at)"
           " VALUES ('work', 'unconfirmed_person', ?, 'owner', 'Dani', ?)", pending, STAMP)

    page.goto(ui.url)
    expect(page.locator("[data-part=headline]")).to_be_visible()

    signup_row = row(page, hebrew.SIGNUP)
    expect(signup_row.locator("[data-part=basis-confirmed]")).to_have_text("Confirmed")
    assert signup_row.locator("[data-part=basis-confirmed]").evaluate("e => getComputedStyle(e).borderTopStyle") == "solid"
    expect(signup_row.locator("[data-part=warning]")).to_have_text(["Sources disagree", "Transcription uncertain"])

    legal_row = row(page, hebrew.LEGAL)
    expect(legal_row.locator("[data-part=basis-inferred]")).to_have_text("Inferred")
    assert legal_row.locator("[data-part=basis-inferred]").evaluate("e => getComputedStyle(e).borderTopStyle") == "dashed"
    expect(legal_row.locator("[data-part=warning]")).to_have_text(["Sources disagree", "Not mentioned since Oct 22"])
    expect(legal_row).to_contain_text("No owner")

    expect(row(page, "Call the landlord").locator("[data-part=warning]")).to_have_text(["unknown speaker"])
    unconfirmed = row(page, "Book the venue")
    expect(unconfirmed.locator("[data-part=warning]")).to_have_text(["unconfirmed person"])
    expect(unconfirmed).not_to_contain_text("Needs attention")


def test_freshness_line_is_on_every_route_and_navigation_keeps_the_page(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    freshness = page.locator("[data-part=freshness]")
    expect(freshness).to_contain_text("Updated from slack")
    expect(freshness).to_contain_text("claude sessions never imported")
    expect(freshness).to_contain_text("recordings")

    page.evaluate("window.librarianNavigate('/nowhere')")
    expect(page).to_have_url(ui.url + "/nowhere")
    expect(page.locator("[data-part=headline]")).to_have_count(0)
    expect(freshness).to_contain_text("Updated from slack")

    page.go_back()
    expect(page.locator("[data-part=headline]")).to_be_visible()
    page.goto(ui.url + "/nowhere")
    expect(page.locator("[data-part=freshness]")).to_contain_text("Updated from slack")


def test_static_files_are_served_from_the_static_folder_only(ui):
    served = ui("payments-cutover", payments.NOW).served
    resp, body = served.request("GET", "/static/views/stream.js")
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/javascript")
    assert "__TOKEN__" not in body
    assert served.request("GET", "/static/../app.py")[0].status == 404
    assert served.request("GET", "/static/%2e%2e/app.py")[0].status == 404
    assert served.request("GET", "/static/nope.js")[0].status == 404


def test_empty_state_is_calm_and_names_the_last_import(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    ui.sql("UPDATE records SET lifecycle = 'dropped' WHERE kind = 'blocker'")
    stamp = ui.answer("open-items")["freshness"]["last_import_finished_at"]
    imported = datetime.fromisoformat(stamp.replace(" ", "T")).replace(tzinfo=UTC)

    page.clock.set_fixed_time(imported)
    page.goto(ui.url)
    empty = page.locator("[data-part=empty]")
    expect(empty).to_have_text(f"Nothing needs you today. Last import {imported:%H:%M}.")
    body = page.locator("body").inner_text().lower()
    assert not re.search(r"confetti|badge|streak|points|congrat", body)
    assert page.locator("audio, video, canvas").count() == 0
