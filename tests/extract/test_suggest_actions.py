# ruff: noqa: F811  (fixtures imported from the sibling test module are used as arguments)
import json

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

from librarian import config, events
from librarian.link import suggestion_actions as actions
from librarian.link.errors import Invalid
from librarian.query import core
from librarian.server import app
from librarian.server.routes import suggestions as route


def item(ref="i1", title="Send rollout plan", **extra):
    return {
        "ref": ref,
        "kind": "new_item",
        "title": title,
        "lifecycle": "open",
        "confidence": 90,
        "basis": "stated",
        "reasoning": "Said so.",
        "evidence": [{"locator": "slack:C1/1760000000.0#1", "quote": DANA}],
        **extra,
    }


def link(frm, to, link_type="belongs_to"):
    return {
        "ref": "l1",
        "kind": "link",
        "link_type": link_type,
        "from": frm,
        "to": to,
        "confidence": 90,
        "basis": "stated",
        "reasoning": "Same thread.",
        "evidence": [{"locator": "slack:C1/1760000000.0#1", "quote": DANA}],
    }


def suggest(conn, *suggestions):
    analyse(conn, Stub({key("C1"): {"suggestions": list(suggestions)}}))
    return {
        kind_title: sid
        for sid, kind_title in conn.execute(
            "SELECT id, COALESCE(json_extract(payload, '$.title'), kind) FROM suggestions"
        )
    }


def record_count(conn):
    return count(conn, "records")


def tables(conn):
    return {
        t: conn.execute(f"SELECT * FROM {t}").fetchall()
        for t in ("records", "persons", "links", "evidence", "unit_records", "record_events",
                  "review_entries", "suggestions", "suggestion_events")
    }  # fmt: skip


def test_accepting_a_new_tag_creates_the_tag_with_exact_evidence_and_a_source_unit(conn, two_units):
    ids = suggest(conn, tag())
    out = actions.accept(conn, WS, ids["Rollout"])
    assert out["status"] == "accepted"
    kind, basis = conn.execute(
        "SELECT kind, basis FROM records WHERE id = ?", (out["record_id"],)
    ).fetchone()
    assert (kind, basis) == ("tag", "stated")
    assert conn.execute("SELECT locator, quote, role FROM evidence").fetchall() == [
        ("slack:C1/1760000000.0#1", DANA, "supports")
    ]
    view = core.current_view(conn, WS, out["record_id"], config.load())
    assert "no_longer_found" not in view and view["basis"] == "confirmed"
    assert conn.execute("SELECT status FROM suggestions").fetchone() == ("accepted",)
    assert [e for (e,) in conn.execute("SELECT event FROM suggestion_events ORDER BY id")] == [
        "created",
        "accepted",
    ]
    assert conn.execute("SELECT event, record_id FROM record_events").fetchall() == [
        ("accept_suggestion", out["record_id"])
    ]


def test_accepting_a_new_item_keeps_fields_and_a_known_owner(conn, two_units):
    ids = suggest(conn, item(owner={"id": 1}, stated_deadline="2025-10-10", lifecycle="pending"))
    rid = actions.accept(conn, WS, ids["Send rollout plan"])["record_id"]
    assert conn.execute(
        "SELECT kind, lifecycle, owner_person_id, stated_deadline FROM records WHERE id = ?", (rid,)
    ).fetchone() == ("action_item", "pending", 1, "2025-10-10")


def test_an_unknown_owner_name_goes_to_person_review_and_creates_no_person(conn, two_units):
    ids = suggest(conn, item(owner={"raw_name": "Priya"}))
    rid = actions.accept(conn, WS, ids["Send rollout plan"])["record_id"]
    assert conn.execute("SELECT COUNT(*) FROM persons WHERE name = 'Priya'").fetchone() == (0,)
    assert conn.execute(
        "SELECT kind, record_id, raw_name FROM review_entries WHERE resolved_at IS NULL"
    ).fetchall() == [("unconfirmed_person", rid, "Priya")]
    assert conn.execute("SELECT owner_person_id FROM records").fetchone() == (None,)


def test_accepting_a_link_to_new_things_needs_them_accepted_first(conn, two_units):
    ids = suggest(conn, tag(), item(), link({"ref": "i1"}, {"ref": "t1"}))
    before = tables(conn)
    with pytest.raises(Invalid) as refused:
        actions.accept(conn, WS, ids["link"])
    assert refused.value.status == 409 and tables(conn) == before
    item_id = actions.accept(conn, WS, ids["Send rollout plan"])["record_id"]
    tag_id = actions.accept(conn, WS, ids["Rollout"])["record_id"]
    assert actions.accept(conn, WS, ids["link"])["record_id"] == item_id
    assert conn.execute("SELECT type, from_id, to_id FROM links").fetchall() == [
        ("belongs_to", item_id, tag_id)
    ]


