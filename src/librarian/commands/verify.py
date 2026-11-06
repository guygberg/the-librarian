from librarian.query import core

help = (
    "Write the real-source check template to <data>/verification/<date>.md "
    "(counts and verdicts only)"
)

# One line per criterion of the spec's Real-source check.
# Fill in numbers and right/wrong/unsupported only:
# the file is meant to be shared, so it must never hold source text.
TEMPLATE = """\
# Real-source check, {date}

Counts and verdicts only. Never paste source text, names or quotes.

## Sample set
- slack_conversations (at least 1):
- claude_sessions (at least 1):
- hebrew_recordings (at least 1):
- mixed_hebrew_english_recordings (at least 1):
- projects_with_two_sources (at least 1):

## Open items pass
- real_open_items_total:
- real_open_items_listed (at least 8 of 10):
- false_items (must be 0):
- misses_written_down (yes/no):
- confirmed_and_inferred_labels_right (yes/no):
- stale_items_marked_stale (yes/no):

## Project status pass
- claims_right:
- claims_wrong (must be 0):
- claims_unsupported:
- evidence_links_opening_right_passage (all/some/none):
- latest_decision_named_or_declared_missing (yes/no):
- main_blocker_named_or_declared_missing (yes/no):

## Transcription pass
- readable_stretch_2_to_3_minutes (yes/no):
- names_and_numbers_wrong_and_unflagged:
- timestamps_within_10_seconds (yes/no):
- one_hour_recording_minutes (under 30):

## Import-twice check
- counts_changed_by_second_import (must be 0):
- person_events_kept (yes/no):
"""


def add_arguments(parser):
    pass


def run(args, ctx):
    date = core.now().date().isoformat()
    target = ctx.home / "verification" / f"{date}.md"
    if target.exists():
        print(f"{target} already exists; fill it in or move it away first")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TEMPLATE.format(date=date))
    print(target)
    return 0
