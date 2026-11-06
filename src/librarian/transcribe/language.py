"""Which model and language a recording is transcribed with.

Precedence: a CLI override beats an explicit flag (config `recording_languages`), which beats detection from the
first 30 seconds. Hebrew and mixed recordings use the Hebrew model with language forced to `he`.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

HEBREW_MODEL = "ivrit-ai/whisper-large-v3-turbo-ct2"
ENGLISH_MODEL = "large-v3-turbo"
CHOICES = ("he", "en", "mixed")


@dataclass(frozen=True)
class Params:
    model: str
    language: str

    @property
    def key(self) -> str:
        """What the transcribe-once rule compares: same bytes with the same key are never transcribed again."""
        return f"{self.model}|{self.language}"


def for_choice(choice: str) -> Params:
    if choice not in CHOICES:
        raise ValueError(f"language must be one of {', '.join(CHOICES)}, got {choice!r}")
    return Params(ENGLISH_MODEL, "en") if choice == "en" else Params(HEBREW_MODEL, "he")


def parse_override(text: str) -> tuple[str, str]:
    """`<file-or-title>=<he|en|mixed>`."""
    target, _, choice = text.rpartition("=")
    if not target or choice not in CHOICES:
        raise ValueError(f"expected <file-or-title>=<{'|'.join(CHOICES)}>, got {text!r}")
    return target, choice


def lookup(table: Mapping[str, str], path: str, title: str) -> str | None:
    """The choice for a recording whose path, file name or title is a key of `table`."""
    for key in (path, PurePosixPath(path).name, title):
        if key in table:
            return table[key]
    return None


def choose(
    path: str, title: str, overrides: Mapping[str, str], flags: Mapping[str, str], detect: Callable[[], str]
) -> Params:
    return for_choice(lookup(overrides, path, title) or lookup(flags, path, title) or detect())
