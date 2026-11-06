"""The no-training gate.

Extraction sends work text to Claude, so it only runs on accounts whose terms exclude training.
"""

from dataclasses import dataclass
from typing import Any

ALLOWED_ACCOUNT_TYPES = ("team", "enterprise")
ACCOUNT_TYPES = ("free", "pro", "max", "team", "enterprise")


@dataclass(frozen=True)
class GateStatus:
    allowed: bool
    reason: str = ""
    fix: str = ""


def training_gate_status(config: dict[str, Any]) -> GateStatus:
    account = config.get("account_type")
    confirmed = config.get("usage_rules_confirmed")
    fix = (
        "run `librarian setup` and give a Team or Enterprise account "
        "that your work usage rules allow"
    )
    if not account or confirmed is None:
        return GateStatus(False, "work account type or usage-rules confirmation is not set", fix)
    if account not in ALLOWED_ACCOUNT_TYPES:
        return GateStatus(False, f"account type {account} may train on your data", fix)
    if not confirmed:
        return GateStatus(False, "work usage rules are not confirmed to allow this", fix)
    return GateStatus(True)
