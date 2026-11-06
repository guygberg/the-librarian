"""One picked channel replayed twice. The second Import (generation 1) no longer returns the message
2 days old (inside the 7-day re-check window) nor the one 20 days old (outside it).

Import with LIBRARIAN_NOW=NOW.
"""

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}
]

RECENT = f.slack_message("U001", "deleted recently", f.ts(NOW - 2 * DAY))
KEPT = f.slack_message("U001", "still there", f.ts(NOW - 3 * DAY))
OLD = f.slack_message("U001", "deleted long ago", f.ts(NOW - 20 * DAY))


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(target, "C001", [OLD, KEPT, RECENT])
    f.write_slack_history(target, "C001", [KEPT], generation=1)
