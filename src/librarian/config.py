"""Config: an optional TOML file in the data folder, merged over defaults."""

import tomllib
from typing import Any

from librarian import paths

DEFAULTS: dict[str, Any] = {
    "import_staleness_days": 7,
}


def load() -> dict[str, Any]:
    path = paths.config_path()
    if not path.exists():
        return dict(DEFAULTS)
    with path.open("rb") as f:
        return {**DEFAULTS, **tomllib.load(f)}
