import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_view  # noqa: E402
from test_view import person, record_id, seed  # noqa: E402

# Re-export the fixture as a variable: pytest registers it as `world`, and tests'
# `world` parameters do not shadow an import.
world = test_view.world

from fixtures.scenarios import stale_and_ownerless as s  # noqa: E402
from librarian import db  # noqa: E402
from librarian.link import review  # noqa: E402
from librarian.query import open_items  # noqa: E402
from support.cli import run_librarian  # noqa: E402
from support.serve import spawn  # noqa: E402


def ask(home, env):
    out = run_librarian(["open-items"], home, env={**env, "TZ": "UTC"})
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def groups(answer):
    return {r["title"]: r["group"] for r in answer["records"]}


def me(home):
    conn = db.connect_rw("work")
    try:
        with conn:
            return conn.execute(
                "INSERT INTO persons (workspace, name, is_me, created_at)"
                " VALUES ('work', 'Dana', 1, '2023-11-01T00:00:00+00:00')"
            ).lastrowid
    finally:
        conn.close()


def suggest(home, title, kind):
    conn = db.connect_rw("work")
    try:
        with conn:
            review.add(conn, "work", kind, record_id(home, title), "owner", "Someone")
    finally:
        conn.close()


def test_ownerless_and_stale_fixtures_land_in_needs_attention_oldest_flagged_first(world):
    home, env = world
    answer = ask(home, env)
    assert groups(answer) == {
        s.VENDOR: "needs_attention",
        s.REGION: "needs_attention",
        s.TAXES: "needs_attention",
        s.INVOICE: "needs_attention",
    }
    assert answer["records"][0]["title"] == s.VENDOR and answer["records"][0]["stale"] is True
    assert answer["headline"]["text"] == "4 things need you, 0 waiting on someone else"
    assert answer["freshness"]["last_import_finished_at"]


def test_groups_follow_owner_and_lifecycle(world):
    home, env = world
    sam = person(home)
    seed(s.TAXES, home, "owner_change", {"person_id": sam})  # someone else's item
    seed(s.VENDOR, home, "status_change", {"lifecycle": "pending", "waiting_on": "Lee"})
    seed(s.REGION, home, "status_change", {"lifecycle": "suspended", "suspended_by": "budget"})
    seed(s.INVOICE, home, "owner_change", {"person_id": me(home)})
    answer = ask(home, env)
    assert groups(answer) == {
        s.INVOICE: "needs_attention",
        s.VENDOR: "waiting_on_others",
        s.TAXES: "other_open",
        s.REGION: "other_open",
    }
    assert (answer["headline"]["needs_you"], answer["headline"]["waiting"]) == (1, 1)
    assert answer["headline"]["text"] == "1 thing needs you, 1 waiting on someone else"


def test_other_peoples_pending_item_is_other_open(world):
    home, env = world
    seed(s.TAXES, home, "owner_change", {"person_id": person(home)})
    seed(s.TAXES, home, "status_change", {"lifecycle": "pending", "waiting_on": "Lee"})
    assert groups(ask(home, env))[s.TAXES] == "other_open"


def test_suggested_owner_stays_out_of_needs_attention_and_is_marked(world):
    home, env = world
    suggest(home, s.INVOICE, review.UNCONFIRMED_PERSON)
    [invoice] = [r for r in ask(home, env)["records"] if r["title"] == s.INVOICE]
    assert invoice["group"] == "other_open" and invoice["mark"] == "unconfirmed person"
    assert "owner" not in invoice


def test_unknown_speaker_counts_as_ownerless_with_the_mark(world):
    home, env = world
    suggest(home, s.INVOICE, review.UNKNOWN_SPEAKER)
    [invoice] = [r for r in ask(home, env)["records"] if r["title"] == s.INVOICE]
    assert invoice["group"] == "needs_attention"
    assert (invoice["owner"], invoice["mark"]) == ("unknown speaker", "unknown speaker")


def test_http_route_returns_what_the_command_returns(world):
    home, env = world
    suggest(home, s.INVOICE, review.UNCONFIRMED_PERSON)
    env = {**env, "TZ": "UTC"}
    proc, served = spawn(home, "--port", "0", env=env)
    try:
        resp, data = served.request("GET", "/api/open-items", {"X-Librarian-Token": served.token()})
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
    assert resp.status == 200
    assert json.loads(data) == ask(home, env)


def test_missing_database_is_the_schema_outdated_envelope(home):
    result = run_librarian(["open-items"], home)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "schema_outdated"


@pytest.mark.parametrize(
    ("at", "start"),
    [
        ("2023-11-12T00:00:00", "2023-11-12T00:00:00"),
        ("2023-11-11T23:59:59", "2023-11-05T00:00:00"),
        ("2023-11-14T22:13:20", "2023-11-12T00:00:00"),
        ("2023-11-18T23:59:59", "2023-11-12T00:00:00"),
    ],
)
def test_week_starts_sunday_midnight_local(at, start):
    zone = timezone(timedelta(hours=2))
    got = open_items.week_start(datetime.fromisoformat(at).replace(tzinfo=zone))
    assert got == datetime.fromisoformat(start).replace(tzinfo=zone)


def test_progress_counts_only_this_weeks_completions(world):
    home, env = world
    # Ship the report was completed 20 days ago; finding that Evidence only now does not make
    # it this week's.
    assert ask(home, env)["progress"]["done_this_week"] == 0
    seed(s.TAXES, home, "status_change", {"lifecycle": "done"}, "2023-11-11T23:59:59+00:00")
    seed(s.INVOICE, home, "status_change", {"lifecycle": "done"}, "2023-11-12T00:00:00+00:00")
    seed(s.VENDOR, home, "status_change", {"lifecycle": "pending", "waiting_on": "Lee"})
    seed(s.REGION, home, "status_change", {"lifecycle": "suspended"})
    progress = ask(home, env)["progress"]
    assert (progress["done_this_week"], progress["total"]) == (1, 1 + 1)
    assert progress["week_start"] == datetime(2023, 11, 12, tzinfo=UTC).isoformat()
