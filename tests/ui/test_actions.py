import pytest
from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.recordings import run_import
from support.ui_stream import open_stream, person, record, row


def panel_of(page, ui, item):
    page.goto(f"{ui.url}/items/{item}")
    panel = page.locator("[data-part=item-expanded]")
    expect(panel).to_be_visible()
    return panel


def history(panel):
    return [t.split(" ")[0:2] for t in panel.locator("[data-part=event]").all_text_contents()]


def test_mark_done_updates_the_counts_and_the_item_appears_under_done_with_history(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    me = person(ui, "Dana Levi", me=True)
    item = record(ui, "Send the invoice", owner=me)
    open_stream(page, ui)
    before = ui.answer("open-items")
    expect(page.locator("[data-part=headline]")).to_have_text(before["headline"]["text"])

    row(page, "Send the invoice").locator(".t a").click()
    page.locator("[data-part=act-done]").click()

    after = ui.answer("open-items")
    assert after["headline"]["needs_you"] == before["headline"]["needs_you"] - 1
    expect(page.locator("[data-part=headline]")).to_have_text(after["headline"]["text"])
    expect(page.locator(".barl")).to_have_text(
        f"{after['progress']['done_this_week']} of {after['progress']['total']}"
        " items finished this week"
    )
    expect(page.locator("[data-part=headline]")).to_have_class("settle")
    expect(page.locator("[data-part=lifecycle]")).to_contain_text("Done")
    expect(page.locator("[data-part=act-reopen]")).to_be_visible()

    page.goto(f"{ui.url}/?kind=done")
    done = row(page, "Send the invoice")
    expect(done).to_be_visible()
    done.locator(".t a").click()
    assert "status change" in page.locator("[data-part=event]").first.text_content()
    assert item == int(page.url.split("/items/")[1].split("?")[0])


def test_reopen_owner_and_project_show_in_history_and_survive_reload_and_import(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    me = person(ui, "Dana Levi", me=True)
    item = record(ui, "Send the invoice", owner=me)
    project = ui.sql("SELECT id FROM records WHERE title = ?", payments.PROJECT)[0][0]

    panel = panel_of(page, ui, item)
    panel.locator("[data-part=act-done]").click()
    expect(page.locator("[data-part=lifecycle]")).to_contain_text("Done")
    page.locator("[data-part=act-reopen]").click()
    expect(page.locator("[data-part=lifecycle]")).to_have_text("Open")
    page.locator("[data-part=act-owner]").select_option(label="Raz Peretz")
    page.locator("[data-part=act-project]").select_option(label=payments.PROJECT)
    expect(page.locator("[data-part=act-project]")).to_have_value(str(project))

    def check():
        current = panel_of(page, ui, item)
        expect(current.locator("[data-part=lifecycle]")).to_have_text("Open")
        [view] = [r for r in ui.answer("open-items")["records"] if r["id"] == item]
        assert (view["owner"], [p["id"] for p in view["projects"]]) == ("Raz Peretz", [project])
        events = [
            e.strip()
            for e in current.locator("[data-part=event] span:first-child").all_text_contents()
        ]
        assert events[-4:] == ["status change", "status change", "owner change", "project move"]

    check()
    code, out = run_import(ui.home, ui.env)
    assert code == 0, out
    page.reload()
    check()

    assert item in [c["record_id"] for c in ui.answer("changes")["changes"]]


@pytest.mark.parametrize("outcome", ["holds", "both_wrong"])
def test_resolving_the_date_disagreement(page, ui, outcome):
    ui = ui("payments-cutover", payments.NOW)
    nov_18, nov_25 = (
        ui.sql("SELECT id FROM records WHERE title = ?", t)[0][0]
        for t in (payments.NOV_18, payments.NOV_25)
    )
    panel = panel_of(page, ui, nov_18)
    expect(panel.locator("[data-part=disagreement]")).to_be_visible()

    if outcome == "holds":
        panel.locator("[data-part=side]").nth(0).locator("[data-part=act-holds]").click()
    else:
        panel.locator("[data-part=act-both-wrong]").click()

    expect(page.locator("[data-part=disagreement]")).to_have_count(0)
    expect(
        page.locator("[data-part=item]", has=page.locator("[data-part=item-expanded]"))
    ).to_have_class("it settle")
    expect(page.locator("[data-part=warning]", has_text="Sources disagree")).to_have_count(0)

    for record_id, expected in (
        (nov_18, "Open" if outcome == "holds" else "Dropped"),
        (nov_25, "Superseded" if outcome == "holds" else "Dropped"),
    ):
        page.goto(f"{ui.url}/items/{record_id}")
        expect(page.locator("[data-part=lifecycle]")).to_contain_text(expected)

    page.goto(f"{ui.url}/items/{nov_18}")
    expect(page.locator("[data-part=disagreement]")).to_have_count(0)
    assert any(
        "resolve disagreement" in t for t in page.locator("[data-part=event]").all_text_contents()
    )
    changed = [c["record_id"] for c in ui.answer("changes")["changes"]]
    assert nov_18 in changed and nov_25 in changed


def test_a_failed_get_and_a_failed_post_throw_errors_with_the_same_shape(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(ui.url)
    shapes = page.evaluate(
        """async () => {
          const api = await import('/static/api.js');
          const shape = (p) => p.then(() => null, (e) => [e.status, e.body !== undefined]);
          return [await shape(api.get('/api/no-such-path')), await shape(api.post('/api/no-such-path', {}))];
        }"""
    )
    assert shapes[0] is not None and shapes[0] == shapes[1]
