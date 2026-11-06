import re
from urllib.parse import quote

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import open_stream

STRIP = "[data-part=changed-strip]"
BANNED = re.compile(r"confetti|badge|points|streak", re.I)


def start(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    open_stream(page, ui)
    return ui


def urls(ui):
    [(rid,)] = ui.sql("SELECT min(id) FROM records WHERE kind = 'action_item'")
    [(project,)] = ui.sql("SELECT title FROM records WHERE kind = 'project' LIMIT 1")
    [(locator,)] = ui.sql("SELECT locator FROM evidence LIMIT 1")
    return [
        "/", f"/?project={quote(project)}", "/?kind=done", f"/items/{rid}", f"/items/{rid}?tab=relations",
        f"/items/{rid}?tab=relations&hops=2", f"/?source={quote(locator, safe='')}", "/?q=cutover", "/review", "/import",
    ]


def test_the_strip_shows_on_first_open_dismisses_and_stays_gone_until_something_changes(page, ui):
    ui = start(page, ui)
    expect(page.locator(STRIP)).to_be_visible()
    assert ui.sql("SELECT count(*) FROM records")[0][0] > 0

    page.locator("[data-part=changed-dismiss]").click()
    expect(page.locator(STRIP)).to_have_count(0)
    page.reload()
    expect(page.locator("[data-part=headline]")).to_be_visible()
    expect(page.locator(STRIP)).to_have_count(0)

    ui.sql("UPDATE records SET updated_at = '2999-01-01T00:00:00+00:00' WHERE id = (SELECT min(id) FROM records)")
    page.reload()
    expect(page.locator(STRIP)).to_have_text(re.compile(r"1 changed since your last visit"))


def test_no_view_has_sounds_confetti_badges_points_or_streaks(page, ui):
    ui = start(page, ui)
    for path in urls(ui):
        page.goto(ui.url + path)
        expect(page.locator("#freshness")).not_to_be_empty()
        assert page.locator("#app audio").count() == 0, path
        classes = page.eval_on_selector_all("#app *", "els => els.map(e => e.className).filter(c => typeof c === 'string')")
        assert not [c for c in classes if BANNED.search(c)], path
        assert not BANNED.search(page.locator("#app").inner_text()), path


def test_every_view_reloads_to_the_same_state(page, ui):
    ui = start(page, ui)
    for path in urls(ui):
        page.goto(ui.url + path)
        expect(page.locator("#freshness")).not_to_be_empty()
        page.wait_for_load_state("networkidle")
        before = page.locator("#view").inner_text(), page.locator("#sheet").inner_text(), page.url
        page.reload()
        expect(page.locator("#freshness")).not_to_be_empty()
        page.wait_for_load_state("networkidle")
        after = page.locator("#view").inner_text(), page.locator("#sheet").inner_text(), page.url
        assert before == after, path
        assert before[0].strip(), path
