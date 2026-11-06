"""Config: an optional TOML file in the data folder, merged over defaults."""

import json
import tomllib
from typing import Any

from librarian import paths

DEFAULTS: dict[str, Any] = {
    "import_staleness_days": 7,
    "low_confidence_avg_logprob": -1.0,
    "low_confidence_no_speech_prob": 0.6,
    "low_confidence_compression_ratio": 2.4,
    "uncertain_word_p": 0.5,
}


def _read_file() -> dict[str, Any]:
    path = paths.config_path()
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load() -> dict[str, Any]:
    return {**DEFAULTS, **_read_file()}


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"cannot write {value!r} to config")


def save(updates: dict[str, Any]) -> None:
    """Merge `updates` into the file's own keys (defaults are not written) and rewrite it."""
    merged = {**_read_file(), **updates}
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k} = {_toml_value(v)}\n" for k, v in merged.items()))
