"""Evidence time and Stale. Stale is computed at read time and never stored; it never means done."""

from datetime import UTC, datetime
from typing import Any

from librarian import locator

DAY = 86_400
UNFINISHED = ("open", "pending", "suspended")


def evidence_time(loc: str, retrieved_at: str) -> datetime:
    """The source timestamp of a piece of Evidence. Only Slack carries it in the locator; other sources
    fall back to when the Evidence was retrieved."""
    parsed = locator.parse(loc)
    if parsed.source == "slack":
        return datetime.fromtimestamp(float(parsed.stable_id.rpartition("/")[2]), UTC)
    return datetime.fromisoformat(retrieved_at)


def is_stale(kind: str, lifecycle: str, last_evidence: datetime | None, now: datetime, cfg: dict[str, Any]) -> bool:
    days = cfg.get(f"stale_days_{kind}")
    if days is None or last_evidence is None or lifecycle not in UNFINISHED:
        return False
    return (now - last_evidence).total_seconds() > days * DAY
