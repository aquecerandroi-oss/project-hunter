"""The row shapes ``repo.py`` writes — split out of it for the 350-line budget
(``infra/scripts/check_file_size.py``) when T4.2d gave ``meme_tokens`` its four
completion signals and the denominator's provenance. ``repo.py`` re-exports
them, so every caller still imports from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenRow:
    """What one observation knows about a mint. Unknown stays ``None``."""

    mint: str
    first_seen_source: str
    first_seen_at: datetime
    last_seen_at: datetime
    name: str | None = None
    symbol: str | None = None
    uri: str | None = None
    creator: str | None = None
    created_at: datetime | None = None
    bonding_curve: str | None = None
    initial_virtual_sol_reserves: Decimal | None = None
    initial_virtual_token_reserves: Decimal | None = None
    initial_real_token_reserves: Decimal | None = None
    progress_denominator_source: str | None = None
    """``observed_virgin`` | ``global_params`` beside the denominator; ``None``
    with it (``graduation.py``). The pair is written once, together."""
    total_supply: Decimal | None = None
    pool: str | None = None
    mayhem_enabled: bool | None = None
    mayhem_mode: str | None = None
    mayhem_state: str | None = None
    completed_at: datetime | None = None
    """The reducer's answer for *this* observation (``graduation.earliest_completion``);
    the database keeps the earliest across observations (``LEAST``)."""
    rest_complete_seen_at: datetime | None = None
    curve_filled_seen_at: datetime | None = None
    graduated_board_seen_at: datetime | None = None
    pool_created_at: datetime | None = None
    pool_created_source: str | None = None
    migrated_at: datetime | None = None
    migrated_pool: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    """One curve observation. ``mcap_sol`` is absent on purpose: the database
    generates it, so no producer can write a market cap that disagrees with the
    reserves beside it."""

    observed_at: datetime
    mint: str
    source: str
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_sol_reserves: Decimal
    real_token_reserves: Decimal
    total_supply: Decimal
    complete: bool
    slot: int | None = None
    commitment: str | None = None
    mayhem_enabled: bool | None = None
    mayhem_state: str | None = None
    mayhem_mode: str | None = None


@dataclass(frozen=True, slots=True)
class GapRow:
    """A window the radar was not watching. ``mint`` is ``None`` for a whole-stream
    hole, because naming one mint would understate it."""

    stream: str
    gap_start: datetime
    gap_end: datetime
    reason: str
    mint: str | None = None
    generation: int | None = None
    detail: dict[str, Any] | None = None


__all__ = ["GapRow", "SnapshotRow", "TokenRow"]
