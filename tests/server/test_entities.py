"""Each entity keeps its own user-set columns: validated, persistent and workspace scoped."""

from librarian import config, db, events
from librarian.query import core, open_items, search
from librarian.server.app import Request
from librarian.server.routes import entities, records


def setup(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    db.connect_rw("work").close()


def request(body=None, **params):
    return Request("work", "POST", "", "", params, body)


def create(kind, **body):
    status, result = entities.create(request(body, kind=kind))
    assert status == 200, result
    return result["id"]


def test_item_priority_and_notes_live_on_the_item_and_stay_workspace_scoped(home, monkeypatch):
    setup(home, monkeypatch)
    id_ = create("item", title="Read the roadmap", body="Review priorities")
    assert entities.set_priority(request({"priority": 94}, id=str(id_)))[0] == 200
    note = "Private <script>note</script>"
    status, result = entities.add_note(request({"text": note}, id=str(id_)))
    assert status == 200 and result["notes"][0]["text"] == "Private <script>note</script>"
    with db.connect_ro("work") as conn:
        view = core.current_view(conn, "work", id_, config.load())
    assert view["priority"] == 94
    assert [n["text"] for n in view["notes"]] == ["Private <script>note</script>"]
    db.connect_rw("personal").close()
    other = request({"priority": 50}, id=str(id_))
    other.workspace = "personal"
    assert entities.set_priority(other)[0] == 404


def test_favorites_color_and_settings_are_columns_on_their_own_rows(home, monkeypatch):
    setup(home, monkeypatch)
    person = create("person", title="Taylor")
    tag = create("project", title="Design")
    assert entities.favorite_person(request({"favorite": True}, id=str(person)))[0] == 200
    style = {"favorite": True, "color": "#aabbcc"}
    assert entities.style_tag(request(style, id=str(tag)))[0] == 200
    assert entities.save_settings(request({"sound": True}))[0] == 200
    assert entities.get_settings(request())[1] == {"sound": True}
    with db.connect_ro("work") as conn:
        answer = open_items.open_items(conn, "work", everything=True)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "presentation" not in names
    assert next(p for p in answer["people"] if p["id"] == person)["favorite"] is True
    shown = next(p for p in answer["projects"] if p["id"] == tag)
    assert (shown["favorite"], shown["color"]) == (True, "#aabbcc")


def test_created_item_and_edits_are_queryable_with_history(home, monkeypatch):
    setup(home, monkeypatch)
    tag = create("project", title="Design", body="Interface work")
    id_ = create("item", title="Read", body="Original", project_id=tag)
    status, _ = entities.edit(
        request({"title": "Read carefully", "body": "Updated", "due": "Tomorrow"}, id=str(id_))
    )
    assert status == 200
    with db.connect_rw("work") as conn:
        events.append(conn, "work", id_, "status_change", {"lifecycle": "done"})
        view = core.current_view(conn, "work", id_, config.load())
        assert search._record_ids(conn, "work", lambda text: "carefully" in text, 10) == [id_]
        assert view["title"] == "Read carefully"
        assert view["body"] == "Updated"
        assert view["stated_deadline"] == "Tomorrow"
        assert view["projects"][0]["id"] == tag
        assert view["lifecycle"] == "done"
        assert "no_longer_found" not in view
        answer = open_items.open_items(conn, "work", everything=True)
        assert any(r["id"] == id_ for r in answer["records"])


def test_invalid_settings_and_creation_leave_no_partial_data(home, monkeypatch):
    setup(home, monkeypatch)
    id_ = create("person", title="Taylor", role="Design")
    assert entities.favorite_person(request({"favorite": "yes"}, id=str(id_)))[0] == 400
    assert entities.favorite_person(request({"favorite": True}, id="999"))[0] == 404
    assert entities.set_priority(request({"priority": 200}, id="999"))[0] == 400
    assert entities.add_note(request({"text": "  "}, id="999"))[0] == 400
    assert entities.style_tag(request({"color": "red"}, id="999"))[0] == 400
    assert entities.style_tag(request({"unknown": True}, id="999"))[0] == 400
    assert entities.save_settings(request({"sound": "on"}))[0] == 400
    assert entities.create(request({"title": "Bad", "project_id": 999}, kind="item"))[0] == 404
    assert entities.edit(request(None, id="1"))[0] == 400
    with db.connect_ro("work") as conn:
        assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 0
        assert conn.execute("SELECT favorite FROM people WHERE id = ?", (id_,)).fetchone() == (0,)


def test_removing_tag_clears_current_view_and_project_membership(home, monkeypatch):
    setup(home, monkeypatch)
    tag = create("project", title="Design")
    id_ = create("item", title="Task", project_id=tag)
    status, view = records.act("unproject")(request({}, id=str(id_)))
    assert status == 200 and view["projects"] == []
    with db.connect_ro("work") as conn:
        assert not conn.execute(
            "SELECT 1 FROM links WHERE from_id = ? AND type = 'belongs_to'", (id_,)
        ).fetchone()
