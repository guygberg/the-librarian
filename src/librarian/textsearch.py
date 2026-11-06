"""Text normalisation and query building for the full-text index. Pure functions, no database."""

import itertools
import json
import re

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
    """The searchable text of a stored revision: a Slack message's `text`, otherwise the content itself."""
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
    return sorted({form for stem in _stems(token) for form in (stem, *(p + stem for p in _PREFIXES))})


def match_expression(query: str) -> str | None:
    """FTS5 MATCH expression: every query word must appear, each in any of its prefixed forms."""
    groups = [
        "(" + " OR ".join(f'"{v}"' for v in _variants(token)) + ")"
        for token in _TOKEN.findall(normalise(query))
    ]
    return " AND ".join(groups) or None