def test_an_owner_link_sets_the_owner_of_an_item(conn, two_units):
    ids = suggest(conn, item(), link({"ref": "i1"}, {"type": "person", "id": 1}, "owner"))
    item_id = actions.accept(conn, WS, ids["Send rollout plan"])["record_id"]
    actions.accept(conn, WS, ids["link"])
    assert conn.execute(
        "SELECT owner_person_id FROM records WHERE id = ?", (item_id,)
    ).fetchone() == (1,)
    assert count(conn, "links") == 0


def raw_link(conn, from_end, to_end, workspace=WS):
    run_id = conn.execute("SELECT run_id FROM suggestions").fetchone()[0]
    return conn.execute(
        "INSERT INTO suggestions (workspace, kind, link_type, payload, from_type, from_id, to_type,"
        " to_id, run_id, confidence, band, basis, reasoning, dedupe_key, created_at)"
        " VALUES (?, 'link', 'related_to', '{}', ?, ?, ?, ?, ?, 90, 'high', 'stated', 'r', ?, 'x')",
        (workspace, *from_end, *to_end, run_id, f"raw{from_end}{to_end}"),
    ).lastrowid


@pytest.mark.parametrize("gone", ["deleted", "other_workspace"])
def test_a_link_whose_end_is_gone_or_foreign_is_refused_and_writes_nothing(conn, two_units, gone):
    ids = suggest(conn, tag())
    mine = actions.accept(conn, WS, ids["Rollout"])["record_id"]
    workspace = "other" if gone == "other_workspace" else WS
    stranger = conn.execute(
        "INSERT INTO records (workspace, kind, title, created_at, updated_at)"
        " VALUES (?, 'tag', 'Other', 'x', 'x')",
        (workspace,),
    ).lastrowid
    if gone == "deleted":
        conn.execute("DELETE FROM records WHERE id = ?", (stranger,))
    suggestion = raw_link(conn, ("record", mine), ("record", stranger))
    before = tables(conn)
    with pytest.raises(Invalid) as refused:
        actions.accept(conn, WS, suggestion)
    assert refused.value.status == 409 and tables(conn) == before


def test_a_repeated_accept_returns_the_same_result_and_writes_nothing_more(conn, two_units):
    ids = suggest(conn, tag())
    first = actions.accept(conn, WS, ids["Rollout"])
    after_first = tables(conn)
    assert actions.accept(conn, WS, ids["Rollout"]) == first
    assert tables(conn) == after_first


def test_reject_records_the_decision_only_and_repeats_quietly(conn, two_units):
    ids = suggest(conn, tag())
    before = {
        t: v
        for t, v in tables(conn).items()
        if t not in ("suggestions", "suggestion_events", "record_events")
    }
    first = actions.reject(conn, WS, ids["Rollout"])
    assert first == {"id": ids["Rollout"], "status": "rejected", "record_id": None}
    after = tables(conn)
    assert {t: after[t] for t in before} == before
    assert [e for (e,) in conn.execute("SELECT event FROM suggestion_events ORDER BY id")] == [
        "created",
        "rejected",
    ]
    assert conn.execute("SELECT event FROM record_events").fetchall() == [("reject_suggestion",)]
    assert actions.reject(conn, WS, ids["Rollout"]) == first
    assert tables(conn) == after


def test_a_settled_suggestion_cannot_be_settled_the_other_way(conn, two_units):
    ids = suggest(conn, tag())
    actions.reject(conn, WS, ids["Rollout"])
    before = tables(conn)
    with pytest.raises(Invalid) as refused:
        actions.accept(conn, WS, ids["Rollout"])
    assert refused.value.status == 409 and tables(conn) == before


def test_a_failure_part_way_rolls_everything_back(conn, two_units, monkeypatch):
    ids = suggest(conn, tag())
    before = tables(conn)

    def boom(*args, **kwargs):
        raise RuntimeError("disk")

    monkeypatch.setattr(events, "insert", boom)
    with pytest.raises(RuntimeError):
        actions.accept(conn, WS, ids["Rollout"])
    assert tables(conn) == before and not conn.in_transaction


def test_the_route_answers_with_the_settled_suggestion_and_the_record_view(conn, two_units):
    ids = suggest(conn, tag())
    req = app.Request(WS, "POST", "/", "", {"id": str(ids["Rollout"])}, {})
    status, body = route._settle(actions.accept)(req)
    assert status == 200 and body["status"] == "accepted"
    assert body["record"]["title"] == "Rollout"
    status, body = route._settle(actions.reject)(req)
    assert status == 409 and "accepted" in body["error"]
    req.params["id"] = "9999"
    assert route._settle(actions.reject)(req)[0] == 404
    assert json.dumps(body)  # JSON-able
