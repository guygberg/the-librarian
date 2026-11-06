import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from fixtures.build import build
from fixtures.scenarios import stale_and_ownerless as s
from librarian import config, db, events
from librarian.query import stale
from support.cli import finish_tty, popen_librarian_tty, run_librarian


@pytest.fixture
def world(tmp_path, home, monkeypatch):
    fixtures = tmp_path / "fixtures"
    build(fixtures, "stale_and_ownerless")
    home.mkdir(parents=True)
    (home / "config.toml").write_text('account_type = "team"\nusage_rules_confirmed = true\n')
    (home / "workspaces" / "work").mkdir(parents=True)
    (home / "workspaces" / "work" / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    monkeypatch.setenv("LIBRARIAN_HOME", str(home))
    env = {
        "LIBRARIAN_ENGINES": "fake",
        "LIBRARIAN_FIXTURES": str(fixtures),
        "LIBRARIAN_NOW": str(s.NOW),
    }
    run_import(home, env)
    return home, env


def run_import(home, env):
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    assert code == 0, out


def record_id(home, title):
    row = (
        sqlite3.connect(next(home.rglob("*.db")))
        .execute("SELECT id FROM records WHERE title = ?", (title,))
        .fetchone()
    )
    return row[0]


def show(home, env, title):
    out = run_librarian(["show", str(record_id(home, title))], home, env=env)
    assert out.returncode == 0, out.stdout
    answer = json.loads(out.stdout)
    answer.pop("freshness")  # moves with every Import; the Record itself must not
    return answer


def person(home, name="Sam Owner"):
    conn = db.connect_rw("work")
    try:
        return conn.execute(
            "INSERT INTO persons (workspace, name, created_at)"
            " VALUES ('work', ?, '2023-11-01T00:00:00+00:00')",
            (name,),
        ).lastrowid
    finally:
        conn.close()


def seed(title, home, event, detail=None, at=None):
    rid = record_id(home, title)
    conn = db.connect_rw("work")
    try:
        events.append(conn, "work", rid, event, detail, at)
    finally:
        conn.close()


def test_events_show_as_history_survive_import_and_set_basis_and_lifecycle(world):
    home, env = world
    seed(s.TAXES, home, "owner_change", {"person_id": person(home)}, "2023-11-14T10:00:00+00:00")
    seed(
        s.TAXES,
        home,
        "status_change",
        {"lifecycle": "pending", "waiting_on": "Lee"},
        "2023-11-14T11:00:00+00:00",
    )
    before = show(home, env, s.TAXES)

    run_import(home, env)
    after = show(home, env, s.TAXES)

    assert after == before
    assert [h["event"] for h in after["history"]] == ["owner_change", "status_change"]
    assert after["history"][1] == {
        "event": "status_change",
        "at": "2023-11-14T11:00:00+00:00",
        "change": {"lifecycle": "pending", "waiting_on": "Lee"},
    }
    assert (after["basis"], after["lifecycle"], after["waiting_on"]) == (
        "confirmed",
        "pending",
        "Lee",
    )
    assert (after["commitment"], after["owner"]) == ("intention", "Sam Owner")
    assert "history" in show(home, env, s.VENDOR) and show(home, env, s.VENDOR)["history"] == []


def test_done_needs_completion_evidence_or_the_persons_mark(world):
    home, env = world
    taxes, shipped = show(home, env, s.TAXES), show(home, env, s.SHIP)
    assert taxes["lifecycle"] == "open" and "done_at" not in taxes
    assert shipped["lifecycle"] == "done"
    assert shipped["done_at"] == datetime.fromtimestamp(s.NOW - 20 * s.DAY - 60, UTC).isoformat()

    seed(s.TAXES, home, "status_change", {"lifecycle": "done"}, "2023-11-13T09:00:00+00:00")
    seed(s.SHIP, home, "status_change", {"lifecycle": "done"}, "2023-11-14T09:00:00+00:00")
    marked = show(home, env, s.TAXES)
    assert (marked["lifecycle"], marked["done_at"]) == ("done", "2023-11-13T09:00:00+00:00")
    assert show(home, env, s.SHIP)["done_at"] == "2023-11-14T09:00:00+00:00"

    seed(s.SHIP, home, "status_change", {"lifecycle": "open"}, "2023-11-14T10:00:00+00:00")
    reopened = show(home, env, s.SHIP)
    assert reopened["lifecycle"] == "open" and "done_at" not in reopened


def test_stale_is_read_time_per_kind_and_follows_config(world):
    home, env = world
    flags = {t: show(home, env, t)["stale"] for t in s.TITLES}
    assert flags == {
        s.VENDOR: True,
        s.REGION: False,
        s.POSTGRES: False,
        s.SHIP: False,
        s.TAXES: False,
        s.DEC1: False,
        s.DEC8: False,
        s.INVOICE: False,
    }
    assert (
        show(home, env, s.VENDOR)["last_evidence"]
        == datetime.fromtimestamp(s.NOW - 28 * s.DAY - 3600, UTC).isoformat()
    )

    with (home / "config.toml").open("a") as cfg:
        cfg.write("stale_days_action_item = 100\nstale_days_open_question = 20\n")
    assert show(home, env, s.VENDOR)["stale"] is False
    assert show(home, env, s.REGION)["stale"] is True
    assert show(home, env, s.INVOICE)["stale"] is False


def test_stale_item_stays_stale_after_importing_the_librarian_echo_session(world, tmp_path):
    home, env = world
    assert show(home, env, s.VENDOR)["stale"] is True
    build(tmp_path / "fixtures", "session_librarian_echo")
    with (home / "config.toml").open("a") as cfg:
        cfg.write(f'claude_projects_dir = "{tmp_path / "fixtures" / "claude" / "projects"}"\n')
    run_import(home, env)
    assert show(home, env, s.VENDOR)["stale"] is True
    assert (
        show(home, env, s.VENDOR)["last_evidence"]
        == datetime.fromtimestamp(s.NOW - 28 * s.DAY - 3600, UTC).isoformat()
    )


@pytest.mark.parametrize(
    ("kind", "age_days", "stale_expected"),
    [
        ("action_item", 14, False),
        ("action_item", 14.01, True),
        ("blocker", 14, False),
        ("blocker", 15, True),
        ("open_question", 30, False),
        ("open_question", 31, True),
        ("decision", 3650, False),
        ("project", 3650, False),
    ],
)
def test_stale_thresholds_boundary(kind, age_days, stale_expected):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    last = now - timedelta(days=age_days)
    assert stale.is_stale(kind, "open", last, now, config.DEFAULTS) is stale_expected


@pytest.mark.parametrize("lifecycle", ["done", "dropped", "superseded"])
def test_finished_records_are_never_stale(lifecycle):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert (
        stale.is_stale("action_item", lifecycle, now - timedelta(days=99), now, config.DEFAULTS)
        is False
    )


def test_corrected_record_extraction_stops_producing_is_kept_and_flagged(world):
    home, env = world
    seed(s.INVOICE, home, "owner_change", {"person_id": person(home)})
    assert "no_longer_found" not in show(home, env, s.INVOICE)

    run_import(
        home, env
    )  # the second generation edits the message; extraction now finds nothing in it

    kept = show(home, env, s.INVOICE)
    assert kept["no_longer_found"] == "no longer found in sources"
    assert "no_longer_found" not in show(
        home, env, s.REGION
    )  # nobody corrected it: only flagged when a person did


def test_contradicting_records_show_each_other_with_evidence(world):
    home, env = world
    one, other = show(home, env, s.DEC1), show(home, env, s.DEC8)
    assert [c["title"] for c in one["contradictions"]] == [s.DEC8]
    assert [c["title"] for c in other["contradictions"]] == [s.DEC1]
    assert one["contradictions"][0]["evidence"][0]["quote"] == "Launch on Dec 8"
    assert other["contradictions"][0]["evidence"][0]["quote"] == "Launch on Dec 1"
    assert all(link["type"] != "contradicts" for link in one["links"])
