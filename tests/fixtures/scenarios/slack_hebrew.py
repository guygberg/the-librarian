"""One picked channel of Hebrew messages (niqqud, prefixed forms, maqaf, geresh) plus an English one.

Import with LIBRARIAN_NOW=NOW.
"""

from fixtures import formats as f

NOW = 1_700_000_000
DAY = 86_400
URL = "https://acme-test.slack.com/"
USERS = [{"id": "U001", "name": "dana", "real_name": "Dana Levi"}]
CONVERSATIONS = [{"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12}]
TEXTS = [
    "הַפְּגִישָׁה נדחתה למחר",
    "נקבע לפגישה עם הלקוח",
    "צריך לבדוק את הבית־ספר ואת הצ׳ק",
    "Deploy the release tomorrow",
]


def build(target):
    f.write_slack_workspace(target, URL, USERS, CONVERSATIONS)
    f.write_slack_history(
        target, "C001", [f.slack_message("U001", t, f.ts(NOW - DAY + n)) for n, t in enumerate(TEXTS)]
    )
