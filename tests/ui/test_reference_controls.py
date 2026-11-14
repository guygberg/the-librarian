"""Reference controls persist in the workspace and keep using real records."""

from playwright.sync_api import expect

from support.ui_stream import record


def test_create_favorite_edit_checklist_and_note(page, ui):
    app = ui("payments-cutover")
    page.goto(app.url)
    page.get_by_role("button", name="New item", exact=True).click()
    dialog = page.locator("dialog")
    dialog.get_by_label("Title", exact=True).fill("Reference parity task")
    dialog.get_by_label("Summary", exact=True).fill("A user-authored task")
    dialog.get_by_label("Due", exact=True).fill("Tomorrow")
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("h1")).to_have_text("Reference parity task")
    page.get_by_label("Review the available context", exact=True).check()
    page.get_by_label("Private note", exact=True).fill("Remember this after reload")
    page.get_by_role("button", name="Save note", exact=True).click()
    expect(page.get_by_text("Private note saved", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_label("Review the available context", exact=True)).to_be_checked()
    expect(page.get_by_text("Remember this after reload", exact=True)).to_be_visible()
    expect(page.get_by_text("High", exact=True)).to_be_visible()
    page.get_by_role("button", name="More item actions", exact=True).click()
    dialog.get_by_role("button", name="Edit details", exact=True).click()
    dialog.get_by_label("Title", exact=True).fill("Updated reference task")
    dialog.get_by_label("Priority", exact=True).select_option("40")
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("h1")).to_have_text("Updated reference task")
    expect(page.get_by_role("button", name="Low", exact=True)).to_be_visible()
    page.goto(app.url + "/people")
    page.get_by_role("button", name="Add person", exact=True).click()
    dialog.get_by_label("Name", exact=True).fill("Taylor Example")
    dialog.get_by_label("Role", exact=True).fill("Designer")
    dialog.get_by_label("Department", exact=True).fill("Product")
    dialog.get_by_label("Email", exact=True).fill("taylor@example.com")
    dialog.get_by_label("Slack ID", exact=True).fill("U_TAYLOR")
    dialog.get_by_label("Aliases (one per line)", exact=True).fill("Tay\nTaylor E")
    dialog.get_by_role("button", name="Save", exact=True).click()
    page.get_by_label("Find a person…").fill("Taylor Example")
    expect(page.get_by_text("Designer · Product", exact=True)).to_be_visible()
    page.get_by_role("button", name="Edit Taylor Example", exact=True).click()
    expect(dialog.get_by_label("Email", exact=True)).to_have_value("taylor@example.com")
    expect(dialog.get_by_label("Slack ID", exact=True)).to_have_value("U_TAYLOR")
    dialog.get_by_label("Department", exact=True).fill("Engineering")
    dialog.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_text("Designer · Engineering", exact=True)).to_be_visible()
    assert app.sql(
        "SELECT slack_id, email, role, department FROM people WHERE name = ?", "Taylor Example"
    ) == [("U_TAYLOR", "taylor@example.com", "Designer", "Engineering")]
    page.get_by_role("button", name="Favorite Taylor Example", exact=True).click()
    expect(page.get_by_role("button", name="Unfavorite Taylor Example", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("link", name="Favorites").click()
    expect(page.get_by_text("Taylor Example", exact=True)).to_be_visible()
    page.goto(app.url + "/projects")
    page.get_by_role("button", name="New tag", exact=True).click()
    dialog.get_by_label("Name", exact=True).fill("Reference tag")
    dialog.get_by_label("Description", exact=True).fill("Design work")
    dialog.get_by_role("button", name="Save", exact=True).click()
    page.get_by_label("Find a tag…").fill("Reference tag")
    page.get_by_role("button", name="Favorite Reference tag", exact=True).click()
    expect(page.get_by_role("button", name="Unfavorite Reference tag", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("link", name="Favorites").click()
    expect(page.locator("#view").get_by_text("Reference tag", exact=True)).to_be_visible()


def test_reference_layout_desktop_and_phone(page, ui, tmp_path):
    app = ui("payments-cutover")
    item = record(app, "Review the roadmap", basis="confirmed")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        for route in (
            "/",
            "/items",
            "/items?view=board",
            f"/items/{item}",
            "/people",
            "/projects",
            "/review",
        ):
            page.goto(app.url + route)
            expect(page.locator("#view h1")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(tmp_path / f"{width}-{route.strip('/').replace('/', '-') or 'today'}.png"),
                full_page=True,
            )
    assert not errors
