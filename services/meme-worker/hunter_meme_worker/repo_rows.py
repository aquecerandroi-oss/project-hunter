"""The row shapes ``repo.py`` writes — split out of it for the 350-line budget
(``infra/scripts/check_file_size.py``) when T4.2d gave ``meme_tokens`` its four
completion signals and the denominator's provenance. ``repo.py`` re-exports
them, so every caller still imports from there.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from typing import Any

NUL = "\x00"
_REQUIRED_TEXT = frozenset({"mint", "first_seen_source"})


def clean_text(value: str | None) -> str | None:
    """T4.47: PostgreSQL ``text`` cannot hold ``\\x00``, and pump.fun does emit
    it — ``"spaceX链游\\x00"`` arrived at 00:11:48Z on 17/09/2026 and every retry
    of the same frame raised ``CharacterNotInRepertoireError`` until the whole
    worker died (its 18th restart). The byte carries no meaning, so it is
    dropped; a string that was *only* NULs becomes ``None`` ("not observed"),
    the same answer ``discovery._identity`` gives an empty one."""
    if value is None or NUL not in value:
        return value
    return value.replace(NUL, "") or None


@dataclass(frozen=True, slots=True)
class TokenRow:
    """What one observation knows about a mint. Unknown stays ``None``.
    Every text field is NUL-free by construction (``clean_text``)."""

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
    bonding_curve_raw: str | None = None
    """T4.39: the create frame's own value, kept only when it disagreed with
    the derived PDA now stored in ``bonding_curve`` (a Mayhem sol-vault, R36).
    ``None`` = the frame's value was already correct."""
    initial_virtual_sol_reserves: Decimal | None = None
    initial_virtual_token_reserves: Decimal | None = None
    creator_initial_tokens: Decimal | None = None
    """T4.45 (``0048``): the creator's own buy inside the ``create`` transaction,
    in tokens - the base the executor compares his on-chain balance against.
    ``None`` = the frame did not carry it; ``0`` = he bought nothing."""
    creator_initial_sol: Decimal | None = None
    """What that buy cost him, in SOL. Audit beside the tokens."""
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
    # --- T4.26: the social identity pump.fun already carries ------------------
    twitter: str | None = None
    telegram: str | None = None
    website: str | None = None
    description: str | None = None
    twitter_kind: str | None = None
    twitter_post_id: int | None = None
    twitter_post_at: datetime | None = None
    social_observed_at: datetime | None = None
    social_source: str | None = None
    """Written once, together (``ddl/meme_social.py``); ``None`` = not read yet."""
    twitter_reuse_count: int | None = None
    twitter_reuse_observed_at: datetime | None = None
    """Mutable, like ``mayhem_state``: the indexer's count keeps moving after
    discovery (clones reusing the same handle)."""

    def __post_init__(self) -> None:
        # frozen + slots: the only door is object.__setattr__; ``mint`` and
        # ``first_seen_source`` are required, so a NUL-only value there stays
        # ``""`` and the schema refuses it loudly instead of writing NULL.
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, str) and NUL in value:
                cleaned = clean_text(value)
                if cleaned is None and f.name in _REQUIRED_TEXT:
                    cleaned = ""
                object.__setattr__(self, f.name, cleaned)


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


__all__ = ["GapRow", "SnapshotRow", "TokenRow", "clean_text"]
