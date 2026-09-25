"""Pure helpers of ``spot_desk_markets.py`` (T4.74-6): the row shape, the
mint validator and the ``--list`` table — no I/O, so the CLI script stays
under the 350-line budget and these rules are testable without a fake
connection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import obsidian_note_gate

__all__ = [
    "COMPONENT",
    "MIN_REASON_LENGTH",
    "MINT_MAX_LENGTH",
    "MINT_MIN_LENGTH",
    "MarketRow",
    "Refused",
    "format_table",
    "require_note",
    "require_reason",
    "validate_mint",
]

COMPONENT = "spot_desk"
MIN_REASON_LENGTH = 10
MINT_MIN_LENGTH, MINT_MAX_LENGTH = 32, 44
_BASE58_ALPHABET = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
_HUNDRED = Decimal(100)
_COST_QUANTUM = Decimal("0.001")


class Refused(Exception):
    """Raised before anything is written; ``str(refused)`` names the reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MarketRow:
    """One row of ``spot_desk_markets`` as ``--list``/the edits read it."""

    binance_symbol: str
    mint: str
    kind: str
    tier: str
    round_trip_cost_pct_at_seed: Decimal
    enabled: bool

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> MarketRow:
        return cls(
            binance_symbol=str(row["binance_symbol"]),
            mint=str(row["mint"]),
            kind=str(row["kind"]),
            tier=str(row["tier"]),
            round_trip_cost_pct_at_seed=Decimal(str(row["round_trip_cost_pct_at_seed"])),
            enabled=bool(row["enabled"]),
        )

    @property
    def mint8(self) -> str:
        return self.mint[:8]

    @property
    def cost_pct(self) -> Decimal:
        """The stored fraction (DATABASE.md §1) as a percentage, three decimals."""
        return (self.round_trip_cost_pct_at_seed * _HUNDRED).quantize(_COST_QUANTUM)


def require_reason(reason: str | None) -> str:
    """Every write needs a reason a human can read in a month (10+ chars)."""
    if reason is None or len(reason.strip()) < MIN_REASON_LENGTH:
        raise Refused("reason_required", f"--reason needs >= {MIN_REASON_LENGTH} chars")
    return reason.strip()


def require_note(
    note: str | None, target_groups: Sequence[Sequence[str]], *, repo_root: Path | None = None
) -> obsidian_note_gate.NoteProof:
    """``--enable``/``--disable``/``--set-mint --apply`` (T4.93, "Obsidian
    primeiro"): a Markdown note under ``obsidian/`` naming the market symbol,
    right before the one write each performs. Converts
    :class:`obsidian_note_gate.NoteRefused` into this module's own
    :class:`Refused` — same ``(reason, detail)`` shape, only the class the
    CLI catches differs."""
    try:
        return obsidian_note_gate.gate(
            note, target_groups, repo_root=repo_root or obsidian_note_gate.default_repo_root()
        )
    except obsidian_note_gate.NoteRefused as note_refused:
        raise Refused(note_refused.reason, str(note_refused).split(": ", 1)[1]) from note_refused


def validate_mint(mint: str) -> str:
    """Base58, 32-44 chars (design §2/§7) — never a network call, never a
    real base58-checksum decode: this only keeps a typo from ever reaching a
    ``spot_positions`` row; the executor's own read of the mint over RPC is
    what actually proves it exists."""
    if not (MINT_MIN_LENGTH <= len(mint) <= MINT_MAX_LENGTH) or any(
        c not in _BASE58_ALPHABET for c in mint
    ):
        raise Refused("invalid_mint", f"{mint!r} is not 32-44 base58 characters")
    return mint


def format_table(rows: list[MarketRow]) -> str:
    header = f"{'symbol':<14}{'mint8':<10}{'kind':<16}{'tier':<6}{'cost %':>8}  enabled"
    lines = [header]
    for row in rows:
        lines.append(
            f"{row.binance_symbol:<14}{row.mint8:<10}{row.kind:<16}{row.tier:<6}"
            f"{format(row.cost_pct, 'f'):>8}  {'yes' if row.enabled else 'no'}"
        )
    return "\n".join(lines)
