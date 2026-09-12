"""Row shapes the Lab repositories hand to the loop, and the one converter
they share (a ``meme_curve_snapshots`` row -> :class:`~.lab_models.Snapshot`).

Split from ``lab_repo.py`` so the proposal side and the bet side of the
repository can each stay under the 350-line budget without importing each
other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hunter_indicators.meme.curve import CurveReserves
from hunter_meme_worker.lab_models import BetState, Snapshot

__all__ = ["ApprovedProposal", "CommandRow", "OpenBet", "snapshot_from_row"]


@dataclass(frozen=True, slots=True)
class ApprovedProposal:
    id: str
    mint: str
    rule_set_id: str
    decision: dict[str, Any]
    decided_at: datetime
    migrated: bool


@dataclass(frozen=True, slots=True)
class OpenBet:
    state: BetState
    migrated_at: datetime | None
    """``meme_tokens.migrated_at`` — compared per snapshot, never read as "now"."""
    completed_at: datetime | None
    creator_net_seller: bool | None


@dataclass(frozen=True, slots=True)
class CommandRow:
    id: str
    bet_id: str | None
    proposal_id: str | None
    command: str
    issued_by: str
    issued_at: datetime


def snapshot_from_row(row: Mapping[Any, Any]) -> Snapshot:
    """A ``meme_curve_snapshots`` row (or the snapshot columns of a join) -> value."""
    return Snapshot(
        mint=str(row["mint"]),
        observed_at=row["observed_at"],
        source=str(row["source"]),
        reserves=CurveReserves(
            virtual_sol_reserves=row["virtual_sol_reserves"],
            virtual_token_reserves=row["virtual_token_reserves"],
            real_token_reserves=row["real_token_reserves"],
            initial_real_token_reserves=row.get("initial_real_token_reserves"),
            complete=bool(row["complete"]),
        ),
        real_sol_reserves=row["real_sol_reserves"],
        total_supply=row["total_supply"],
        complete=bool(row["complete"]),
        mcap_sol=row.get("snapshot_mcap_sol", row.get("mcap_sol")),
    )
