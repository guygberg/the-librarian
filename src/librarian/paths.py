"""Where data lives: `$LIBRARIAN_HOME` or `data/` in the clone, then one folder per Workspace."""

import os
from pathlib import Path

DEFAULT_WORKSPACE = "work"


def data_home() -> Path:
    override = os.environ.get("LIBRARIAN_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def workspace_dir(workspace: str) -> Path:
    return data_home() / "workspaces" / workspace


def config_path() -> Path:
    return data_home() / "config.toml"
