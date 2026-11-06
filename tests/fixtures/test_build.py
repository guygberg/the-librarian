import json
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).with_name("build.py")


def run_build(*args):
    return subprocess.run([sys.executable, str(BUILD), *args], capture_output=True, text=True)


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def load(path: Path):
    return json.loads(path.read_text())


def test_cli_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_build(str(a)).returncode == 0
    assert run_build(str(b)).returncode == 0
    assert snapshot(a) == snapshot(b)


def test_base_has_slack_replay_shapes(fixtures_dir):
    slack = fixtures_dir / "slack"
    assert load(slack / "auth.test.json")["url"].startswith("https://")
    kinds = {k for c in load(slack / "conversations.list.json")["channels"] for k in c if k.startswith("is_")}
    assert {"is_channel", "is_group", "is_im", "is_mpim"} <= kinds
    assert all("num_members" in c for c in load(slack / "conversations.list.json")["channels"])
    assert load(slack / "users.list.json")["members"]

    first = load(slack / "history/C001/page-0.json")
    assert len(first["messages"]) == 200
    assert first["response_metadata"]["next_cursor"]
    assert load(slack / "history/C001/page-1.json")["response_metadata"]["next_cursor"] == ""
    msg = first["messages"][0]
    assert {"ts", "user", "text"} <= msg.keys()
    assert not any("permalink" in m for p in slack.glob("history/*/*.json") for m in load(p)["messages"])
    messages = [m for p in slack.glob("history/*/*.json") for m in load(p)["messages"]]
    assert any("thread_ts" in m for m in messages)
    assert any("files" in m for r in slack.glob("replies/*/*.json") for m in load(r)["messages"])
    assert list(slack.glob("replies/*/*.json"))
    picked = set(load(slack / "picked.json")["picked"])
    all_ids = {c["id"] for c in load(slack / "conversations.list.json")["channels"]}
    assert picked and picked < all_ids


def test_base_has_session_shapes(fixtures_dir):
    files = list((fixtures_dir / "claude/projects").glob("*/*.jsonl"))
    assert len({p.parent for p in files}) >= 2
    lines = [json.loads(l) for p in files for l in p.read_text().splitlines()]
    assert all({"timestamp", "message"} <= l.keys() and "role" in l["message"] for l in lines)
    blocks = [b for l in lines if isinstance(l["message"]["content"], list) for b in l["message"]["content"]]
    assert {"tool_use", "tool_result"} <= {b["type"] for b in blocks}


def test_base_has_recording_shapes(fixtures_dir):
    name_re = re.compile(r".+ - \d{4}-\d{2}-\d{2} \d{2}\.\d{2} .+ - Recording")
    drive = list((fixtures_dir / "My Drive/Google Meet").glob("*/*"))
    flat = list((fixtures_dir / "Meet Recordings").iterdir())
    for group in (drive, flat):
        placeholders = [p for p in group if not p.name.endswith(".transcript.json")]
        assert placeholders
        for p in placeholders:
            assert name_re.fullmatch(p.name)  # ends in "Recording": no media extension
            seg = load(p.with_name(p.name + ".transcript.json"))["segments"][0]
            assert {"start", "end", "text", "avg_logprob", "no_speech_prob", "compression_ratio"} <= seg.keys()
            assert {"text", "p"} <= seg["tokens"][0].keys()


def test_base_has_two_sources_about_one_project(fixtures_dir):
    hits = [
        p
        for p in fixtures_dir.rglob("*")
        if p.is_file() and "Atlas" in p.read_text(errors="ignore") + p.name
    ]
    roots = {p.relative_to(fixtures_dir).parts[0] for p in hits}
    assert {"slack", "claude", "My Drive"} <= roots


def test_hebrew_is_real_with_niqqud(fixtures_dir):
    text = "".join(p.read_text() for p in fixtures_dir.rglob("*.json") if p.is_file())
    assert re.search(r"[א-ת]", text)
    assert re.search(r"[ְ-ׇ]", text)  # niqqud points
    assert "\\u05" not in text  # stored as real characters, not escapes


SPEC_FIXTURE_SET = [
    "cross-source project", "date disagreement", "uncertain Hebrew passage", "unnamed first-person speech",
    "deleted Slack message", "edited Slack message", "ambiguous project name", "stale item", "ownerless item",
    "failing extractor", "partial file", "Slack history older than 30 days",
    "replayed conversation list", "project with no recording", "prompt-injection message",
]


def test_every_item_of_the_spec_fixture_set_has_a_scenario():
    from fixtures.build import MANIFEST, discover

    missing = [item for item in SPEC_FIXTURE_SET if item not in MANIFEST]
    assert not missing, f"no scenario for: {missing}"
    assert not [s for s in MANIFEST.values() if s not in discover()]


def test_ui_scenarios_build_under_their_hyphenated_names(tmp_path):
    for name in ("payments-cutover", "onboarding-hebrew"):
        assert run_build(str(tmp_path / name), "--scenario", name).returncode == 0
        assert snapshot(tmp_path / name)


def test_scenario_discovery_and_unknown_name(tmp_path):
    scenarios = tmp_path / "scn"
    scenarios.mkdir()
    (scenarios / "tiny.py").write_text(
        "def build(target):\n    (target / 'marker.txt').write_text('hi')\n"
    )
    out = tmp_path / "out"
    ok = run_build(str(out), "--scenario", "tiny", "--scenarios-dir", str(scenarios))
    assert ok.returncode == 0 and (out / "marker.txt").read_text() == "hi"

    bad = run_build(str(tmp_path / "out2"), "--scenario", "nope", "--scenarios-dir", str(scenarios))
    assert bad.returncode != 0 and "nope" in bad.stderr
