import shutil
import sqlite3

import pytest

from librarian import config, db

NOW = "2026-11-14T00:00:00Z"


@pytest.fixture
def conn(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    return db.connect_rw("work")


def add_run(conn, workspace="work", purpose="suggestions"):
    return conn.execute(
        "INSERT INTO extraction_runs (workspace, unit_key, model, claude_code_version, prompt_hash,"
        " schema_hash, envelope, accepted, created_at, purpose)"
        " VALUES (?, 'u', 'm', 'v', 'p', 's', '{}', 1, ?, ?)",
        (workspace, NOW, purpose),
    ).lastrowid


def add_revision(conn, workspace="work"):
    item = conn.execute(
        "INSERT INTO source_items (workspace, source, stable_id, created_at)"
        " VALUES (?, 'slack', ?, ?)",
        (workspace, f"s{workspace}", NOW),
    ).lastrowid
    return conn.execute(
        "INSERT INTO source_item_revisions (workspace, source_item_id, revision, content_hash,"
        " content,"
        " fetched_at) VALUES (?, ?, 1, 'h', 'text', ?)",
        (workspace, item, NOW),
    ).lastrowid


def suggestion(conn, run_id, **over):
    row = {
        "workspace": "work", "kind": "new_tag", "link_type": None, "payload": "{}",
        "run_id": run_id, "confidence": 90, "band": "high", "basis": "stated",
        "reasoning": "r", "status": "pending", "dedupe_key": "k", "created_at": NOW,
        "resolved_at": None,
    } | over  # fmt: skip
    cols = ", ".join(row)
    return conn.execute(
        f"INSERT INTO suggestions ({cols}) VALUES ({', '.join('?' * len(row))})", list(row.values())
    ).lastrowid


def test_tag_replaces_project_and_no_generic_items_table(conn):
    conn.execute(
        "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
        " VALUES ('work', 'tag', 'Atlas', 1, 1)"
    )
    conn.execute(
        "INSERT INTO records (workspace, kind, title, parent_id, created_at, updated_at)"
        " VALUES ('work', 'tag', 'Sub', 1, 1, 1)"
    )
    for kind in ("project", "topic"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
                f" VALUES ('work', '{kind}', 'x', 1, 1)"
            )
    with pytest.raises(sqlite3.IntegrityError):  # only a Tag nests
        conn.execute(
            "INSERT INTO records (workspace, kind, title, parent_id, created_at, updated_at)"
            " VALUES ('work', 'action_item', 'x', 1, 1, 1)"
        )
    schema = " ".join(r[0] or "" for r in conn.execute("SELECT sql FROM sqlite_master"))
    assert "project" not in schema.lower()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {"items", "tags"} & tables


def test_upgrade_from_previous_schema_keeps_records_and_their_children(home, tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    old = tmp_path / "v16"
    old.mkdir()
    for version, path in db.migration_files():
        if version <= 16:
            shutil.copy(path, old / path.name)
    before = db.connect_rw("work", old)
    revision = add_revision(before)
    before.execute(
        "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
        " VALUES ('work', 'project', 'Atlas', ?, ?)",
        (NOW, NOW),
    )
    before.execute(
        "INSERT INTO records (workspace, kind, title, parent_id, created_at, updated_at)"
        " VALUES ('work', 'project', 'Sub', 1, ?, ?)",
        (NOW, NOW),
    )
    before.execute(
        "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role,"
        " retrieved_at)"
        " VALUES ('work', 1, ?, 'l', 'q', 'supports', ?)",
        (revision, NOW),
    )
    before.execute("INSERT INTO project_aliases VALUES ('work', 1, 'Atlas v2')")
    before.execute(
        "INSERT INTO review_entries"
        " (workspace, kind, record_id, link_type, created_at, other_record_id)"
        " VALUES ('work', 'merge_project', 2, 'belongs_to', 't', 1)"
    )
    before.execute(
        "INSERT INTO record_events (workspace, record_id, event, detail, at)"
        " VALUES ('work', 2, 'project_move', '{\"project_id\": 1}', 't')"
    )
    before.close()

    after = db.connect_rw("work")
    assert db.current_version(db.db_path("work")) == db.latest_version()
    assert after.execute(
        "SELECT id, kind, title, parent_id FROM records ORDER BY id"
    ).fetchall() == [
        (1, "tag", "Atlas", None),
        (2, "tag", "Sub", 1),
    ]
    assert after.execute("SELECT alias FROM tag_aliases").fetchall() == [("Atlas v2",)]
    assert after.execute("SELECT kind, other_record_id FROM review_entries").fetchall() == [
        ("merge_tag", 1)
    ]
    assert after.execute("SELECT event, detail FROM record_events").fetchall() == [
        ("tag_move", '{"tag_id":1}')
    ]
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        after.execute("UPDATE record_events SET event = 'x'")
    assert after.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1
    assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        after.execute("DELETE FROM records WHERE id = 1")


def test_defaults_for_persistence_and_visibility_floors(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    loaded = config.load()
    assert (loaded["suggest_min_confidence"], loaded["suggest_auto_hide_below"]) == (40, 40)


def test_extraction_runs_carry_a_purpose_defaulting_to_extraction(conn):
    plain = conn.execute(
        "INSERT INTO extraction_runs (workspace, unit_key, model, claude_code_version, prompt_hash,"
        " schema_hash, envelope, accepted, created_at)"
        " VALUES ('work', 'u', 'm', 'v', 'p', 's', '{}', 1, ?)",
        (NOW,),
    ).lastrowid
    assert conn.execute(
        "SELECT purpose FROM extraction_runs WHERE id = ?", (plain,)
    ).fetchone() == ("extraction",)
    with pytest.raises(sqlite3.IntegrityError):
        add_run(conn, purpose="other")


@pytest.mark.parametrize(
    "bad",
    [
        {"confidence": 101},
        {"confidence": -1},
        {"band": "huge"},
        {"basis": "confirmed"},
        {"basis": "inferred", "confidence": 90},
        {"status": "done"},
        {"kind": "new_record"},
        {"kind": "link"},  # a Link needs a link_type
        {"link_type": "mentions"},  # and only a Link has one
        {"kind": "link", "link_type": "evidence"},  # not a supported suggestion link
        {"from_type": "record"},  # an end is a (type, id) pair
        {"from_type": "tag", "from_id": 1},
        {"status": "rejected"},  # settled needs resolved_at
        {"resolved_at": NOW},  # pending has none
    ],
)
def test_suggestion_constraints(conn, bad):
    run = add_run(conn)
    with pytest.raises(sqlite3.IntegrityError):
        suggestion(conn, run, **bad)


def test_suggestion_dedupe_is_per_workspace_and_unique(conn):
    run = add_run(conn)
    suggestion(conn, run)
    with pytest.raises(sqlite3.IntegrityError):
        suggestion(conn, run)
    suggestion(conn, run, workspace="other")
    assert (
        conn.execute("SELECT count(*) FROM suggestions WHERE workspace = 'work'").fetchone()[0] == 1
    )


def test_a_pending_suggestion_with_evidence_and_one_created_event(conn):
    run = add_run(conn)
    revision = add_revision(conn)
    sid = suggestion(conn, run, kind="link", link_type="owner", from_type="record", from_id=1,
                     to_type="person", to_id=2)  # fmt: skip
    conn.execute(
        "INSERT INTO suggestion_evidence (workspace, suggestion_id, revision_id, locator, quote)"
        " VALUES ('work', ?, ?, 'l', 'q')",
        (sid, revision),
    )
    conn.execute(
        "INSERT INTO suggestion_events (workspace, suggestion_id, event, at)"
        " VALUES ('work', ?, 'created', ?)",
        (sid, NOW),
    )
    assert conn.execute("SELECT count(*) FROM records").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM links").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM persons").fetchone()[0] == 0


def test_suggestion_events_are_append_only_and_typed(conn):
    run = add_run(conn)
    sid = suggestion(conn, run)
    conn.execute(
        "INSERT INTO suggestion_events (workspace, suggestion_id, event, at)"
        " VALUES ('work', ?, 'created', ?)",
        (sid, NOW),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO suggestion_events (workspace, suggestion_id, event, at)"
            " VALUES ('work', ?, 'bogus', ?)",
            (sid, NOW),
        )
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE suggestion_events SET event = 'accepted'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM suggestion_events")


def test_suggestion_units_are_unique_per_unit_and_independent_of_extracted_units(conn):
    run = add_run(conn)
    unit = (
        "INSERT INTO suggestion_units (workspace, unit_key, text_hash, prompt_hash, schema_hash,"
        " run_id, status, suggestion_count, analysed_at)"
        " VALUES (?, 'u1', 't', 'p', 's', ?, ?, 0, ?)"
    )
    conn.execute(unit, ("work", run, "succeeded", NOW))  # a valid empty result
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(unit, ("work", run, "failed", NOW))
    conn.execute(unit, ("other", None, "failed", NOW))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(unit, ("third", run, "running", NOW))
    assert conn.execute("SELECT count(*) FROM extracted_units").fetchone()[0] == 0
