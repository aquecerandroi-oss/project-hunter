"""The three gates of ``docs/RISK_ENGINE_MEME.md`` §12, as a file the process refuses without.

``ENABLE_MEME_LIVE_TRADING`` (§3.4) is a switch only the owner flips, and flipping
it with the gates red is **refused by the process**, not tolerated. The gates are
attested in ``meme_gates.json`` — a small, human-written state file, named by
``MEME_GATES_FILE`` — and validated here before any key is read:

.. code-block:: json

    {
      "schema": "hunter.meme_gates/v1",
      "gate_a_engineering": {"passed": true, "date": "2026-10-01", "evidence": ".claude/state/notes-T4.x.md"},
      "gate_b_evidence":    {"passed": true, "date": "2026-10-20", "evidence": "EXP-M1 report"},
      "gate_c_owner":       {"enabled": true, "date": "2026-10-21"},
      "signed_by": "everton",
      "signed_at": "2026-10-21",
      "valid_until": "2026-11-21"
    }

Every refusal is a :class:`MemeLiveTradingRefused` with a **named** reason, so the
boot log says *which* gate is red. Nothing here reads a secret, and the flag being
``false`` short-circuits: paper and devnet never need this file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

__all__ = [
    "ENV_GATES_FILE",
    "ENV_LIVE_FLAG",
    "GATES_SCHEMA",
    "MemeExecutionMode",
    "MemeGates",
    "MemeLiveTradingRefused",
    "load_execution_mode",
    "load_gates",
    "parse_flag",
]

ENV_LIVE_FLAG = "ENABLE_MEME_LIVE_TRADING"
ENV_GATES_FILE = "MEME_GATES_FILE"
GATES_SCHEMA = "hunter.meme_gates/v1"


class MemeLiveTradingRefused(RuntimeError):
    """The live flag on with a gate red: this process refuses to exist."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


def parse_flag(raw: str | None, default: bool = False) -> bool:
    """Same vocabulary as the execution-worker's ``_flag``: ``1/true/yes/on``."""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class MemeGates:
    engineering_date: date
    engineering_evidence: str
    evidence_date: date
    evidence_evidence: str
    owner_date: date
    signed_by: str
    signed_at: date
    valid_until: date


@dataclass(frozen=True, slots=True)
class MemeExecutionMode:
    """``live=False`` is paper/devnet: nothing in this package may send to mainnet."""

    live: bool
    gates: MemeGates | None


def _date(raw: Any, field: str) -> date:
    if not isinstance(raw, str):
        raise MemeLiveTradingRefused("gates_file_invalid", f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise MemeLiveTradingRefused("gates_file_invalid", f"{field}: {exc}") from exc


def _section(doc: Mapping[str, Any], key: str) -> dict[str, Any]:
    raw: Any = doc.get(key)
    if not isinstance(raw, dict):
        raise MemeLiveTradingRefused("gates_file_invalid", f"{key} must be an object")
    return cast(dict[str, Any], raw)


def load_gates(path: Path, *, today: date) -> MemeGates:
    """Read and validate ``meme_gates.json``; every failure is a named refusal."""
    if not path.is_file():
        raise MemeLiveTradingRefused("gates_file_missing", str(path))
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MemeLiveTradingRefused("gates_file_invalid", f"unreadable JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MemeLiveTradingRefused("gates_file_invalid", "top level must be an object")
    doc = cast(dict[str, Any], parsed)
    if doc.get("schema") != GATES_SCHEMA:
        raise MemeLiveTradingRefused("gates_schema_mismatch", str(doc.get("schema")))
    gate_a = _section(doc, "gate_a_engineering")
    gate_b = _section(doc, "gate_b_evidence")
    gate_c = _section(doc, "gate_c_owner")
    if gate_a.get("passed") is not True:
        raise MemeLiveTradingRefused("gate_a_engineering_not_passed")
    if gate_b.get("passed") is not True:
        raise MemeLiveTradingRefused("gate_b_evidence_not_passed")
    if gate_c.get("enabled") is not True:
        raise MemeLiveTradingRefused("gate_c_owner_not_enabled")
    signed_by = doc.get("signed_by")
    if not isinstance(signed_by, str) or not signed_by.strip():
        raise MemeLiveTradingRefused("gates_unsigned", "signed_by is empty")
    gates = MemeGates(
        engineering_date=_date(gate_a.get("date"), "gate_a_engineering.date"),
        engineering_evidence=str(gate_a.get("evidence", "")),
        evidence_date=_date(gate_b.get("date"), "gate_b_evidence.date"),
        evidence_evidence=str(gate_b.get("evidence", "")),
        owner_date=_date(gate_c.get("date"), "gate_c_owner.date"),
        signed_by=signed_by.strip(),
        signed_at=_date(doc.get("signed_at"), "signed_at"),
        valid_until=_date(doc.get("valid_until"), "valid_until"),
    )
    for name, when in (
        ("gate_a_engineering.date", gates.engineering_date),
        ("gate_b_evidence.date", gates.evidence_date),
        ("gate_c_owner.date", gates.owner_date),
        ("signed_at", gates.signed_at),
    ):
        if when > today:
            raise MemeLiveTradingRefused("gates_date_in_future", f"{name}={when.isoformat()}")
    if gates.valid_until < today:
        raise MemeLiveTradingRefused("gates_expired", gates.valid_until.isoformat())
    if not gates.engineering_evidence.strip() or not gates.evidence_evidence.strip():
        raise MemeLiveTradingRefused("gates_without_evidence")
    return gates


def load_execution_mode(env: Mapping[str, str], *, today: date) -> MemeExecutionMode:
    """Boot-time decision. Flag off ⇒ paper/devnet; flag on ⇒ the gates file must be valid."""
    if not parse_flag(env.get(ENV_LIVE_FLAG)):
        return MemeExecutionMode(live=False, gates=None)
    path = env.get(ENV_GATES_FILE, "").strip()
    if not path:
        raise MemeLiveTradingRefused(
            "gates_file_not_configured",
            f"{ENV_LIVE_FLAG} is true but {ENV_GATES_FILE} is empty",
        )
    return MemeExecutionMode(live=True, gates=load_gates(Path(path), today=today))
