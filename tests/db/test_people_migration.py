"""The merged people table preserves identity, ownership, and existing UI profiles."""

import json
import shutil

from librarian import db
from librarian.link import people
from librarian.server.app import Request
from librarian.server.routes import entities


def test_v17_people_aliases_and_roles_migrate_without_losing_references(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(tmp_path / "home"))
    old = tmp_path / "migrations"
    old.mkdir()
    for version, path in db.migration_files():
        if version <= 17:
            shutil.copy(path, old / path.name)
    conn = db.connect_rw("work", old)
    conn.execute("INSERT INTO persons VALUES (1, 'work', 'Alex Morgan', '2026-11-14', 1)")
    for alias in ("Alex", "אלכס", "slack:U001", "slack:U002"):
        conn.execute(
            "INSERT INTO aliases (workspace, person_id, alias) VALUES ('work', 1, ?)", (alias,)
        )
    conn.execute(
        "INSERT INTO records (workspace, kind, title, owner_person_id, created_at,"
        " updated_at) VALUES ('work', 'action_item', 'Review roadmap', 1, 't', 't')"
    )
    conn.execute("INSERT INTO segment_speakers VALUES ('work', 'meeting.mp4', 0, 5, 1, 't')")
    conn.execute(
        "INSERT INTO presentation VALUES ('work', 'person', 1, ?)",
        (json.dumps({"role": "Designer", "favorite": True}),),
    )
    conn.close()
    conn = db.connect_rw("work")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "people" in names and not {"persons", "aliases"} & names
    row = conn.execute(
        "SELECT id, name, aliases, slack_id, email, role, department FROM people"
    ).fetchone()
    assert row[:2] == (1, "Alex Morgan")
    assert json.loads(row[2]) == ["Alex", "אלכס", "slack:U002"]
    assert row[3:] == ("U001", None, "Designer", None)
    assert set(people.aliases_for(conn, "work", 1)) == {"Alex", "אלכס", "slack:U001", "slack:U002"}
    assert conn.execute("SELECT owner_person_id FROM records").fetchone() == (1,)
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert conn.execute("SELECT favorite FROM people").fetchone() == (1,)
    assert list((db.db_path("work").parent / "backups").glob("*.db"))
    conn.close()


def test_slack_profiles_fill_missing_fields_without_replacing_user_corrections(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LIBRARIAN_HOME", str(tmp_path / "home"))
    conn = db.connect_rw("work")
    users = [
        {
            "id": "U001",
            "name": "alex",
            "real_name": "Alex Morgan",
            "profile": {
                "email": "alex@example.com",
                "title": "Designer",
                "department": "Product",
            },
        }
    ]
    people.save_slack_users(conn, "work", users, "U001")
    people.save_slack_users(conn, "work", users, "U001")
    assert conn.execute("SELECT count(*) FROM people").fetchone()[0] == 1
    assert conn.execute("SELECT slack_id, email, role, department FROM people").fetchone() == (
        "U001",
        "alex@example.com",
        "Designer",
        "Product",
    )
    conn.execute("UPDATE people SET role = 'Design Lead'")
    people.save_slack_users(conn, "work", users, "U001")
    assert conn.execute("SELECT role FROM people").fetchone()[0] == "Design Lead"
    assert people.resolve(conn, "work", {"slack_user": "U001"}, False) == (1, None)
    conn.close()


def test_profile_creation_and_edit_validate_identity_before_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(tmp_path / "home"))
    db.connect_rw("work").close()

    def req(body, **params):
        return Request("work", "POST", "", "", params, body)

    data = {
        "title": "Alex Morgan",
        "aliases": ["Alex"],
        "slack_id": "U001",
        "email": "alex@example.com",
        "role": "Designer",
        "department": "Product",
    }
    status, result = entities.create(req(data, kind="person"))
    assert status == 200
    assert entities.create(req({**data, "title": "Different Person"}, kind="person"))[0] == 409
    assert (
        entities.create(req({"title": "Bad", "aliases": "not a list"}, kind="person"))[0] == 400
    )
    id_ = result["id"]
    assert (
        entities.profile(req({**data, "name": "Alex Morgan", "role": "Lead"}, id=str(id_)))[0]
        == 200
    )
    with db.connect_ro("work") as conn:
        assert conn.execute("SELECT count(*) FROM people").fetchone()[0] == 1
        assert conn.execute("SELECT role FROM people").fetchone()[0] == "Lead"
        assert json.loads(conn.execute("SELECT aliases FROM people").fetchone()[0]) == [
            "Alex",
            "Alex Morgan",
        ]
