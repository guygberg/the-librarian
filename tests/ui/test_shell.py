import re
from pathlib import Path

from playwright.sync_api import expect

from fixtures.scenarios import payments_cutover as payments

REFERENCE = Path(__file__).parents[2] / "docs" / "reference" / "mission-control-lime.html"
NAV = "#nav a"


def test_reference_is_preserved_in_the_repository():
    html = REFERENCE.read_text()
    assert "palette-home" in html and "#d5f52f" in html


def test_nav_lists_the_five_pages_and_each_route_loads(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(ui.url)
    expect(page.locator(NAV)).to_have_text(
        ["Today", "Items", "People", "Tags", re.compile(r"Suggestions\d*")]  # carries its count
    )
    pages = [("People", "/people"), ("Tags", "/tags"), ("Suggestions", "/review")]
    pages.append(("Items", "/items"))
    for label, path in pages:
        page.locator(NAV, has_text=label).click()
        expect(page).to_have_url(ui.url + path)
        expect(page.locator(NAV, has_text=label)).to_have_attribute("aria-current", "page")
    page.locator(NAV, has_text="Today").click()
    expect(page.locator(NAV, has_text="Today")).to_have_attribute("aria-current", "page")
    page.goto(ui.url + "/people")
    expect(page.locator("[data-part=people]")).to_be_visible()


def test_theme_toggle_switches_and_remembers(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.goto(ui.url)
    page.locator("[data-part=theme-toggle]").click()
    expect(page.locator("body")).to_have_class("light")
    page.reload()
    expect(page.locator("body")).to_have_class("light")


def test_phone_drawer_opens_from_the_menu_and_closes_on_navigation(page, ui):
    ui = ui("payments-cutover", payments.NOW)
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(ui.url)
    sidebar = page.locator("#sidebar")
    assert sidebar.bounding_box()["x"] < 0
    page.locator("[data-part=menu]").click()
    expect(page.locator("[data-part=menu]")).to_have_attribute("aria-expanded", "true")
    page.wait_for_function("document.getElementById('sidebar').getBoundingClientRect().x >= 0")
    page.locator(NAV, has_text="People").click()
    expect(page).to_have_url(ui.url + "/people")
    expect(page.locator("[data-part=menu]")).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
