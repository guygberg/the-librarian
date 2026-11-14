import copy
import json

import pytest

from librarian import db
from librarian.extract import runs, schema, suggest_validate
from librarian.extract.candidates import pick_for_suggestions
from librarian.extract.claude_runner import ClaudeExtractor, ClaudeSuggester, ExtractionFailed
from librarian.extract.units import Unit
from support.jsonschema_lite import errors

DANA = "I will send the rollout plan by Friday."
LEE = "we decided to ship in two phases"
HEBREW = "דנה תשלח את תוכנית ההטמעה"

CANDIDATES = [
    {"id": 7, "kind": "tag", "title": "Rollout"},
    {"id": 8, "kind": "action_item", "title": "Send plan", "lifecycle": "open"},
    {"id": 3, "kind": "person", "name": "Dana Levi", "aliases": ["Dana"]},
]


def make_unit():
    unit = Unit("slack-day-C1-2026-11-01")
    unit.add("slack", "C1/1.0", "Dana", DANA, revision_id=11)
    unit.add("slack", "C1/2.0", "Lee", LEE, revision_id=12)
    unit.add("slack", "C1/3.0", "Lee", HEBREW, revision_id=13)
    return unit


def ev(quote=DANA, locator="slack:C1/1.0#1"):
    return {"locator": locator, "quote": quote}


def sug(kind, ref, **over):
    base = {
        "ref": ref,
        "kind": kind,
        "confidence": 92,
        "basis": "stated",
        "reasoning": "Named in the text.",
        "evidence": [ev()],
    }
    extra = {
        "new_tag": {"title": "Pricing", "body": ""},
        "new_item": {"title": "Send plan", "lifecycle": "open"},
        "link": {
            "link_type": "belongs_to",
            "from": {"type": "record", "id": 8},
            "to": {"type": "record", "id": 7},
        },
    }[kind]
    return {**base, **extra, **over}


def run(items, min_confidence=40, unit=None):
    raw = items if isinstance(items, str) else json.dumps({"suggestions": items})
    return suggest_validate.validate(raw, unit or make_unit(), CANDIDATES, min_confidence)


def reasons(out):
    return [(r.piece, r.reason) for r in out.rejections]


def test_all_six_decisions_are_accepted_with_exact_revisions():
    items = [
        sug("new_tag", "t1"),
        sug("link", "l1"),  # Tag Link: an existing item belongs to an existing Tag
        sug(
            "link",
            "l2",
            link_type="mentions",
            **{"from": {"ref": "t1"}, "to": {"type": "person", "id": 3}},
        ),
        sug("new_item", "i1", owner={"id": 3}, stated_deadline="2026-11-20"),
        sug(
            "link",
            "l3",
            link_type="related_to",
            to={"type": "record", "id": 8},
            **{"from": {"ref": "t1"}},
        ),
        sug(
            "link",
            "l4",
            link_type="owner",
            **{"from": {"ref": "i1"}, "to": {"type": "person", "id": 3}},
        ),
    ]
    out = run(items)
    assert out.rejections == []
    assert [s["ref"] for s in out.suggestions] == ["t1", "l1", "l2", "i1", "l3", "l4"]
    assert out.suggestions[0]["evidence"] == [
        {"revision_id": 11, "locator": "slack:C1/1.0#1", "quote": DANA}
    ]
    assert {s["band"] for s in out.suggestions} == {"high"}


def test_empty_list_is_valid():
    out = run([])
    assert out.suggestions == [] and out.rejections == []


def test_hebrew_quote_and_title():
    item = sug("new_item", "i1", title="לשלוח תוכנית", evidence=[ev(HEBREW, "slack:C1/3.0")])
    out = run([item])
    assert out.rejections == []
    assert out.suggestions[0]["evidence"][0]["revision_id"] == 13


def test_bad_json_and_shape_drop_the_answer():
    assert reasons(run("{nope")) == [("result", "invalid_json")]
    assert reasons(run('{"records": []}')) == [("result", "bad_shape")]


@pytest.mark.parametrize("bad", [None, True, 91.5, "90", 90.0])
def test_non_integer_confidence_is_rejected(bad):
    assert reasons(run([sug("new_tag", "t1", confidence=bad)])) == [
        ("suggestions[0]", "bad_confidence")
    ]


def test_missing_confidence_is_rejected():
    item = sug("new_tag", "t1")
    del item["confidence"]
    assert reasons(run([item])) == [("suggestions[0]", "bad_confidence")]


def test_confidence_is_clamped_capped_and_banded():
    out = run(
        [
            sug("new_tag", "a", confidence=250),
            sug("new_tag", "b", confidence=95, basis="inferred"),
            sug("new_tag", "c", confidence=75),
            sug("new_tag", "d", confidence=60),
            sug("new_tag", "e", confidence=59),
            sug("new_tag", "f", confidence=-5),
        ],
        min_confidence=0,
    )
    got = [(s["confidence"], s["band"]) for s in out.suggestions]
    assert got == [
        (100, "high"),
        (89, "high"),
        (75, "medium"),
        (60, "medium"),
        (59, "low"),
        (0, "low"),
    ]


