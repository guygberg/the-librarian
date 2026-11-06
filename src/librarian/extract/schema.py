"""The extraction result contract: one JSON schema, exported for `claude -p --json-schema`.

The enum lists here are the single home for the validator too. They mirror the CHECK constraints in
`migrations/0001_core.sql`.
"""

import hashlib
import json

KINDS = ["project", "action_item", "decision", "blocker", "open_question"]
LIFECYCLES = ["open", "pending", "suspended", "done", "dropped", "superseded"]
BASES = ["stated", "inferred", "confirmed"]
COMMITMENTS = ["intention", "request", "commitment"]
LINK_TYPES = ["belongs_to", "owner", "waiting_on", "blocks", "supersedes", "related_to", "mentions"]
ID_DECISIONS = ["same", "updated", "new"]
EVIDENCE_ROLES = ["supports", "completes", "contradicts"]

# A link end or parent: a Record of this result, a candidate Record id, or (links only) a person.
_REF_END = {"type": "object", "required": ["ref"], "additionalProperties": False,
            "properties": {"ref": {"type": "string"}}}
_ID_END = {"type": "object", "required": ["id"], "additionalProperties": False,
           "properties": {"id": {"type": "integer"}}}
_OWNER_VARIANTS = [
    {"type": "object", "required": ["slack_user"], "additionalProperties": False,
     "properties": {"slack_user": {"type": "string"}}},
    {"type": "object", "required": ["name"], "additionalProperties": False,
     "properties": {"name": {"type": "string"}}},
    {"type": "object", "required": ["speaker"], "additionalProperties": False,
     "properties": {"speaker": {"enum": ["first_person"]}}},
]

SCHEMA = {
    "type": "object",
    "required": ["records"],
    "additionalProperties": False,
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ref", "match", "kind", "title", "lifecycle", "basis", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "ref": {"type": "string"},
                    "match": {
                        "type": "object",
                        "required": ["decision"],
                        "additionalProperties": False,
                        "properties": {
                            "decision": {"enum": ID_DECISIONS},
                            "id": {"type": "integer"},
                        },
                    },
                    "kind": {"enum": KINDS},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "lifecycle": {"enum": LIFECYCLES},
                    "basis": {"enum": BASES},
                    "commitment": {"enum": COMMITMENTS},
                    "owner": {"oneOf": _OWNER_VARIANTS},
                    "stated_deadline": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "parent": {"oneOf": [_REF_END, _ID_END]},
                    "links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type", "to"],
                            "additionalProperties": False,
                            "properties": {
                                "type": {"enum": LINK_TYPES},
                                "to": {"oneOf": [_REF_END, _ID_END, *_OWNER_VARIANTS]},
                            },
                        },
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["locator", "quote", "role"],
                            "additionalProperties": False,
                            "properties": {
                                "locator": {"type": "string"},
                                "quote": {"type": "string"},
                                "role": {"enum": EVIDENCE_ROLES},
                                "gloss": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}


def schema_json() -> str:
    return json.dumps(SCHEMA, sort_keys=True, indent=2)


def schema_hash() -> str:
    return hashlib.sha256(schema_json().encode()).hexdigest()
