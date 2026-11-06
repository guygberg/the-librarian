import json
import sqlite3

import pytest

from fixtures.build import build
from fixtures.scenarios import people_aliases as p
from librarian.link import review
from support.cli import finish_tty, popen_librarian_tty, run_librarian


@pytest.fixture
def imported(tmp_path, home):
    fixtures = tmp_path / "fixtures"
    build(fixtures, "people_aliases")
    home.mkdir(parents=True)
    me_names = ", ".join(json.dumps(n, ensure_ascii=False) for n in p.ME_NAMES)
    (home / "config.toml").write_text(
        f'account_type = "team"\nusage_rules_confirmed = true\ndrive_dir = "{fixtures}"\n'
        f'claude_projects_dir = "{fixtures}/none"\nme_names = [{me_names}]\n'
    )
    workspace = home / "workspaces" / "work"
    workspace.mkdir(parents=True)
    (workspace / "channels.json").write_text(json.dumps({"picked": ["C001"]}))
    env = {
        "LIBRARIAN_ENGINES": "fake",
        "LIBRARIAN_FIXTURES": str(fixtures),
        "LIBRARIAN_NOW": str(p.NOW),
    }
    code, out = finish_tty(popen_librarian_tty(["import"], home, env))
    assert code == 0, out
    return home


def shown(home, title):
    conn = sqlite3.connect(next(home.rglob("*.db")))
    (record_id,) = conn.execute("SELECT id FROM records WHERE title = ?", (title,)).fetchone()
    out = run_librarian(["show", str(record_id)], home)
    assert out.returncode == 0, out.stdout
    return json.loads(out.stdout)


def test_slack_id_links_to_its_person_without_review(imported):
    record = shown(imported, "By id")
    assert (
        record["owner"] == "Dana Cohen"
        and "owner_is_me" not in record
        and "suggested" not in record
    )


def test_slack_id_missing_from_users_list_still_links(imported):
    assert shown(imported, "By id, not in the users list")["owner"] == "U099"


def test_name_matching_two_persons_is_only_suggested(imported):
    record = shown(imported, "By colliding name")
    assert "owner" not in record
    assert record["suggested"] == [
        {
            "kind": "unconfirmed_person",
            "mark": "unconfirmed person",
            "link": "owner",
            "raw_name": "Dana Cohen",
        }
    ]


def test_near_duplicate_name_never_auto_links(imported):
    record = shown(imported, "By near-duplicate name")
    assert "owner" not in record and record["suggested"][0]["raw_name"] == "Dana Cohn"


def test_first_person_recording_line_has_unknown_speaker_and_review_entry(imported):
    record = shown(imported, "By first person")
    assert record["owner"] == "unknown speaker"
    assert [(s["kind"], s["link"]) for s in record["suggested"]] == [("unknown_speaker", "owner")]


@pytest.mark.parametrize("title", ["By Hebrew me-name", "By login name"])
def test_me_names_and_login_are_flagged_as_own(imported, title):
    record = shown(imported, title)
    assert (
        record["owner"] == "Omer Katz"
        and record["owner_is_me"] is True
        and "suggested" not in record
    )


def test_review_list_data_holds_exactly_the_unlinked_names(imported):
    conn = sqlite3.connect(next(imported.rglob("*.db")))
    entries = review.open_entries(conn, "work")
    assert sorted((e["kind"], e["raw_name"]) for e in entries) == [
        ("unconfirmed_person", "Dana Cohen"),
        ("unconfirmed_person", "Dana Cohn"),
        ("unknown_speaker", None),
    ]
