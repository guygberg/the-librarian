import json

import pytest
from support.cli import run_librarian
from support.recordings import engine_calls, make_env, run_import, search

from librarian.transcribe import language
from librarian.transcribe.confidence import uncertain_words

ONBOARDING = "Onboarding - 2026-10-20 10.00 GMT+03.00 - Recording"
HE = (language.HEBREW_MODEL, "he")
EN = (language.ENGLISH_MODEL, "en")


def last_transcribe(home):
    args = engine_calls(home, "transcribe")[-1]
    return args["model"], args["language"]


def show(home, query):
    [hit] = search(home, query)
    return json.loads(run_librarian(["show", hit["locator"]], home).stdout)


@pytest.mark.parametrize(
    "flags, cli, expected, detected",
    [
        ("", [], HE, True),  # detection: the fixture says mixed
        ('recording_languages = {"Onboarding" = "en"}\n', [], EN, False),  # explicit flag beats detection
        ('recording_languages = {"Onboarding" = "en"}\n', [f"--language={ONBOARDING}=he"], HE, False),  # override wins
        ("", ["--language=Onboarding=en"], EN, False),
    ],
)
def test_language_precedence_chooses_model_and_language(tmp_path, home, flags, cli, expected, detected):
    env, _ = make_env(tmp_path, home, "recording_uncertain_hebrew", flags)
    assert run_import(home, env, *cli)[0] == 0
    assert last_transcribe(home) == expected
    assert bool(engine_calls(home, "detect_language")) is detected
    content = json.loads(show(home, "Thursday")["revisions"][0]["content"])
    assert (content["model"], content["language"]) == expected


def test_new_override_retranscribes_and_unchanged_parameters_do_not(tmp_path, home):
    env, _ = make_env(tmp_path, home, "recording_uncertain_hebrew")
    run_import(home, env)
    run_import(home, env)
    assert len(engine_calls(home, "transcribe")) == 1
    run_import(home, env, "--language=Onboarding=en")
    assert len(engine_calls(home, "transcribe")) == 2
    run_import(home, env, "--language=Onboarding=en")
    assert len(engine_calls(home, "transcribe")) == 2


def test_bad_override_is_refused(tmp_path, home):
    env, _ = make_env(tmp_path, home, "recording_uncertain_hebrew")
    code, out = run_import(home, env, "--language=Onboarding=klingon")
    assert code == 2 and "expected" in out


@pytest.mark.parametrize(
    "setting, flagged",
    [("-1.0", True), ("-1.4", False), ("-1.5", False)],
)
def test_low_confidence_flag_follows_configured_threshold(tmp_path, home, setting, flagged):
    env, _ = make_env(tmp_path, home, "recording_uncertain_hebrew", f"low_confidence_avg_logprob = {setting}\n")
    run_import(home, env)
    # the mumble has avg_logprob -1.4: below -1.0, not below -1.4 or -1.5 (a boundary is not "below")
    item = show(home, "מממ")
    assert (item.get("confidence", {}).get("label") == "low confidence") is flagged
    assert "low confidence" not in json.dumps(show(home, "Thursday"))


def test_uncertain_word_has_character_span_and_follows_threshold(tmp_path, home):
    env, _ = make_env(tmp_path, home, "recording_uncertain_hebrew")
    run_import(home, env)
    [word] = show(home, "Thursday")["uncertain_words"]
    text = "ניפגש ביום Thursday בבוקר"
    assert (word["text"], word["start"], word["end"]) == ("Thursday", 11, 19)
    assert text[word["start"] : word["end"]] == "Thursday"
    run_import(home, env)  # unchanged; now lower the threshold below the word's 0.3
    (home / "config.toml").write_text((home / "config.toml").read_text() + "uncertain_word_p = 0.2\n")
    assert "uncertain_words" not in show(home, "Thursday")


def test_uncertain_words_skip_unmatched_tokens():
    segment = {"text": "a b", "tokens": [{"text": "zzz", "p": 0.1}, {"text": "b", "p": 0.1}]}
    assert uncertain_words(segment, {"uncertain_word_p": 0.5}) == [{"text": "b", "p": 0.1, "start": 2, "end": 3}]


def test_parse_override_rejects_unknown_language():
    assert language.parse_override("Atlas=he") == ("Atlas", "he")
    with pytest.raises(ValueError):
        language.parse_override("Atlas")