def test_persistence_floor_drops_and_logs():
    out = run([sug("new_tag", "a", confidence=39), sug("new_tag", "b", confidence=40)])
    assert [s["ref"] for s in out.suggestions] == ["b"]
    assert reasons(out) == [("suggestions[0]", "below_confidence_floor")]


def test_inferred_is_capped_before_the_floor():
    out = run([sug("new_tag", "a", confidence=95, basis="inferred")], min_confidence=90)
    assert reasons(out) == [("suggestions[0]", "below_confidence_floor")]


BAD = [
    ("invented quote", sug("new_tag", "t", evidence=[ev("never said")]), "no_evidence"),
    (
        "quote only across items",
        sug("new_tag", "t", evidence=[ev(DANA[:10] + " " + LEE[:5])]),
        "no_evidence",
    ),
    (
        "quote from another item than its locator",
        sug("new_tag", "t", evidence=[ev(LEE, "slack:C1/1.0")]),
        "no_evidence",
    ),
    (
        "whitespace is not normalised",
        sug("new_tag", "t", evidence=[ev("send  the")]),
        "no_evidence",
    ),
    ("locator not sent", sug("new_tag", "t", evidence=[ev(DANA, "slack:C9/9.9")]), "no_evidence"),
    ("locator malformed", sug("new_tag", "t", evidence=[ev(DANA, "nonsense")]), "no_evidence"),
    ("no evidence", sug("new_tag", "t", evidence=[]), "no_evidence"),
    ("kind", {**sug("new_tag", "t"), "kind": "project"}, "bad_enum"),
    ("basis", sug("new_tag", "t", basis="confirmed"), "bad_enum"),
    ("no title", sug("new_tag", "t", title=" "), "bad_shape"),
    ("no reasoning", sug("new_tag", "t", reasoning=""), "bad_shape"),
    ("owner on a tag", sug("new_tag", "t", owner={"id": 3}), "bad_shape"),
    ("link fields on an item", sug("new_item", "t", link_type="owner"), "bad_shape"),
    ("item lifecycle", sug("new_item", "t", lifecycle="done"), "bad_enum"),
    ("item date", sug("new_item", "t", stated_deadline="soon"), "bad_date"),
    ("unknown owner id", sug("new_item", "t", owner={"id": 99}), "unknown_id"),
    ("tag id as owner", sug("new_item", "t", owner={"id": 7}), "unknown_id"),
    ("empty raw name", sug("new_item", "t", owner={"raw_name": " "}), "bad_shape"),
    ("link type", sug("link", "t", link_type="loves"), "bad_enum"),
    ("unknown record id", sug("link", "t", to={"type": "record", "id": 99}), "unknown_id"),
    ("person id as record", sug("link", "t", to={"type": "record", "id": 3}), "unknown_id"),
    ("source item end", sug("link", "t", to={"type": "source_item", "id": 1}), "bad_link_end"),
    ("dangling ref", sug("link", "t", to={"ref": "nope"}), "bad_ref"),
    ("owner to a record", sug("link", "t", link_type="owner"), "bad_link_end"),
    (
        "related_to a person",
        sug("link", "t", link_type="related_to", to={"type": "person", "id": 3}),
        "bad_link_end",
    ),
    (
        "person to person",
        sug(
            "link",
            "t",
            link_type="mentions",
            **{"from": {"type": "person", "id": 3}, "to": {"type": "person", "id": 3}},
        ),
        "bad_link_end",
    ),
]


@pytest.mark.parametrize(("name", "item", "reason"), BAD, ids=[b[0] for b in BAD])
def test_bad_suggestion_is_dropped_with_its_reason(name, item, reason):
    out = run([item])
    assert out.suggestions == []
    assert reasons(out)[-1] == ("suggestions[0]", reason)


def test_one_bad_piece_does_not_drop_the_rest():
    out = run(
        [
            sug("new_tag", "good"),
            sug("new_tag", "bad", evidence=[ev("never said")]),
            sug("new_tag", "mixed", evidence=[ev("never said"), ev(LEE, "slack:C1/2.0")]),
        ]
    )
    assert [s["ref"] for s in out.suggestions] == ["good", "mixed"]
    assert out.suggestions[1]["evidence"] == [
        {"revision_id": 12, "locator": "slack:C1/2.0", "quote": LEE}
    ]
    assert [r.reason for r in out.rejections] == [
        "quote_not_found",
        "no_evidence",
        "quote_not_found",
    ]


def test_duplicate_ref_is_rejected():
    out = run([sug("new_tag", "x"), sug("new_tag", "x")])
    assert [s["ref"] for s in out.suggestions] == ["x"]
    assert reasons(out) == [("suggestions[1]", "duplicate_ref")]


