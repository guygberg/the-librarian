"""Canned extraction results shared by the validator and run-record tests."""

import copy
import json

UNIT_TEXT = (
    "Dana:  I will send the   rollout plan by Friday.\n"
    "Lee: we decided to ship in two phases, because the migration is risky.\n"
    "Lee: התחלנו עם הבדיקות"
)
LOCATORS = {"slack:C1/1.0", "slack:C1/2.0"}
CANDIDATE_IDS = {7, 8}


def good() -> dict:
    return {
        "records": [
            {
                "ref": "p1",
                "match": {"decision": "same", "id": 7},
                "kind": "project",
                "title": "Rollout",
                "lifecycle": "open",
                "basis": "stated",
                "evidence": [{"locator": "slack:C1/1.0#1", "quote": "send the rollout plan", "role": "supports"}],
            },
            {
                "ref": "a1",
                "match": {"decision": "new"},
                "kind": "action_item",
                "title": "Send rollout plan",
                "lifecycle": "open",
                "basis": "stated",
                "commitment": "commitment",
                "owner": {"slack_user": "U123ABC"},
                "stated_deadline": "2026-11-13",
                "links": [
                    {"type": "belongs_to", "to": {"ref": "p1"}},
                    {"type": "waiting_on", "to": {"name": "Lee"}},
                    {"type": "related_to", "to": {"id": 8}},
                ],
                "evidence": [{"locator": "slack:C1/1.0", "quote": "I will send the rollout plan by Friday", "role": "supports"}],
            },
            {
                "ref": "d1",
                "match": {"decision": "updated", "id": 8},
                "kind": "decision",
                "title": "Ship in two phases",
                "lifecycle": "done",
                "basis": "inferred",
                "reasoning": "the migration is risky",
                "evidence": [
                    {"locator": "slack:C1/2.0", "quote": "התחלנו עם הבדיקות", "role": "supports", "gloss": "We started with the tests"}
                ],
            },
            {
                "ref": "a2",
                "match": {"decision": "new"},
                "kind": "action_item",
                "title": "Unknown speaker promises",
                "lifecycle": "open",
                "basis": "inferred",
                "commitment": "intention",
                "owner": {"speaker": "first_person"},
                "evidence": [{"locator": "slack:C1/2.0", "quote": "we decided to ship", "role": "completes"}],
            },
        ]
    }


def with_record(index: int, **changes) -> dict:
    """`good()` with changes applied to one Record; a None value removes the key."""
    result = copy.deepcopy(good())
    for key, value in changes.items():
        if value is None:
            result["records"][index].pop(key, None)
        else:
            result["records"][index][key] = value
    return result


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)
