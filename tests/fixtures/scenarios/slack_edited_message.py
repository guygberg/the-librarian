"""One picked channel replayed twice: the second Import (generation 1) sees message 1 edited.

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


def messages(edited: bool = False):
    texts = ["first", "second (edited)" if edited else "second", "third"]
    return [f.slack_message("U001", text, f.ts(NOW - 2 * DAY + n)) for n, text in enumerate(texts)]


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(target, "C001", messages())
    f.write_slack_history(target, "C001", messages(edited=True), generation=1)
