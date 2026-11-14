# ruff: noqa: F811  (fixtures imported from the sibling test module are used as arguments)
import json
import sqlite3

import pytest
from test_suggest_stage import (  # noqa: F401  (fixtures)
    DANA,
    WS,
    Stub,
    add_item,
    analyse,
    conn,
    count,
    key,
    tag,
    two_units,
)

from librarian import forget


def revise(conn, channel, ts, text):
    item_id = conn.execute(
        "SELECT id FROM source_items WHERE stable_id = ?", (f"{channel}/{ts}",)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO source_item_revisions (workspace, source_item_id, revision, content_hash,"
        " content, fetched_at) VALUES (?, ?, 2, 'h2', ?, 'x')",
        (WS, item_id, json.dumps({"ts": ts, "user": "Dana", "text": text})),
    )


def events(conn):
    return [e for (e,) in conn.execute("SELECT event FROM suggestion_events ORDER BY id")]


def statuses(conn):
    return [s for (s,) in conn.execute("SELECT status FROM suggestions ORDER BY id")]


def two_sources(*locators):
    return dict(tag(), evidence=[{"locator": loc, "quote": DANA} for loc in locators])


def test_rerun_with_new_prompt_stores_nothing_twice(conn, two_units):
    answer = {key("C1"): {"suggestions": [tag(), tag("t2", "ROLLOUT")]}}
    analyse(conn, Stub(answer))
    counts = analyse(conn, Stub(answer, prompt="p2"))
    assert (counts.sent, counts.created) == (2, 0)
    assert count(conn, "suggestions") == 1 and events(conn) == ["created"]


def test_confidence_and_wording_do_not_change_identity(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    lower = dict(tag(), confidence=70, basis="inferred", reasoning="Other words.")
    counts = analyse(conn, Stub({key("C1"): {"suggestions": [lower]}}, prompt="p2"))
    assert counts.created == 0 and count(conn, "suggestions") == 1


def test_rejected_unchanged_suggestion_never_reappears(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    conn.execute("UPDATE suggestions SET status = 'rejected', resolved_at = 'x'")
    counts = analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}, prompt="p2"))
    assert counts.created == 0 and statuses(conn) == ["rejected"]


def test_changed_revision_supersedes_explicitly(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    revise(conn, "C1", "1760000000.0", DANA + " Dana confirmed.")
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    rows = conn.execute("SELECT status, dedupe_key FROM suggestions ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["superseded", "pending"]
    assert rows[0][1].endswith("#superseded:1") and "#" not in rows[1][1]
    assert events(conn) == ["created", "superseded", "created"]
    revisions = conn.execute("SELECT revision_id FROM suggestion_evidence ORDER BY id").fetchall()
    assert revisions[0] != revisions[1]


def test_accepted_suggestion_survives_a_changed_source(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    conn.execute("UPDATE suggestions SET status = 'accepted', resolved_at = 'x'")
    revise(conn, "C1", "1760000000.0", DANA + " Dana confirmed.")
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    assert statuses(conn) == ["accepted"]


def test_multi_evidence_suggestion_keeps_every_row(conn, two_units):
    add_item(conn, "C1", "1760000050.0")
    both = two_sources("slack:C1/1760000000.0#1", "slack:C1/1760000050.0#1")
    analyse(conn, Stub({key("C1"): {"suggestions": [both]}}))
    assert count(conn, "suggestion_evidence") == 1 + 1 and events(conn) == ["created"]


def test_forgetting_sole_source_supersedes_and_resets_the_ledger(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    forget.forget(conn, WS, "C1")
    assert statuses(conn) == ["superseded"] and events(conn) == ["created", "superseded"]
    assert count(conn, "suggestion_evidence") == 0
    assert conn.execute("SELECT unit_key FROM suggestion_units").fetchall() == [(key("C2"),)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_forgetting_one_of_two_sources_keeps_the_suggestion(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    # A unit only cites its own items, so a second source's Evidence is added directly.
    other = conn.execute("SELECT id FROM source_item_revisions ORDER BY id DESC").fetchone()[0]
    conn.execute(
        "INSERT INTO suggestion_evidence (workspace, suggestion_id, revision_id, locator, quote)"
        " VALUES (?, 1, ?, 'slack:C2/1760000100.0#1', ?)",
        (WS, other, DANA),
    )
    forget.forget(conn, WS, "C1")
    assert statuses(conn) == ["pending"] and count(conn, "suggestion_evidence") == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_forgetting_supersedes_a_suggestion_aimed_at_a_forgotten_record(conn, two_units):
    c1 = conn.execute(
        "SELECT r.id FROM source_item_revisions r JOIN source_items i ON i.id = r.source_item_id"
        " WHERE i.stable_id LIKE 'C1/%'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
        " VALUES ('work', 'tag', 'Rollout', 'x', 'x')"
    )
    conn.execute(
        "INSERT INTO evidence (workspace, record_id, revision_id, locator, quote, role,"
        " retrieved_at) VALUES ('work', 1, ?, 'slack:C1/1760000000.0#1', ?, 'supports', 'x')",
        (c1, DANA),
    )
    analyse(conn, Stub({key("C2"): {"suggestions": [tag(locator="slack:C2/1760000100.0#1")]}}))
    conn.execute("UPDATE suggestions SET to_type = 'record', to_id = 1, from_type = 'person',"
                 " from_id = 1")  # fmt: skip
    forget.forget(conn, WS, "C1")
    assert statuses(conn) == ["superseded"]


def test_a_forgotten_proposal_can_be_made_again(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    forget.forget(conn, WS, "C1")
    add_item(conn, "C1", "1760000000.0")
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    assert statuses(conn) == ["superseded", "pending"]


def test_suggestion_events_stay_append_only(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE suggestion_events SET event = 'edited'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM suggestion_events")


def test_cross_workspace_references_are_refused(conn, two_units):
    analyse(conn, Stub({key("C1"): {"suggestions": [tag()]}}))
    add_item(conn, "C9", "1760000900.0", workspace="other")
    revision = conn.execute(
        "SELECT id FROM source_item_revisions WHERE workspace = 'other'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(
            "INSERT INTO suggestion_evidence (workspace, suggestion_id, revision_id, locator,"
            " quote) VALUES ('work', 1, ?, 'l', 'q')",
            (revision,),
        )
