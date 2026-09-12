"""The two value objects of the tracked set — split out of ``tracker.py`` in
T4.16b for the 350-line budget, re-exported there so nothing that imported
them from ``hunter_meme_worker.tracker`` has to move.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

__all__ = ["ACTIVE_MAYHEM_STATES", "PollPlan", "TrackedMint"]

ACTIVE_MAYHEM_STATES = frozenset({"active", "paused"})
"""``paused`` means liquidity is insufficient right now, not that the agent is
done (A4.1b §2) — so it keeps the mint in the set."""


@dataclass(frozen=True, slots=True)
class TrackedMint:
    """One mint the collector is watching, with everything the poller needs."""

    mint: str
    first_seen_at: datetime
    created_at: datetime | None = None
    creator: str | None = None
    bonding_curve: str | None = None
    mayhem_state: str | None = None
    initial_real_token_reserves: Decimal | None = None
    last_polled_at: datetime | None = None
    last_rest_polled_at: datetime | None = None
    """The last successful ``pumpfun_rest`` read (T4.2f): with the chain
    photographing the curve every minute, this is what says whether the mirror
    has ever told us the site's agent state of this mint, and when."""
    mcap_sol: Decimal | None = None
    complete: bool = False
    migrated: bool = False
    final_read_pending: bool = False
    """The curve finished (or left for PumpSwap) and no reading of the finished
    state has been persisted yet: one more poll, then eviction."""
    quote_unsupported: bool = False
    board: str | None = None
    """The site board that last listed the mint (``new`` / ``graduating``), a
    priority hint — never a claim about the curve."""

    @property
    def age_anchor(self) -> datetime:
        """``created_at`` when we know it, else when we first saw the mint.

        Never a fabricated creation time: a mint discovered by its *migration*
        genuinely has no creation time (the PumpPortal migration frame carries
        none), and ranking it by ``first_seen_at`` says "as old as our knowledge
        of it" instead of claiming it was born when we noticed it.
        """
        return self.created_at or self.first_seen_at

    @property
    def finished(self) -> bool:
        return self.complete or self.migrated

    def is_trackable(self, now: datetime, window: timedelta) -> bool:
        if self.quote_unsupported:
            return False
        if self.finished:
            return self.final_read_pending
        if self.mayhem_state in ACTIVE_MAYHEM_STATES:
            return True
        return now - self.age_anchor <= window


@dataclass(frozen=True, slots=True)
class PollPlan:
    """What this cycle polls, and what it could not reach."""

    selected: tuple[str, ...]
    skipped: tuple[str, ...]

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)
