# ruff: noqa: F811  (fixtures imported from the sibling test module are used as arguments)
import pytest
from test_suggest_actions import DANA, WS, item, link, suggest
from test_suggest_stage import conn, tag, two_units  # noqa: F401  (fixtures)

from librarian.link import review, review_actions
from librarian.link import suggestion_actions as actions
from librarian.link.errors import Invalid
from librarian.server import app
from librarian.server.routes import review as route


def set_confidence(conn, sid, confidence, band, created="2025-10-09T00:00:00Z"):
    conn.execute(
        "UPDATE suggestions SET confidence = ?, band = ?, created_at = ? WHERE id = ?",
        (confidence, band, created, sid),
    )


@pytest.fixture
def graded(conn, two_units):
    ids = suggest(conn, tag(), item("i1", "Alpha"), item("i2", "Beta"), item("i3", "Gamma"))
    set_confidence(conn, ids["Rollout"], 95, "high")
    set_confidence(conn, ids["Alpha"], 60, "medium", "2025-10-10T00:00:00Z")
    set_confidence(conn, ids["Beta"], 60, "medium", "2025-10-11T00:00:00Z")
    set_confidence(conn, ids["Gamma"], 20, "low")
    return ids


def titles(out):
    return [r.get("title") for r in out["rows"]]


def test_default_order_is_confidence_then_newest_and_hides_rows_below_the_floor(conn, graded):
    out = review_actions.rows(conn, WS)
    assert titles(out) == ["Rollout", "Beta", "Alpha"]
    assert out["count"] == 3


def test_a_suggestion_row_carries_its_grade_reasoning_and_exact_source_identity(conn, graded):
    row = review_actions.rows(conn, WS)["rows"][0]
    assert (row["type"], row["id"], row["kind"], row["mark"]) == (
        "suggestion", graded["Rollout"], "new_tag", "suggested new tag",
    )  # fmt: skip
    assert (row["confidence"], row["band"], row["basis"], row["reasoning"]) == (
        95, "high", "stated", "Named.",
    )  # fmt: skip
    assert row["evidence"] == [
        {
            "source": "slack",
            "stable_id": "C1/1760000000.0",
            "revision": 1,
            "locator": "slack:C1/1760000000.0#1",
            "quote": DANA,
        }
    ]


def test_a_link_names_both_ends_existing_and_proposed(conn, two_units):
    suggest(conn, item(), link({"ref": "i1"}, {"type": "person", "id": 1}, "owner"))
    row = next(r for r in review_actions.rows(conn, WS)["rows"] if r["kind"] == "link")
    assert row["from"] == {"type": "new_item", "title": "Send rollout plan"}
    assert row["to"] == {"type": "person", "id": 1, "title": "Dana"}
    assert row["link_type"] == "owner"


def test_min_confidence_and_band_filter_and_can_reveal_hidden_rows(conn, graded):
    assert titles(review_actions.rows(conn, WS, "min_confidence=61")) == ["Rollout"]
    assert titles(review_actions.rows(conn, WS, "min_confidence=0")) == [
        "Rollout", "Beta", "Alpha", "Gamma",
    ]  # fmt: skip
    for band, expected in (("high", ["Rollout"]), ("medium", ["Beta", "Alpha"])):
        assert titles(review_actions.rows(conn, WS, f"band={band}")) == expected
    assert titles(review_actions.rows(conn, WS, "band=low")) == []  # still below the floor
    assert titles(review_actions.rows(conn, WS, "band=low&min_confidence=0")) == ["Gamma"]


def test_newest_sort(conn, graded):
    assert titles(review_actions.rows(conn, WS, "sort=newest")) == ["Beta", "Alpha", "Rollout"]


@pytest.mark.parametrize(
    "query",
    ["min_confidence=high", "min_confidence=101", "min_confidence=-1", "min_confidence=",
     "band=urgent", "sort=oldest", "band=high&band=low"],
)  # fmt: skip
def test_invalid_queries_are_refused(conn, query):
    with pytest.raises(Invalid) as refused:
        review_actions.rows(conn, WS, query)
    assert refused.value.status == 400
    req = app.Request(WS, "GET", "/api/review", query, {}, None)
    assert route.get_review(req)[0] == 400


def test_settled_suggestions_leave_the_answer_and_the_count(conn, graded):
    actions.reject(conn, WS, graded["Rollout"])
    out = review_actions.rows(conn, WS)
    assert titles(out) == ["Beta", "Alpha"] and out["count"] == 2


def test_existing_entries_stay_compatible_and_are_left_out_of_graded_filters(conn, graded):
    record_id = actions.accept(conn, WS, graded["Alpha"])["record_id"]
    review.add(conn, WS, review.UNCONFIRMED_PERSON, record_id, "owner", "Sam")
    out = review_actions.rows(conn, WS)
    first = out["rows"][0]
    assert (first["type"], first["kind"], first["raw_name"]) == (
        "entry",
        "unconfirmed_person",
        "Sam",
    )
    assert first["record"]["id"] == record_id
    assert [r["type"] for r in out["rows"]] == ["entry", "suggestion", "suggestion"]
    assert out["count"] == 3
    assert [r["type"] for r in review_actions.rows(conn, WS, "min_confidence=0")["rows"]] == [
        "suggestion"
    ] * 3
