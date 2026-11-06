"""A mixed Hebrew/English recording: one doubtful word ("Thursday") and one low-confidence segment.

The full `onboarding-hebrew` scenario reuses `segments`.
"""

from fixtures import formats as f

NAME = "Onboarding - 2026-10-20 10.00 GMT+03.00 - Recording"
UNCERTAIN_TEXT = "ניפגש ביום Thursday בבוקר"
MUMBLE_TEXT = "מממ לא ברור"


def segments(start: float = 0.0) -> list[dict]:
    """The doubtful-word segment at `start` seconds, then the mumble right after it."""
    clear = {"start": start, "end": start + 5.0, "text": UNCERTAIN_TEXT, "avg_logprob": -0.3, "no_speech_prob": 0.02,
             "compression_ratio": 1.2, "tokens": [{"text": w, "p": 0.9} for w in UNCERTAIN_TEXT.split()]}
    clear["tokens"][2]["p"] = 0.3
    mumble = {"start": start + 5.0, "end": start + 8.0, "text": MUMBLE_TEXT, "avg_logprob": -1.4,
              "no_speech_prob": 0.1, "compression_ratio": 1.5,
              "tokens": [{"text": w, "p": 0.9} for w in MUMBLE_TEXT.split()]}
    return [clear, mumble]


def build(target):
    f.write_recording(target / "Meet Recordings", NAME, segments(), detected_language="mixed")
