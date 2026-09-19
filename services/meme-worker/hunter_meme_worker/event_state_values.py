"""The value objects of :mod:`hunter_meme_worker.event_state` — one photo of
the curve (:class:`CurvePoint`) and the creator's flow since the subscription
(:class:`CreatorFlow`) — moved here for the 350-line budget (T4.66); both are
re-exported by ``event_state`` under their old names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hunter_indicators.meme.fast import FastPoint

__all__ = ["CreatorFlow", "CurvePoint"]


@dataclass(frozen=True, slots=True)
class CurvePoint:
    """One photo of the curve with its two clocks, from whichever source."""

    observed_at: datetime
    received_at: datetime
    mcap_sol: Decimal | None
    real_sol: Decimal
    real_token: Decimal
    mayhem: bool | None
    slot: int | None = None
    source: str = "trade_event"

    def as_fast_point(self) -> FastPoint:
        return FastPoint(
            observed_at=self.observed_at,
            received_at=self.received_at,
            mcap_sol=self.mcap_sol,
            real_token_reserves=self.real_token,
            real_sol_reserves=self.real_sol,
            mayhem_enabled=self.mayhem,
        )


@dataclass(frozen=True, slots=True)
class CreatorFlow:
    """Σ of the creator's fills seen since ``since`` (lamports, counts)."""

    since: datetime
    bought_lamports: int
    sold_lamports: int
    buys: int
    sells: int
    last_sell_at: datetime | None
    covered_from_birth: bool
    """The subscription began within :data:`COVERAGE_GRACE_S` of
    ``first_seen_at``: a zero here is a zero the feed stated."""

    @property
    def sold_any(self) -> bool | None:
        if self.sells > 0:
            return True
        return False if self.covered_from_birth else None

    @property
    def net_seller(self) -> bool | None:
        """The plan's event-lane rule: ``True`` at the first creator sell."""
        return self.sold_any
