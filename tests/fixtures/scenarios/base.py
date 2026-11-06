"""Base fixture set: English, Hebrew and mixed content; project "Atlas" appears in all three
sources."""

import random

from fixtures import formats as f

T0 = 1_760_000_000  # fixed clock: every timestamp derives from this

USERS = [
    {"id": "U001", "name": "dana", "real_name": "Dana Levi"},
    {"id": "U002", "name": "omer", "real_name": "עומר כהן"},
    {"id": "U003", "name": "priya", "real_name": "Priya Shah"},
]

CONVERSATIONS = [
    {"id": "C001", "name": "atlas-dev", "is_channel": True, "is_private": False, "num_members": 12},
    {"id": "C002", "name": "random", "is_channel": True, "is_private": False, "num_members": 40},
    {"id": "G001", "name": "atlas-leads", "is_group": True, "is_private": True, "num_members": 4},
    {"id": "D001", "is_im": True, "is_private": True, "user": "U002", "num_members": 2},
    {
        "id": "M001",
        "name": "mpdm-dana--omer--priya-1",
        "is_mpim": True,
        "is_private": True,
        "num_members": 3,
    },
    {"id": "C003", "name": "עברית-צוות", "is_channel": True, "is_private": False, "num_members": 7},
]
PICKED = ["C001", "G001", "D001", "C003"]

HEBREW_NIQQUD = "שָׁלוֹם, נִפְגָּשׁ מָחָר בַּבֹּקֶר"


def _slack(target):
    f.write_slack_workspace(target, "https://acme-test.slack.com/", USERS, CONVERSATIONS)
    f.write_json(target / "slack" / "picked.json", {"picked": PICKED})

    # 230 messages: forces a second history page.
    bulk = [
        f.slack_message(USERS[i % 3]["id"], f"Atlas status note {i}", f.ts(T0 + i * 60))
        for i in range(230)
    ]
    root = f.ts(T0 + 100 * 60)
    bulk[100] = f.slack_message(
        "U001", "Should Atlas use SQLite per workspace?", root, thread_ts=root
    )
    f.write_slack_history(target, "C001", bulk)
    f.write_slack_replies(
        target,
        "C001",
        root,
        [
            bulk[100],
            f.slack_message(
                "U003",
                "Yes, decided: SQLite with FTS5.",
                f.ts(T0 + 100 * 60 + 30, 1),
                thread_ts=root,
            ),
            f.slack_message(
                "U002",
                "מסכים, נתחיל מזה",
                f.ts(T0 + 100 * 60 + 90, 2),
                thread_ts=root,
                files=[{"id": "F001", "name": "schema.png", "mimetype": "image/png"}],
            ),
        ],
    )

    f.write_slack_history(
        target,
        "G001",
        [f.slack_message("U001", "Atlas launch moves to next sprint, ok?", f.ts(T0 + 5000))],
    )
    f.write_slack_history(
        target,
        "D001",
        [
            f.slack_message("U002", HEBREW_NIQQUD, f.ts(T0 + 6000)),
            f.slack_message("U001", "Great, see you then. נדבר על Atlas", f.ts(T0 + 6060)),
        ],
    )
    f.write_slack_history(
        target, "M001", [f.slack_message("U003", "Lunch on Thursday?", f.ts(T0 + 7000))]
    )
    f.write_slack_history(
        target, "C002", [f.slack_message("U003", "Anyone seen the new café?", f.ts(T0 + 8000))]
    )
    f.write_slack_history(
        target,
        "C003",
        [f.slack_message("U002", "שלום לכולם, הפגישה נדחתה ליום רביעי", f.ts(T0 + 9000))],
    )


def _sessions(target):
    iso = lambda n: f"2026-10-1{n}T09:0{n}:00.000Z"  # noqa: E731
    f.write_session(
        target,
        "-home-dana-projects-atlas",
        "11111111-aaaa-4bbb-8ccc-000000000001",
        [
            f.session_line(
                "user", iso(1), "Why does the Atlas importer re-read old pages?", sessionId="s1"
            ),
            f.session_line(
                "assistant",
                iso(2),
                [
                    {"type": "text", "text": "Let me check the cursor handling."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Read",
                        "input": {"file_path": "importer.py"},
                    },
                ],
                sessionId="s1",
            ),
            f.session_line(
                "user",
                iso(3),
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "def import_pages(): ...",
                    }
                ],
                sessionId="s1",
            ),
            f.session_line(
                "assistant",
                iso(4),
                [{"type": "text", "text": "The cursor is never saved; add a checkpoint."}],
                sessionId="s1",
            ),
        ],
    )
    f.write_session(
        target,
        "-home-dana-projects-garden",
        "22222222-aaaa-4bbb-8ccc-000000000002",
        [
            f.session_line("user", iso(5), "תכתוב לי פונקציה שמחשבת שטח גינה", sessionId="s2"),
            f.session_line(
                "assistant",
                iso(6),
                [{"type": "text", "text": "Sure: area = width * length."}],
                sessionId="s2",
            ),
        ],
    )


def _recordings(target):
    rng = random.Random(7)
    drive = target / "My Drive" / "Google Meet" / "Atlas sync - 2026-10-12 10.00 GMT+03.00"
    f.write_recording(
        drive,
        "Atlas sync - 2026-10-12 10.00 GMT+03.00 - Recording",
        [
            f.segment(0.0, 4.5, "Let's review the Atlas schema decisions.", rng),
            f.segment(4.5, 9.0, "אני חושב שנשתמש ב SQLite לכל workspace", rng),
        ],
    )
    flat = target / "Meet Recordings"
    f.write_recording(
        flat,
        "שיחת צוות - 2026-10-14 16.30 GMT+03.00 - Recording",
        [f.segment(0.0, 5.0, HEBREW_NIQQUD, rng), f.segment(5.0, 8.0, "תודה לכולם", rng)],
    )
    f.write_recording(
        flat,
        "Standup - 2026-10-15 09.00 GMT+03.00 - Recording",
        [f.segment(0.0, 3.0, "Quick standup, nothing blocked.", rng)],
    )


def build(target):
    _slack(target)
    _sessions(target)
    _recordings(target)
