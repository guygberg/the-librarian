"""A session that calls `librarian`: only the user's own words survive as evidence."""

from fixtures import formats as f

SESSION_ID = "33333333-aaaa-4bbb-8ccc-000000000003"
PROJECT = "-home-dana-projects-atlas"


def build(target):
    iso = lambda n: f"2026-10-20T09:0{n}:00.000Z"  # noqa: E731
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "Bash",
        "input": {"command": "librarian open-items"},
    }
    f.write_session(
        target,
        PROJECT,
        SESSION_ID,
        [
            f.session_line("user", iso(1), "What are my open items on Atlas?"),
            f.session_line("assistant", iso(2), [{"type": "text", "text": "Checking."}, call]),
            f.session_line(
                "user",
                iso(3),
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "Open: ship the zephyr report",
                    }
                ],
            ),
            f.session_line("user", iso(4), "the cutover moved to Dec 1"),
            f.session_line(
                "assistant",
                iso(5),
                [{"type": "text", "text": "Noted: the cutover moved to Dec 1."}],
            ),
        ],
    )
