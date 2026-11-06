"""Helpers the stream UI tests share: seed People and Records straight into the Workspace,
then open the page."""

from datetime import datetime

from playwright.sync_api import expect

NOW = "2023-11-14T09:30:00+00:00"
STAMP = "2023-11-01T00:00:00+00:00"


def person(ui, name, me=False):
    ui.sql(
        "INSERT INTO persons (workspace, name, is_me, created_at) VALUES ('work', ?, ?, ?)",
        name,
        int(me),
        STAMP,
    )
    return ui.sql("SELECT id FROM persons WHERE name = ?", name)[0][0]


def record(ui, title, kind="action_item", lifecycle="open", basis="inferred", owner=None):
    ui.sql(
        "INSERT INTO records"
        " (workspace, kind, title, lifecycle, basis, owner_person_id, created_at, updated_at)"
        " VALUES ('work', ?, ?, ?, ?, ?, ?, ?)",
        kind,
        title,
        lifecycle,
        basis,
        owner,
        STAMP,
        STAMP,
    )
    return ui.sql("SELECT id FROM records WHERE title = ?", title)[0][0]


def row(page, title):
    return page.locator("[data-part=item]", has=page.get_by_text(title, exact=True))


def open_stream(page, ui):
    page.clock.set_fixed_time(datetime.fromisoformat(NOW))
    page.goto(ui.url)
    expect(page.locator("[data-part=headline]")).to_be_visible()
