from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import STAMP, person, record

API = """async (path) => {
  const token = document.querySelector('meta[name=librarian-token]').content;
  return (await fetch(path, { headers: { 'X-Librarian-Token': token } })).json();
}"""


def seed(ui):
    me = person(ui, "Dana Levi", me=True)
    raz = person(ui, "Raz Peretz")
    for n in range(1, 8):
        record(ui, f"Task {n}", owner=me)
    record(ui, "Chase the vendor", lifecycle="pending", owner=me)
    record(ui, "Review the budget", owner=raz)
    quote = record(ui, "Which vendor", kind="open_question")
    ui.sql(
        "INSERT INTO review_entries (workspace, kind, record_id, link_type, raw_name, created_at)"
        " VALUES ('work', 'unknown_speaker', ?, 'owner', NULL, ?)",
        quote,
        STAMP,
    )


def count(page, part):
    return int(page.locator(f"[data-part={part}] b").text_content())


def test_counts_match_the_api_and_next_best_move_opens(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url)
    expect(page.locator("[data-part=counts]")).to_be_visible()
    page.wait_for_function("document.querySelector('[data-part=count-open] b')")
    items = page.evaluate(API, "/api/open-items?scope=all")
    review = page.evaluate(API, "/api/review")
    grouped = [r["group"] for r in items["records"] if r["group"]]
    assert count(page, "count-open") == len(grouped)
    assert count(page, "count-needs") == grouped.count("needs_attention")
    assert count(page, "count-waiting") == grouped.count("waiting_on_others")
    assert count(page, "count-review") == review["count"]

    first = next(r for r in items["records"] if r["group"] == "needs_attention")
    expect(page.locator("[data-part=next-title]")).to_have_text(first["title"])
    expect(page.locator("[data-part=next-why]")).to_contain_text("Ranked first of")
    page.locator("[data-part=next-open]").click()
    expect(page).to_have_url(f"{ui.url}/items/{first['id']}")


def test_panels_page_and_completing_updates_every_count(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    seed(ui)
    page.goto(ui.url)
    needs = page.locator("[data-part=needs]")
    total = count(page, "count-needs")
    open_before = count(page, "count-open")
    assert total > 5
    expect(needs.locator("[data-part=today-item]")).to_have_count(5)
    expect(needs.locator("[data-part=needs-range]")).to_have_text(f"1–5 of {total}")
    needs.locator("[data-part=needs-next]").click()
    expect(needs.locator("[data-part=today-item]")).to_have_count(total - 5)
    expect(needs.locator("[data-part=needs-next]")).to_be_disabled()
    needs.locator("[data-part=needs-prev]").click()
    expect(needs.locator("[data-part=needs-range]")).to_have_text(f"1–5 of {total}")

    expect(page.locator("[data-part=completed] [data-part=empty]")).to_be_visible()
    needs.locator("[data-part=today-done]").first.click()
    expect(page.locator("[data-part=count-needs] b")).to_have_text(str(total - 1))
    assert count(page, "count-open") == open_before - 1
    done = page.locator("[data-part=completed-item]")
    expect(done).to_have_count(1)
    expect(done.locator("[data-part=completed-at]")).to_contain_text("Finished")
    expect(page.locator("[data-part=person-event]")).to_have_count(1)

    done.locator("[data-part=today-reopen]").click()
    expect(page.locator("[data-part=count-needs] b")).to_have_text(str(total))
    assert count(page, "count-open") == open_before
    expect(done).to_have_count(0)


def test_quiet_workspace_shows_calm_truthful_empty_states(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    ui.sql("DELETE FROM review_entries")
    ui.sql("UPDATE records SET lifecycle = 'dropped'")
    page.goto(ui.url)
    expect(page.locator("[data-part=count-open] b")).to_have_text("0")
    expect(page.locator("[data-part=next-best-move]")).to_have_count(0)
    expect(page.locator("[data-part=needs] [data-part=empty]")).to_contain_text(
        "Nothing needs you today."
    )
    expect(page.locator("[data-part=waiting] [data-part=empty]")).to_have_text(
        "Nothing is waiting on someone else."
    )
    expect(page.locator("[data-part=review] [data-part=empty]")).to_have_text("Nothing to review.")
    expect(page.locator("[data-part=completed] [data-part=empty]")).to_have_text(
        "Nothing has been finished yet."
    )
