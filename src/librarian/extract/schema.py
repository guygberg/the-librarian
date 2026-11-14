"""The extraction result contract: one JSON schema, exported for `claude -p --json-schema`.

The enum lists here are the single home for the validator too. They mirror the CHECK constraints in
`migrations/0001_core.sql`. Extraction never emits a `tag` Record; only an accepted Suggestion
creates one.
"""

import hashlib
import json

KINDS = ["tag", "action_item", "decision", "blocker", "open_question"]
LIFECYCLES = ["open", "pending", "suspended", "done", "dropped", "superseded"]
BASES = ["stated", "inferred", "confirmed"]
COMMITMENTS = ["intention", "request", "commitment"]
LINK_TYPES = [
    "belongs_to",
    "owner",
    "waiting_on",
    "blocks",
    "supersedes",
    "related_to",
    "mentions",
    "contradicts",
]
ID_DECISIONS = ["same", "updated", "new"]
EVIDENCE_ROLES = ["supports", "completes", "contradicts"]

# A link end or parent: a Record of this result, a candidate Record id, or (links only) a person.
_REF_END = {
    "type": "object",
    "required": ["ref"],
    "additionalProperties": False,
    "properties": {"ref": {"type": "string"}},
}
_ID_END = {
    "type": "object",
    "required": ["id"],
    "additionalProperties": False,
    "properties": {"id": {"type": "integer"}},
}
_OWNER_VARIANTS = [
    {
        "type": "object",
        "required": ["slack_user"],
        "additionalProperties": False,
        "properties": {"slack_user": {"type": "string"}},
    },
    {
        "type": "object",
        "required": ["name"],
        "additionalProperties": False,
        "properties": {"name": {"type": "string"}},
    },
    {
        "type": "object",
        "required": ["speaker"],
        "additionalProperties": False,
        "properties": {"speaker": {"enum": ["first_person"]}},
    },
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


SUGGEST_KINDS = ["new_tag", "new_item", "link"]
SUGGEST_BASES = ["stated", "inferred"]
SUGGEST_LIFECYCLES = ["open", "pending"]
INFERRED_CAP = 89

# A Link end of a Suggestion: a candidate Record or Person, or a new Tag/Item of the same answer.
_TYPED_END = {
    "type": "object",
    "required": ["type", "id"],
    "additionalProperties": False,
    "properties": {"type": {"enum": ["record", "person"]}, "id": {"type": "integer"}},
}

SUGGEST_SCHEMA = {
    "type": "object",
    "required": ["suggestions"],
    "additionalProperties": False,
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ref", "kind", "confidence", "basis", "reasoning", "evidence"],
                "additionalProperties": False,
                "properties": {
                    "ref": {"type": "string"},
                    "kind": {"enum": SUGGEST_KINDS},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "owner": {
                        "oneOf": [
                            _ID_END,
                            {
                                "type": "object",
                                "required": ["raw_name"],
                                "additionalProperties": False,
                                "properties": {"raw_name": {"type": "string"}},
                            },
                        ]
                    },
                    "stated_deadline": {"type": "string"},
                    "lifecycle": {"enum": SUGGEST_LIFECYCLES},
                    "link_type": {"enum": LINK_TYPES},
                    "from": {"oneOf": [_TYPED_END, _REF_END]},
                    "to": {"oneOf": [_TYPED_END, _REF_END]},
                    "confidence": {"type": "integer"},
                    "basis": {"enum": SUGGEST_BASES},
                    "reasoning": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["locator", "quote"],
                            "additionalProperties": False,
                            "properties": {
                                "locator": {"type": "string"},
                                "quote": {"type": "string"},
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


def suggest_schema_json() -> str:
    return json.dumps(SUGGEST_SCHEMA, sort_keys=True, indent=2)


def suggest_schema_hash() -> str:
    return hashlib.sha256(suggest_schema_json().encode()).hexdigest()
