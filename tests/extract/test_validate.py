import json

import pytest

from extract.results import CANDIDATE_IDS, LOCATORS, UNIT_TEXT, dumps, good, with_record
from librarian.extract import schema
from librarian.extract.validate import validate
from support.jsonschema_lite import errors


def run(raw):
    return validate(raw if isinstance(raw, str) else dumps(raw), UNIT_TEXT, CANDIDATE_IDS, LOCATORS)


def test_good_result_is_accepted_whole():
    out = run(good())
    assert out.rejections == []
    assert [r["ref"] for r in out.records] == ["p1", "a1", "d1", "a2"]
    assert len(out.records[1]["links"]) == 3


BAD_RECORDS = [
    ("invented quote", with_record(1, evidence=[{"locator": "slack:C1/1.0", "quote": "I never said this", "role": "supports"}]), "records[1]", "quote_not_found", "no_evidence"),
    ("locator not sent", with_record(1, evidence=[{"locator": "slack:C9/9.9", "quote": "send the rollout plan", "role": "supports"}]), "records[1]", "bad_locator", "no_evidence"),
    ("locator malformed", with_record(1, evidence=[{"locator": "nonsense", "quote": "send the rollout plan", "role": "supports"}]), "records[1]", "bad_locator", "no_evidence"),
    ("evidence role", with_record(1, evidence=[{"locator": "slack:C1/1.0", "quote": "send the rollout plan", "role": "proves"}]), "records[1]", "bad_enum", "no_evidence"),
    ("no evidence", with_record(1, evidence=[]), "records[1]", "no_evidence", None),
    ("id not sent", with_record(0, match={"decision": "same", "id": 99}), "records[0]", "unknown_id", None),
    ("new with id", with_record(0, match={"decision": "new", "id": 7}), "records[0]", "unknown_id", None),
    ("bad decision", with_record(0, match={"decision": "maybe"}), "records[0]", "bad_enum", None),
    ("bad kind", with_record(0, kind="epic"), "records[0]", "bad_enum", None),
    ("bad lifecycle", with_record(0, lifecycle="finished"), "records[0]", "bad_enum", None),
    ("bad basis", with_record(0, basis="guessed"), "records[0]", "bad_enum", None),
    ("bad commitment", with_record(1, commitment="vow"), "records[1]", "bad_enum", None),
    ("bad date", with_record(1, stated_deadline="next Friday"), "records[1]", "bad_date", None),
    ("impossible date", with_record(1, stated_deadline="2026-02-30"), "records[1]", "bad_date", None),
    ("bad owner", with_record(1, owner={"slack_user": "dana"}), "records[1]", "bad_shape", None),
    ("action item without commitment", with_record(1, commitment=None), "records[1]", "bad_shape", None),
    ("reasoning on a project", with_record(0, reasoning="because"), "records[0]", "bad_shape", None),
    ("duplicate ref", with_record(1, ref="p1"), "records[1]", "duplicate_ref", None),
]


@pytest.mark.parametrize(("name", "result", "piece", "reason", "followup"), BAD_RECORDS, ids=[b[0] for b in BAD_RECORDS])
def test_bad_content_is_rejected_with_a_named_reason(name, result, piece, reason, followup):
    out = run(result)
    reasons = {(r.piece.split(".")[0], r.reason) for r in out.rejections}
    assert (piece, reason) in reasons
    if followup:
        assert (piece, followup) in reasons
    assert len(out.records) == 3  # the accepted remainder is still usable


def test_bad_evidence_item_drops_only_that_item():
    evidence = [
        {"locator": "slack:C1/1.0", "quote": "send the rollout plan", "role": "supports"},
        {"locator": "slack:C1/1.0", "quote": "made up", "role": "supports"},
    ]
    out = run(with_record(1, evidence=evidence))
    assert [r.piece for r in out.rejections] == ["records[1].evidence[1]"]
    assert len(out.records[1]["evidence"]) == 1


def test_quote_matches_after_whitespace_normalisation():
    spaced = {"locator": "slack:C1/1.0", "quote": "I will   send the\nrollout plan", "role": "supports"}
    assert run(with_record(1, evidence=[spaced])).rejections == []


@pytest.mark.parametrize(
    "link",
    [
        {"type": "belongs_to", "to": {"ref": "ghost"}},
        {"type": "blocks", "to": {"id": 99}},
        {"type": "belongs_to", "to": {"name": "Lee"}},
        {"type": "owner", "to": {"ref": "p1"}},
        {"type": "reports_to", "to": {"ref": "p1"}},
    ],
)
def test_bad_link_is_dropped_and_the_record_kept(link):
    out = run(with_record(1, links=[link]))
    assert [r.piece for r in out.rejections] == ["records[1].links[0]"]
    assert out.rejections[0].reason in {"bad_link_end", "bad_enum"}
    assert out.records[1]["links"] == []


def test_link_to_a_rejected_record_is_a_bad_end():
    result = with_record(0, kind="epic")
    out = run(result)
    assert ("records[1].links[0]", "bad_link_end") in {(r.piece, r.reason) for r in out.rejections}


def test_bad_parent_is_dropped():
    result = good()
    result["records"].append(
        {"ref": "p2", "match": {"decision": "new"}, "kind": "project", "title": "Sub", "lifecycle": "open",
         "basis": "inferred", "parent": {"ref": "nowhere"},
         "evidence": [{"locator": "slack:C1/1.0", "quote": "rollout plan", "role": "supports"}]}
    )
    out = run(result)
    assert [(r.piece, r.reason) for r in out.rejections] == [("records[4].parent", "bad_link_end")]
    assert "parent" not in out.records[-1]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [("{not json", "invalid_json"), ("[]", "bad_shape"), ('{"records": "x"}', "bad_shape")],
)
def test_unusable_result_is_one_rejection(raw, reason):
    out = run(raw)
    assert out.records == []
    assert [(r.piece, r.reason) for r in out.rejections] == [("result", reason)]


def test_schema_document_is_exportable_json():
    assert json.loads(schema.schema_json()) == schema.SCHEMA


def test_canned_good_result_validates_against_the_schema():
    assert errors(good(), schema.SCHEMA) == []


def test_schema_rejects_what_the_validator_rejects_structurally():
    assert errors(with_record(0, kind="epic"), schema.SCHEMA)
    assert errors(with_record(1, owner={"slack_user": "U1", "name": "x"}), schema.SCHEMA)
    assert errors(with_record(1, evidence=[{"quote": "x", "role": "supports"}]), schema.SCHEMA)
