"""The Onboarding meeting in Hebrew (UI scenario `onboarding-hebrew`).

Import with LIBRARIAN_NOW=NOW and the config CONFIG. The recording is `recording_uncertain_hebrew`'s with the
doubtful "Thursday" at 00:09:14 and a Hebrew line before it that asks for the signup copy item (extracted with a
Hebrew quote and an English gloss). A Slack legal question has no owner and was last mentioned on Oct 22, so it
is stale at NOW (CONFIG lowers the open-question threshold so that it fits inside the 30-day fetch window).
"""

import json
import random

from fixtures import formats as f
from fixtures.scenarios import recording_uncertain_hebrew as hebrew
from librarian.importer import recordings

NOW = 1_794_960_000  # 2026-11-18
CONFIG = "stale_days_open_question = 14\n"
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [{"id": "C001", "name": "onboarding", "is_channel": True, "is_private": False, "num_members": 6}]
UNCERTAIN_START = 554.0  # 00:09:14
SIGNUP_LINE = "צריך לעדכן את הטקסט במסך ההרשמה"
SIGNUP, LEGAL = "Update the signup copy", "Does legal approve the consent wording?"
SIGNUP_GLOSS = "Update the text on the signup screen"
LEGAL_AT = f.ts(1_792_659_600)  # 2026-10-22 09:00 UTC
LEGAL_TEXT = "Has legal approved the consent wording?"
SLACK_KEY = "slack-day-C001-2026-10-22"


def _record(ref: str, kind: str, title: str, locator: str, quote: str, **extra) -> dict:
    return {"ref": ref, "match": {"decision": "new"}, "kind": kind, "title": title, "lifecycle": "open",
            "basis": "stated", "evidence": [{"locator": locator, "quote": quote, "role": "supports"}]} | extra


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(target, "C001", [f.slack_message("U001", LEGAL_TEXT, LEGAL_AT)])

    flat = target / "Meet Recordings"
    intro = f.segment(0.0, 6.0, SIGNUP_LINE, random.Random(3))
    f.write_recording(flat, hebrew.NAME, [intro, *hebrew.segments(UNCERTAIN_START)], detected_language="mixed")
    file_id = recordings._file_hash(flat / hebrew.NAME)[: recordings._ID_LENGTH]

    signup = _record("s", "action_item", SIGNUP, f"drive:{file_id}/1", SIGNUP_LINE, body=SIGNUP_GLOSS,
                     commitment="request", owner={"slack_user": "U001"})
    legal = _record("l", "open_question", LEGAL, f"slack:C001/{LEGAL_AT}", LEGAL_TEXT)
    folder = target / "extraction"
    folder.mkdir()
    (folder / f"drive-{file_id}-1.json").write_text(json.dumps({"result": {"records": [signup]}}, ensure_ascii=False))
    (folder / f"{SLACK_KEY}.json").write_text(json.dumps({"result": {"records": [legal]}}))