def test_link_to_a_dropped_suggestion_is_a_bad_ref():
    out = run(
        [
            sug("new_tag", "t1", confidence=10),
            sug(
                "link",
                "l1",
                **{"from": {"ref": "t1"}, "to": {"type": "record", "id": 8}},
                link_type="related_to",
            ),
        ]
    )
    assert out.suggestions == []
    assert reasons(out) == [
        ("suggestions[0]", "below_confidence_floor"),
        ("suggestions[1]", "bad_ref"),
    ]


def test_link_cannot_point_at_another_link():
    out = run([sug("link", "l1"), sug("link", "l2", **{"from": {"ref": "l1"}})])
    assert [s["ref"] for s in out.suggestions] == ["l1"]
    assert reasons(out) == [("suggestions[1]", "bad_ref")]


def test_schema_accepts_a_valid_answer_and_rejects_a_boolean_confidence():
    answer = {"suggestions": [sug("link", "l1")]}
    assert errors(answer, schema.SUGGEST_SCHEMA) == []
    bad = copy.deepcopy(answer)
    bad["suggestions"][0]["confidence"] = True
    assert errors(bad, schema.SUGGEST_SCHEMA)


def test_hashes_differ_from_extraction():
    assert schema.suggest_schema_hash() != schema.schema_hash()


def test_runner_uses_suggestions_prompt_and_schema():
    cfg = {
        "claude_bin": "claude",
        "claude_model": "m",
        "claude_workers": 1,
        "claude_max_turns": 1,
        "claude_max_budget_usd": 1,
        "claude_retries": 0,
        "claude_backoff_seconds": 0,
    }
    argv = ClaudeSuggester(cfg).argv()
    assert argv[argv.index("--json-schema") + 1] == schema.suggest_schema_json()
    assert argv[2] != ClaudeExtractor(cfg).argv()[2]


class Fake:
    def __init__(self, answer=None, failure=None):
        self.answer, self.failure = answer, failure

    def extract(self, unit_key, unit_text, candidates):
        if self.failure:
            raise self.failure
        return json.dumps(self.answer)


META = runs.RunMeta(model="m", claude_code_version="1", prompt="p")


@pytest.fixture
def conn(home, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    conn = db.connect_rw("work")
    yield conn
    conn.close()


def test_run_is_recorded_with_purpose_suggestions_and_rejections(conn):
    answer = {"suggestions": [sug("new_tag", "ok"), sug("new_tag", "bad", evidence=[ev("nope")])]}
    run_id, result = runs.suggest_and_record(
        conn, "work", Fake(answer), META, make_unit(), CANDIDATES, 40
    )
    assert [s["ref"] for s in result.suggestions] == ["ok"]
    assert conn.execute(
        "SELECT purpose, schema_hash, accepted FROM extraction_runs WHERE id = ?", (run_id,)
    ).fetchone() == ("suggestions", schema.suggest_schema_hash(), 1)
    assert conn.execute(
        "SELECT piece, reason FROM extraction_rejections WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall() == [
        ("suggestions[1].evidence[0]", "quote_not_found"),
        ("suggestions[1]", "no_evidence"),
    ]
    assert runs.list_runs(conn, "work") == []


def test_failed_call_keeps_the_run_and_raises(conn):
    failure = ExtractionFailed("call", "boom", "{envelope}")
    with pytest.raises(ExtractionFailed):
        runs.suggest_and_record(
            conn, "work", Fake(failure=failure), META, make_unit(), CANDIDATES, 40
        )
    assert conn.execute("SELECT purpose, envelope FROM extraction_runs").fetchall() == [
        ("suggestions", "{envelope}")
    ]
    assert conn.execute("SELECT reason FROM extraction_rejections").fetchall() == [
        ("extraction_failed",)
    ]


def test_candidates_are_this_workspaces_tags_open_items_and_persons(conn):
    now = "2026-11-01T00:00:00+00:00"
    for ws in ("work", "other"):
        conn.execute(
            "INSERT INTO persons (workspace, name, created_at) VALUES (?, ?, ?)",
            (ws, f"P-{ws}", now),
        )
        conn.execute(
            "INSERT INTO records (workspace, kind, title, lifecycle, created_at, updated_at)"
            " VALUES (?, 'tag', ?, 'open', ?, ?)",
            (ws, f"Tag-{ws}", now, now),
        )
        for lifecycle in ("open", "done"):
            conn.execute(
                "INSERT INTO records (workspace, kind, title, lifecycle, created_at, updated_at)"
                " VALUES (?, 'action_item', ?, ?, ?, ?)",
                (ws, f"Item-{ws}-{lifecycle}", lifecycle, now, now),
            )
    conn.execute("INSERT INTO aliases (workspace, person_id, alias) VALUES ('work', 1, 'Pee')")
    got = pick_for_suggestions(conn, "work", make_unit(), 30)
    assert [(c["kind"], c.get("title") or c["name"]) for c in got] == [
        ("tag", "Tag-work"),
        ("action_item", "Item-work-open"),
        ("person", "P-work"),
    ]
    assert got[-1]["aliases"] == ["Pee"]
