"""Per-run call log under the Workspace folder: one JSON line per engine call."""

import json
from pathlib import Path

LOG_NAME = "engine-calls.jsonl"


class CallLog:
    def __init__(self, workspace_dir: Path):
        self.path = workspace_dir / LOG_NAME

    def record(self, engine: str, method: str, **args) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(
                json.dumps({"engine": engine, "method": method, "args": args}, sort_keys=True)
                + "\n"
            )

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines()]
