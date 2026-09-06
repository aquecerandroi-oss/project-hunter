"""``PortfolioState``: what the wallet is, at one instant, with nothing to fetch.

The engine never reads a clock, a database or a price feed, so everything the
limits are measured against arrives here already computed by the caller - and
everything that can be *derived* from those facts is derived here instead of
being passed in, so a caller cannot hand the engine an exposure that disagrees
with its own positions.

Three properties of the directive live in this module:

- **pending entries are exposure** (§4). ``total_exposure``, ``slots_used``,
  ``committed_planned_risk`` and the per-coin ceiling all count them, which is
  what stops two agents from opening the same 10 % at the same instant;
- **the peak of equity is monotonic** (§5) - :func:`advance_peak` is the only
  way it moves, and a state whose peak sits below its equity is refused as the
  bug it is;
- **the day is the Sao Paulo day** (§5), computed by
  :func:`sao_paulo_day_start_utc` from an instant the caller passes; the state
  stores the anchor and the model checks that it really is the anchor of
  ``as_of``, so a worker that started at 00:15 cannot quietly call that moment
  "the start of the day" and erase the loss taken since midnight.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.base import RiskModel
from hunter_risk.inputs import MarketIdentity

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
"""Named zone, not a fixed -03:00: Brazil has no DST today, and the day the rule
is reinstated the anchor has to move with it (directive analysis §6)."""

_ZERO = Decimal(0)


def sao_paulo_day_start_utc(now: datetime) -> datetime:
    """Start of the Sao Paulo day containing ``now``, expressed in UTC.

    Pure: the instant is an argument. A naive ``now`` is refused rather than
    assumed to be UTC - assuming it would shift the daily-loss window by three
    hours and reset the kill switch in the middle of the afternoon.
    """
    utc_now = ensure_utc(now)
    local = utc_now.astimezone(SAO_PAULO)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(utc_now.tzinfo)


def advance_peak(peak_equity: Decimal, equity: Decimal) -> Decimal:
    """The new historical peak. Never decreases - directive §5, "sem resets"."""
    return peak_equity if peak_equity >= equity else equity


class OpenPosition(RiskModel):
    """A position already in the market, marked at the same instant as the state."""

    position_id: uuid.UUID
    market: MarketIdentity
    qty: Decimal = Field(gt=0)
    """Base units held. On spot an exit can never be larger than this."""
    notional: Decimal = Field(gt=0)
    """Current marked notional in the quote currency."""
    planned_risk_quote: Decimal = Field(ge=0)
    """What this position still loses if its stop is hit, costs included."""
    beta_btc: Decimal | None = None
    """``None`` means *not validated*, never 0: an unknown beta counted as zero
    would remove the position from the aggregate exactly when it matters."""


class PendingEntry(RiskModel):
    """An approved entry that has not filled yet: it reserves slot, risk, exposure and cash."""

    market: MarketIdentity
    reserved_notional: Decimal = Field(gt=0)
    """What it commits to exposure and to the participation budget."""
    reserved_cash: Decimal = Field(gt=0)
    """What it commits to **cash**, fees included - the reservation's own number,
    not a re-estimate made with the next candidate's cost hypothesis. A candidate
    that declares zero costs must not be able to make a standing reservation
    cheaper than it is (Astra, review of this diff). Mirrors
    ``trade_proposals.reserved_cash``."""
    planned_risk_quote: Decimal = Field(ge=0)
    beta_btc: Decimal | None = None

    @model_validator(mode="after")
    def _cash_covers_the_notional(self) -> PendingEntry:
        if self.reserved_cash < self.reserved_notional:
            raise ValueError(
                f"reserved_cash {self.reserved_cash} is below reserved_notional "
                f"{self.reserved_notional}: on spot the cash a purchase holds is the notional "
                "plus its fees, never less"
            )
        return self


class PortfolioState(RiskModel):
    """The wallet at ``as_of``. Every aggregate below is derived, never supplied."""

    portfolio_id: uuid.UUID
    """Which wallet this is. :func:`hunter_risk.evaluate.evaluate` refuses a state
    whose id is not the proposal own: a proposal of A evaluated against the state
    of B would pass B checks and be stamped with A id."""
    as_of: datetime
    equity: Decimal = Field(gt=0)
    """Directive §5: total patrimony - cash plus open positions, costs included."""
    cash: Decimal = Field(ge=0)
    peak_equity: Decimal = Field(gt=0)
    day_start_equity: Decimal = Field(gt=0)
    day_start_utc: datetime
    open_positions: tuple[OpenPosition, ...] = ()
    pending_entries: tuple[PendingEntry, ...] = ()
    daily_realized_pnl: Decimal | None = None
    """Reporting only, and **never** the source of the day's loss (v2 §5). The
    loss is ``1 - equity / day_start_equity``; these three fields decompose it
    for the panel. ``None`` means "not reported", never zero - a decomposition
    that defaults to zero is how a wallet 2,5 % down reported ``daily_loss
    PASSED value=0`` (review of 2026-09-06, finding 1). **Gross of costs**:
    ``daily_costs`` is subtracted once, here."""
    daily_unrealized_pnl: Decimal | None = None
    daily_costs: Decimal | None = Field(default=None, ge=0)
    marks_complete: bool = True
    """False when any open position could not be marked with a fresh price, or when
    the daily anchor could not be rebuilt after a restart: the equity is then a
    guess, and a guess must not size an entry."""
    is_active: bool = True
    """``portfolios.status = active``. Passed in; the engine reads no database."""

    @field_validator("as_of", "day_start_utc", mode="after")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _consistent(self) -> PortfolioState:
        if self.peak_equity < self.equity:
            raise ValueError(
                "peak_equity is below equity: the peak is monotonic, advance it with "
                "advance_peak() before building the state"
            )
        expected = sao_paulo_day_start_utc(self.as_of)
        if self.day_start_utc != expected:
            raise ValueError(
                f"day_start_utc {self.day_start_utc.isoformat()} is not the Sao Paulo day of "
                f"as_of {self.as_of.isoformat()} (expected {expected.isoformat()})"
            )
        return self

    @property
    def daily_decomposition_gap(self) -> Decimal | None:
        """How far the reported decomposition sits from the equity's own movement.

        ``None`` when the three fields were not all reported. **It never refuses
        the state**, and that is a deliberate reversal: an exception here would
        make a wallet whose ledger is a rounding unit off impossible to build,
        and :func:`hunter_risk.evaluate.evaluate_exit` needs a built state - an
        accounting discrepancy would then block a protective exit, which the
        directive §3 forbids outright (Astra, review of this diff). The number is
        published so the reconciliation of T3.3 can act on it; nothing in this
        engine decides anything with it, because the loss that blocks the wallet
        is :attr:`daily_loss_pct`, derived from the equity.
        """
        parts = (self.daily_realized_pnl, self.daily_unrealized_pnl, self.daily_costs)
        if any(part is None for part in parts):
            return None
        realized, unrealized, costs = parts
        assert realized is not None and unrealized is not None and costs is not None
        return (realized + unrealized - costs) - (self.equity - self.day_start_equity)

    @property
    def daily_pnl(self) -> Decimal:
        """The day's result: the equity's own movement since the day start (v2 §5).

        Derived, not supplied: the loss that blocks the wallet is a fact about
        the patrimony, and a caller that forgot to fill the PnL fields must not
        be able to produce a day with no loss in it.
        """
        return self.equity - self.day_start_equity

    @property
    def daily_loss_pct(self) -> Decimal:
        """``max(0, 1 - equity / day_start_equity)`` - v2 §5. Never negative."""
        if self.equity >= self.day_start_equity:
            return _ZERO
        with localcontext(CONTEXT):
            return (self.day_start_equity - self.equity) / self.day_start_equity

    @property
    def drawdown_pct(self) -> Decimal:
        """Distance from the historical peak. Never negative."""
        if self.equity >= self.peak_equity:
            return _ZERO
        with localcontext(CONTEXT):
            return (self.peak_equity - self.equity) / self.peak_equity

    @property
    def total_exposure(self) -> Decimal:
        """Open notional plus reserved notional - directive §4."""
        open_notional = sum((p.notional for p in self.open_positions), _ZERO)
        return sum((e.reserved_notional for e in self.pending_entries), open_notional)

    @property
    def slots_used(self) -> int:
        """Positions **and** pending entries: five slots, not five fills."""
        return len(self.open_positions) + len(self.pending_entries)

    @property
    def committed_planned_risk(self) -> Decimal:
        """Planned loss already committed, open and pending - directive §2."""
        open_risk = sum((p.planned_risk_quote for p in self.open_positions), _ZERO)
        return sum((e.planned_risk_quote for e in self.pending_entries), open_risk)

    @property
    def assets_held(self) -> frozenset[str]:
        """Base assets with a position or a reservation (D3: never two on one coin)."""
        return frozenset(
            [p.market.base_asset for p in self.open_positions]
            + [e.market.base_asset for e in self.pending_entries]
        )

    def position_by_id(self, position_id: uuid.UUID) -> OpenPosition | None:
        """The open position an exit refers to, or ``None`` if the wallet has none."""
        return next((p for p in self.open_positions if p.position_id == position_id), None)

    def exposure_for_asset(self, base_asset: str) -> Decimal:
        """Exposure on one coin, open plus reserved, across markets."""
        held = sum(
            (p.notional for p in self.open_positions if p.market.base_asset == base_asset), _ZERO
        )
        return sum(
            (
                e.reserved_notional
                for e in self.pending_entries
                if e.market.base_asset == base_asset
            ),
            held,
        )

    @property
    def available_cash(self) -> Decimal:
        """Cash minus what the standing reservations already hold, fees included.

        Cash was the one ceiling that ignored the reservations, and the hole was
        arithmetical: 500 of cash with 400 already reserved authorised another
        499,5, so 900 was committed against 500 (review of 2026-09-06, finding
        4). Each reservation brings its **own** ``reserved_cash``: re-estimating
        it with the candidate's cost hypothesis would let a candidate that
        declares no costs shrink a commitment somebody else already made.
        """
        with localcontext(CONTEXT):
            reserved = sum((e.reserved_cash for e in self.pending_entries), _ZERO)
            return max(_ZERO, self.cash - reserved)

    def beta_exposure(self) -> Decimal | None:
        """``Sum |notional_i * beta_i|`` - directive §4, absolute value, not signed.

        ``None`` when any position or reservation lacks a validated beta: the
        aggregate is then unknown, and an unknown aggregate rejects (R-OPS-1)
        instead of being reported as a smaller number than it is.
        """
        total = _ZERO
        with localcontext(CONTEXT):
            for notional, beta in [
                *((p.notional, p.beta_btc) for p in self.open_positions),
                *((e.reserved_notional, e.beta_btc) for e in self.pending_entries),
            ]:
                if beta is None:
                    return None
                total += abs(notional * beta)
        return total

    def age_s(self, observed_at: datetime) -> Decimal:
        """Age of an observation at ``as_of``, in seconds; negative if it is ahead."""
        delta: timedelta = self.as_of - ensure_utc(observed_at)
        return Decimal(str(delta.total_seconds()))
