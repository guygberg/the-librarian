import re
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments
from support.ui_stream import open_stream, record

PHONE = {"width": 390, "height": 800}
LONG = "Reconcile-the-" + "very-long-unbroken-identifier-" * 6 + "end"
MOCK = re.compile(r"mock|lorem|placeholder item|demo", re.I)
OVERFLOW = "document.documentElement.scrollWidth - document.documentElement.clientWidth"


def start(ui):
    ui = ui("payments-cutover", payments.NOW)
    record(ui, LONG, kind="decision")
    return ui


def urls(ui):
    [(rid,)] = ui.sql("SELECT id FROM records WHERE title = ?", LONG)
    [(project,)] = ui.sql("SELECT title FROM records WHERE kind = 'project' LIMIT 1")
    [(locator,)] = ui.sql("SELECT locator FROM evidence LIMIT 1")
    return [
        "/",
        "/items",
        "/items?view=board",
        f"/items?project={quote(project)}",
        f"/items/{rid}",
        f"/items/{rid}?tab=activity",
        f"/items/{rid}?tab=sources",
        f"/items/{rid}?tab=relations",
        f"/items?source={quote(locator, safe='')}",
        "/people",
        "/projects",
        "/review",
        "/import",
    ]


def test_no_page_scrolls_sideways_on_a_phone_and_none_shows_a_mock_label(page, ui):
    ui = start(ui)
    page.set_viewport_size(PHONE)
    for path in urls(ui):
        page.goto(ui.url + path)
        page.wait_for_load_state("networkidle")
        assert page.evaluate(OVERFLOW) <= 0, path
        assert not MOCK.search(page.locator("main").inner_text()), path


def test_the_closed_drawer_is_out_of_the_tab_order_and_escape_returns_focus(page, ui):
    ui = start(ui)
    page.set_viewport_size(PHONE)
    page.goto(ui.url)
    expect(page.locator(".sidebar")).to_have_attribute("inert", "")
    page.locator("[data-part=menu]").click()
    expect(page.locator(".sidebar")).not_to_have_attribute("inert", "")
    page.keyboard.press("Escape")
    expect(page.locator("[data-part=menu]")).to_be_focused()
    expect(page.locator(".sidebar")).to_have_attribute("inert", "")


def test_the_desktop_sidebar_is_always_reachable(page, ui):
    ui = start(ui)
    page.goto(ui.url)
    expect(page.locator(".sidebar")).not_to_have_attribute("inert", "")


def test_the_source_sheet_and_dialogs_fit_a_phone(page, ui):
    ui = start(ui)
    page.set_viewport_size(PHONE)
    [(locator,)] = ui.sql("SELECT locator FROM evidence LIMIT 1")
    page.goto(ui.url + f"/items?source={quote(locator, safe='')}")
    sheet = page.locator(".sheet")
    expect(sheet).to_be_visible()
    box = sheet.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= PHONE["width"]
    assert page.evaluate(OVERFLOW) <= 0
    page.goto(ui.url + "/import")
    page.evaluate("document.getElementById('dialog').innerHTML = '<p>x</p>'")
    page.evaluate("document.getElementById('dialog').showModal()")
    box = page.locator("#dialog").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= PHONE["width"]


def test_reduced_motion_stops_the_drawer_and_the_settle(page, ui):
    ui = start(ui)
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size(PHONE)
    page.goto(ui.url)
    for selector in (".sidebar", "#toast"):
        duration = page.evaluate(
            "(s) => getComputedStyle(document.querySelector(s)).transitionDuration", selector
        )
        assert duration == "0s", selector


def test_trust_states_read_differently_in_the_list(page, ui):
    ui = start(ui)
    record(ui, "Stated thing", kind="decision", basis="stated")
    record(ui, "Confirmed thing", kind="decision", basis="confirmed")
    open_stream(page, ui)
    page.locator("[data-part=kind-filter]").select_option(label="Decisions")
    expect(page).to_have_url(ui.url + "/items?kind=decisions")
    labels = {
        title: page.locator("[data-part=item]", has_text=title).first.inner_text()
        for title in ("Stated thing", "Confirmed thing", LONG)
    }
    assert "Confirmed" in labels["Confirmed thing"]
    assert "Inferred" in labels[LONG]
    assert "Inferred" not in labels["Confirmed thing"] and "Confirmed" not in labels[LONG]


def test_phone_hit_targets_are_at_least_44_px(page, ui):
    ui = start(ui)
    page.set_viewport_size(PHONE)
    page.goto(ui.url)
    for part in ("menu",):
        box = page.locator(f"[data-part={part}]").bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44, part


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_body_text_contrast_meets_aa_in_both_themes(page, ui, theme):
    ui = start(ui)
    page.goto(ui.url)
    if theme == "light":
        page.locator("[data-part=theme-toggle]").click()
    ratio = page.evaluate(
        """() => {
          const s = getComputedStyle(document.body);
          const rgb = (c) => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
          const lin = (v) => {
            v /= 255;
            return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
          };
          const lum = (c) => c.reduce((a, v, i) => a + lin(v) * [.2126, .7152, .0722][i], 0);
          const mut = s.getPropertyValue('--mut').trim();
          const probe = document.createElement('i');
          probe.style.color = mut;
          document.body.append(probe);
          const fg = lum(rgb(getComputedStyle(probe).color)), bg = lum(rgb(s.backgroundColor));
          probe.remove();
          return (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05);
        }"""
    )
    assert ratio >= 4.5
