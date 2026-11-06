"""Locator: the text that names one Source item (and optionally a place inside it).

    <source>:<stable_id>[#<part>]

- source: `slack`, `session` or `drive`.
- stable_id: slack `<channel>/<ts>`, session `<session id>/<message id>`, drive `<file id>`.
- part: optional line (session, slack) or segment number (drive); never part of the item's identity.

Examples: `slack:C123/1700000000.000100`, `session:abc/m7#12`, `drive:1AbC#3`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Locator:
    source: str
    stable_id: str
    part: str | None = None

    def __str__(self) -> str:
        return f"{self.source}:{self.stable_id}" + (f"#{self.part}" if self.part else "")


def parse(text: str) -> Locator:
    source, sep, rest = text.partition(":")
    stable_id, _, part = rest.partition("#")
    if not (sep and source and stable_id):
        raise ValueError(f"not a locator: {text!r} (expected <source>:<stable_id>[#<part>])")
    return Locator(source, stable_id, part or None)
