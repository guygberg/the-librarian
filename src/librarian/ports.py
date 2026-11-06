"""Engine ports: the three outside-world seams. Slack is read-only by construction."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class SlackSource(Protocol):
    def auth_info(self) -> dict[str, Any]: ...  # includes the workspace "url"

    def list_conversations(self) -> list[dict[str, Any]]: ...

    def list_users(self) -> list[dict[str, Any]]: ...

    def history(self, channel: str, cursor: str | None = None) -> dict[str, Any]:
        """One page (newest first); `response_metadata.next_cursor` is empty on the last."""
        ...

    def replies(self, channel: str, thread_ts: str) -> list[dict[str, Any]]: ...


@dataclass
class Token:
    text: str
    p: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    tokens: list[Token] = field(default_factory=list)


class Transcriber(Protocol):
    def detect_language(self, file: Path) -> str:
        """`he`, `en` or `mixed`, from the first 30 seconds."""
        ...

    def transcribe(self, file: Path, model: str, language: str) -> list[Segment]: ...


class Extractor(Protocol):
    def extract(self, unit_key: str, unit_text: str, candidates: list[dict[str, Any]]) -> str:
        """Schema-valid JSON text.

        Validation is the caller's job: this returns whatever the engine said.
        """
        ...


@dataclass
class Engines:
    slack: SlackSource
    transcriber: Transcriber
    extractor: Extractor
