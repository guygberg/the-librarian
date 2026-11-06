"""Text normalisation and query building for the full-text index. Pure functions, no database."""

import itertools
import json
import re
from collections.abc import Callable

_NIQQUD_AND_TAAMIM = re.compile("[֑-ֽֿ-ׇ]")  # U+05BE (maqaf) is handled separately
_MAQAF_AND_HYPHENS = re.compile("[־‐-―-]")
_TOKEN = re.compile(r"\w+")
_HEBREW_LETTER = re.compile("[א-ת]")

# Prefix grammar: optional ו, optional ש, optional one of ה ב ל מ כ.
_PREFIXES = sorted(
    {"".join(p) for p in itertools.product(["", "ו"], ["", "ש"], ["", *"הבלמכ"])} - {""}
)
MIN_STEM = 2


def normalise(text: str) -> str:
    text = _NIQQUD_AND_TAAMIM.sub("", text)
    text = _MAQAF_AND_HYPHENS.sub(" ", text)
    return text.replace("׳", "'").replace("״", '"').casefold()


def index_text(content: str) -> str:
    """The searchable text of a stored revision: a Slack message's `text`, else the content."""
    try:
        data = json.loads(content)
    except ValueError:
        return content
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return data["text"]
    return content


def _stems(token: str) -> set[str]:
    stems = {token}
    for prefix in _PREFIXES:
        if token.startswith(prefix) and len(token) - len(prefix) >= MIN_STEM:
            stems.add(token[len(prefix) :])
    return stems


def _variants(token: str) -> list[str]:
    if not _HEBREW_LETTER.match(token):
        return [token]
    return sorted(
        {form for stem in _stems(token) for form in (stem, *(p + stem for p in _PREFIXES))}
    )


def _query_groups(query: str) -> list[list[str]]:
    return [_variants(token) for token in _TOKEN.findall(normalise(query))]


def match_expression(query: str) -> str | None:
    """FTS5 MATCH expression: every query word must appear, each in any of its prefixed forms."""
    groups = ["(" + " OR ".join(f'"{v}"' for v in group) + ")" for group in _query_groups(query)]
    return " AND ".join(groups) or None


def matcher(query: str) -> Callable[[str], bool]:
    """The same matching as `match_expression`, for text held outside the full-text index.

    An empty query matches nothing.
    """
    groups = [set(group) for group in _query_groups(query)]

    def matches(text: str) -> bool:
        tokens = set(_TOKEN.findall(normalise(text)))
        return bool(groups) and all(group & tokens for group in groups)

    return matches
