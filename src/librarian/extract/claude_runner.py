"""The real Extractor: one headless `claude -p` call per unit, unit text on stdin.

The call is locked down (no tools, no MCP, no session kept, no telemetry) because it sends work text.
`--bare` is deliberately not used: it would skip the account login the Team/Enterprise gate relies on.
A unit is accepted only when the envelope says success and carries structured output; anything else
raises `ExtractionFailed` with the raw envelope so the run record can keep it.
"""

import json
import os
import re
import subprocess
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any

from librarian.extract import schema
from librarian.extract.runs import RunMeta

PROMPT = (
    "Extract work-memory Records from the Slack, Claude or recording text on stdin. "
    "Follow the JSON schema exactly. Quote Evidence verbatim from the text; return no Records when nothing qualifies."
)

# Environment that switches off everything not needed to answer.
QUIET_ENV = {
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_AUTOUPDATER": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}

_TRANSIENT = re.compile(r"overloaded|rate.?limit|\b429\b|\b529\b", re.IGNORECASE)


class ExtractionFailed(RuntimeError):
    def __init__(self, stage: str, error: str, envelope: str = ""):
        super().__init__(f"{stage}: {error}")
        self.stage, self.error, self.envelope = stage, error, envelope


class RawEnvelopeText(str):
    """The structured output text, remembering the whole envelope it came from for the run record."""

    raw: str


class Transient(Exception):
    pass


class ClaudeExtractor:
    def __init__(self, cfg: dict[str, Any]):
        self._bin = cfg["claude_bin"]
        self._model = cfg["claude_model"]
        self._pinned_version = cfg.get("claude_code_version")
        self._workers = min(4, max(1, int(cfg["claude_workers"])))
        self._max_turns = cfg["claude_max_turns"]
        self._budget = cfg["claude_max_budget_usd"]
        self._retries = cfg["claude_retries"]
        self._backoff = cfg["claude_backoff_seconds"]
        self._version: str | None = None

    @property
    def meta(self) -> RunMeta:
        return RunMeta(model=self._model, claude_code_version=self._claude_version(), prompt=PROMPT)

    def _claude_version(self) -> str:
        if self._version is None:
            try:
                out = subprocess.run([self._bin, "--version"], capture_output=True, text=True, check=True, timeout=30)
            except (OSError, subprocess.SubprocessError) as err:
                raise ExtractionFailed("version", f"could not run `{self._bin} --version`: {err}") from err
            self._version = out.stdout.strip()
            if self._pinned_version and self._pinned_version not in self._version:
                raise ExtractionFailed(
                    "version", f"claude is {self._version} but config pins claude_code_version {self._pinned_version}"
                )
        return self._version

    def argv(self) -> list[str]:
        return [
            self._bin, "-p", PROMPT,
            "--output-format", "json",
            "--json-schema", schema.schema_json(),
            "--tools", "",
            "--strict-mcp-config",
            "--safe-mode",
            "--no-session-persistence",
            "--max-turns", str(self._max_turns),
            "--max-budget-usd", str(self._budget),
            "--model", self._model,
        ]  # fmt: skip

    def extract(self, unit_key: str, unit_text: str, candidates: list[dict[str, Any]]) -> str:
        stdin = unit_text
        if candidates:
            stdin += "\n\nCandidate Records already stored:\n" + json.dumps(candidates, ensure_ascii=False)
        self._claude_version()  # fail before the first send, not after
        for attempt in range(self._retries + 1):
            try:
                return self._call(stdin)
            except Transient as err:
                if attempt == self._retries:
                    raise ExtractionFailed("call", f"still failing after {attempt + 1} tries: {err}") from err
                time.sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")

    def extract_stream(
        self, items: Iterable[tuple[str, str, list[dict[str, Any]]]]
    ) -> Iterator[tuple[str, str | Exception]]:
        """Run units on up to `workers` threads; yield each outcome as it finishes so the caller can store it at once."""
        pending = iter(items)
        with ThreadPoolExecutor(self._workers) as pool:
            running = {}
            while True:
                for key, text, candidates in pending:
                    running[pool.submit(self.extract, key, text, candidates)] = key
                    if len(running) >= self._workers:
                        break
                if not running:
                    return
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    key = running.pop(future)
                    yield key, future.exception() or future.result()

    def _call(self, stdin: str) -> str:
        try:
            proc = subprocess.run(
                self.argv(), input=stdin, capture_output=True, text=True, env={**os.environ, **QUIET_ENV}, timeout=900
            )
        except subprocess.TimeoutExpired as err:
            raise Transient("timed out") from err
        except OSError as err:
            raise ExtractionFailed("launch", f"could not run `{self._bin}`: {err}") from err
        out = proc.stdout
        try:
            envelope = json.loads(out)
        except ValueError:
            if _TRANSIENT.search(proc.stderr + out):
                raise Transient((proc.stderr or out).strip()[:200]) from None
            raise ExtractionFailed("envelope", f"not JSON (exit {proc.returncode}): {(proc.stderr or out)[:200]}", out) from None
        if not isinstance(envelope, dict):
            raise ExtractionFailed("envelope", "not a JSON object", out)
        subtype = envelope.get("subtype")
        if subtype != "success" or envelope.get("is_error"):
            message = str(envelope.get("result") or subtype)
            if _TRANSIENT.search(message) or envelope.get("api_error_status") in (429, 529):
                raise Transient(message[:200])
            raise ExtractionFailed("result", f"subtype {subtype}: {message[:200]}", out)
        structured = envelope.get("structured_output")
        if structured is None:
            raise ExtractionFailed("result", "success without structured_output", out)
        text = RawEnvelopeText(json.dumps(structured, ensure_ascii=False))
        text.raw = out
        return text
