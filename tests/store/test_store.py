import json
import sqlite3

import pytest
from support.cli import run_librarian

from librarian import db, store


@pytest.fixture
def conn(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    c = db.connect_rw("work")
    yield c
    c.close()


def show(home, locator):
    out = run_librarian(["show", locator], home)
    return out.returncode, json.loads(out.stdout)


def test_changed_upsert_keeps_both_revisions_and_origin(conn, home):
    assert store.upsert(conn, "work", "slack", "C1/1.0", "v1", origin_name="eng", origin_kind="channel")
    assert store.upsert(conn, "work", "slack", "C1/1.0", "v2", origin_name="eng", origin_kind="channel")
    code, item = show(home, "slack:C1/1.0")
    assert code == 0
    assert [r["content"] for r in item["revisions"]] == ["v1", "v2"]
    assert (item["origin_name"], item["origin_kind"]) == ("eng", "channel")
    assert item["flags"] == {"gone_from_source": False}


def test_identical_upsert_changes_nothing(conn):
    assert store.upsert(conn, "work", "slack", "C1/1.0", "same")
    before = conn.execute("SELECT * FROM source_item_revisions").fetchall()
    assert not store.upsert(conn, "work", "slack", "C1/1.0", "same")
    assert conn.execute("SELECT * FROM source_item_revisions").fetchall() == before
    assert conn.execute("SELECT count(*) FROM source_items").fetchone()[0] == 1


def test_gone_flag_keeps_evidence(conn, home):
    store.upsert(conn, "work", "slack", "C1/1.0", "v1")
    store.mark_gone(conn, "work", "slack", "C1/1.0")
    _, item = show(home, "slack:C1/1.0#4")
    assert item["flags"]["gone_from_source"] is True
    assert len(item["revisions"]) == 1
    assert item["part"] == "4"


def test_same_stable_id_in_two_workspaces_is_two_items(conn):
    store.upsert(conn, "work", "drive", "f1", "a")
    store.upsert(conn, "home", "drive", "f1", "a")
    assert conn.execute("SELECT count(*) FROM source_items").fetchone()[0] == 2
    assert store.get_item(conn, "home", "drive", "f1")["workspace"] == "home"


def test_show_opens_read_only(conn, home):
    store.upsert(conn, "work", "slack", "C1/1.0", "v1")
    ro = db.connect_ro("work")
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM source_items")
    ro.close()


def test_show_errors_are_envelopes(conn, home):
    code, err = show(home, "slack:nope")
    assert code == 1 and err["error"]["code"] == "not_found"
    code, err = show(home, "garbage")
    assert code == 1 and err["error"]["code"] == "bad_locator"


def test_show_on_old_schema_says_how_to_update(home):
    code, err = show(home, "slack:C1/1.0")
    assert code == 1 and err["error"]["code"] == "schema_outdated"
    assert "librarian serve" in err["error"]["message"] and "librarian import" in err["error"]["message"]
