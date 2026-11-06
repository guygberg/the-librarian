import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "slack"))
from test_fetch import make_env, run_import  # noqa: E402

from librarian import textsearch  # noqa: E402
from support.cli import run_librarian  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("הַפְּגִישָׁה", "הפגישה"),
        ("בית־ספר", "בית ספר"),
        ("צ׳ק", "צ'ק"),
        ("ראש הממשלה, מר״ם", 'ראש הממשלה, מר"ם'),
        ("Deploy", "deploy"),
    ],
)
def test_normalise(raw, normalised):
    assert textsearch.normalise(raw) == normalised


@pytest.mark.parametrize(
    ("content", "text"),
    [('{"text": "hello", "user": "U1"}', "hello"), ("plain words", "plain words"), ("[1, 2]", "[1, 2]")],
)
def test_index_text(content, text):
    assert textsearch.index_text(content) == text


def test_match_expression():
    assert textsearch.match_expression("   ") is None
    assert textsearch.match_expression("deploy") == '("deploy")'
    expression = textsearch.match_expression("פגישה")
    assert '"הפגישה"' in expression and '"ולפגישה"' in expression
    assert '"פגישה"' in textsearch.match_expression("הפגישה")


@pytest.fixture
def hebrew(tmp_path, home):
    env = make_env(tmp_path, home, "slack_hebrew")
    assert run_import(home, env)[0] == 0
    return home


def search(home, query, *extra):
    result = run_librarian([*extra, "search", query], home)
    return result.returncode, json.loads(result.stdout)


def snippets(answer):
    return [r["quote"] for r in answer["evidence"]]


def test_finds_slack_text_with_locator_source_and_freshness(hebrew):
    code, answer = search(hebrew, "deploy")
    assert code == 0
    [hit] = answer["evidence"]
    assert hit["quote"] == "Deploy the release tomorrow" and hit["role"] == "match"
    assert hit["source"] == "slack" and hit["locator"].startswith("slack:C001/")
    assert answer["freshness"]["last_import_finished_at"]


def test_no_match_is_an_empty_list_not_an_error(hebrew):
    code, answer = search(hebrew, "nonexistent")
    assert code == 0 and answer["evidence"] == [] and answer["records"] == []
    assert search(hebrew, "   ")[1]["evidence"] == []


def test_unmarked_query_finds_niqqud_text(hebrew):
    assert any("הַפְּגִישָׁה" in s for s in snippets(search(hebrew, "הפגישה")[1]))


def test_niqqud_query_finds_unmarked_text(hebrew):
    assert any("לפגישה" in s for s in snippets(search(hebrew, "לְפְגִישָׁה")[1]))


def test_base_word_finds_prefixed_forms(hebrew):
    found = snippets(search(hebrew, "פגישה")[1])
    assert len(found) == 2


def test_prefixed_query_finds_base_and_other_prefixes(hebrew):
    assert len(snippets(search(hebrew, "בפגישה")[1])) == 2


def test_maqaf_and_geresh_are_unified(hebrew):
    assert len(snippets(search(hebrew, "בית-ספר")[1])) == 1
    assert len(snippets(search(hebrew, "ספר")[1])) == 1
    assert len(snippets(search(hebrew, "צ'ק")[1])) == 1


def test_other_workspace_sees_nothing(hebrew, monkeypatch):
    monkeypatch.setenv("LIBRARIAN_HOME", str(hebrew))
    from librarian import db

    db.connect_rw("other").close()
    code, answer = search(hebrew, "deploy", "--workspace", "other")
    assert code == 0 and answer["evidence"] == []


def test_missing_database_is_the_schema_outdated_envelope(home):
    result = run_librarian(["search", "x"], home)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "schema_outdated"
