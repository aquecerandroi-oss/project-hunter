"""The H-038 scheduled-signal contract — buy **or** sell, no target, time exit.

Its own contract on purpose (plan ``docs/plans/MERCADO-TRADICIONAL.md`` §1.6): the Lab's
``hunter_core.strategies.base.Decision`` is LONG-only and demands ``target1`` with
``stop < reference < target``; forcing H-038 into it would mean inventing a target or
turning a sell into a buy. Integration with the ``Strategy`` protocol waits for an explicit
compatibility design (W0-2).

Every instant is a timezone-aware ``datetime`` normalised to UTC here; BRT is a display
concern of the caller. Prices and index values are ``Decimal``. Nothing here reads a clock
or does IO — ``decision_at`` travels inside :class:`IndexReadings`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Context, Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class NoTradeReason(StrEnum):
    """Why a session produced no signal. Each one is counted and published (plan §1.2)."""

    SHORTENED_SESSION = "shortened_session"
    WIN_EXPIRY_DAY = "win_expiry_day"
    KNOWN_IMPEDIMENT = "known_impediment"
    READING_MISSING = "reading_missing"
    PREVIOUS_CLOSE_NOT_PREVIOUS_SESSION = "previous_close_not_previous_session"
    READING_NOT_AT_SIGNAL_TIME = "reading_not_at_signal_time"
    RECEIVED_BEFORE_EVENT = "received_before_event"
    NOT_YET_RECEIVED = "not_yet_received"
    RECEIVED_AFTER_DEADLINE = "received_after_deadline"
    ZERO_RETURN = "zero_return"


SESSION_EXCLUSIONS = frozenset(
    {
        NoTradeReason.SHORTENED_SESSION,
        NoTradeReason.WIN_EXPIRY_DAY,
        NoTradeReason.KNOWN_IMPEDIMENT,
    }
)
"""The reasons decided from the calendar before any reading — the only ones a session carries."""


_EXACT = Context(prec=34)
"""Private arithmetic context: prices of ~1e5 with a 3-decimal fraction are exact in it."""


def utc(value: datetime, name: str) -> datetime:
    """``value`` in UTC; a naive ``datetime`` is refused, never assumed."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Contract data (tick, R$ per point) — passed in as data, never a constant in the rule."""

    root: str
    tick_size: Decimal
    point_value_brl: Decimal

    def __post_init__(self) -> None:
        if self.tick_size <= 0 or self.point_value_brl <= 0:
            raise ValueError("tick_size and point_value_brl must be positive")


def stop_level(
    entry_price: Decimal, side: Side, fraction: Decimal, spec: InstrumentSpec
) -> Decimal:
    """Catastrophic stop ``fraction`` away from ``entry_price``, rounded to tick **by side**.

    Bought: below the entry, rounded **down**; sold: above, rounded **up**. The rounding never
    brings the stop closer than the nominal fraction (plan §1.2, step 3). Computed in its own
    34-digit context, so a caller's low-precision context cannot move the level.
    """
    tick = spec.tick_size
    with localcontext(_EXACT):
        if entry_price <= 0 or entry_price % tick != 0:
            raise ValueError(f"entry price {entry_price} is not a positive multiple of tick {tick}")
        if side is Side.BUY:
            raw, rounding = entry_price * (1 - fraction), ROUND_FLOOR
        else:
            raw, rounding = entry_price * (1 + fraction), ROUND_CEILING
        return (raw / tick).to_integral_value(rounding=rounding) * tick


@dataclass(frozen=True, slots=True)
class IndexReading:
    """One Ibovespa number: the instant it refers to, the instant we got it, and from where.

    ``event_at`` is the end of a **final** bar (or the official close). The module can only
    check the instant; not passing a forming bar's value is the caller's duty (the manual
    reading is taken from the chart history after 10:30, never the live quote).
    """

    value: Decimal
    event_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.value.is_finite() or self.value <= 0:
            raise ValueError(f"index value must be a positive finite Decimal, got {self.value!r}")
        if not self.source.strip():
            raise ValueError("an index reading needs a source")
        object.__setattr__(self, "event_at", utc(self.event_at, "event_at"))
        object.__setattr__(self, "received_at", utc(self.received_at, "received_at"))


@dataclass(frozen=True, slots=True)
class IndexReadings:
    """The two numbers H-038 needs, plus the explicit instant of the decision."""

    previous_close: IndexReading
    first_half_hour: IndexReading | None
    decision_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_at", utc(self.decision_at, "decision_at"))


@dataclass(frozen=True, slots=True)
class SessionTimes:
    """One B3 session: O (cash-market open), C (end of the closing call), previous C."""

    trading_date: date
    open_at: datetime
    close_at: datetime
    previous_close_at: datetime
    exclusions: tuple[NoTradeReason, ...] = ()

    def __post_init__(self) -> None:
        for name in ("open_at", "close_at", "previous_close_at"):
            object.__setattr__(self, name, utc(getattr(self, name), name))
        if not self.previous_close_at < self.open_at < self.close_at:
            raise ValueError("session times out of order: previous close < open < close")
        stray = [r for r in self.exclusions if r not in SESSION_EXCLUSIONS]
        if stray:
            raise ValueError(f"not a session-level exclusion: {stray}")


@dataclass(frozen=True, slots=True)
class IntradayMomentumParams:
    """Frozen with ``version``; a changed number is a new version, never an edit."""

    version: str
    signal_offset: timedelta
    deadline_offset: timedelta
    entry_before_close: timedelta
    entry_tolerance: timedelta
    stop_fraction: Decimal

    def __post_init__(self) -> None:
        if not Decimal(0) < self.stop_fraction < Decimal(1):
            raise ValueError("stop_fraction must be in (0, 1)")
        if not timedelta(0) < self.signal_offset <= self.deadline_offset:
            raise ValueError("need 0 < signal_offset <= deadline_offset")
        if not timedelta(0) < self.entry_tolerance < self.entry_before_close:
            raise ValueError("need 0 < entry_tolerance < entry_before_close")


@dataclass(frozen=True, slots=True)
class Signal:
    """A scheduled order idea for a human: direction now, entry hours later, exit by time.

    ``stop_fraction`` is a fraction of the **entry fill**, which does not exist yet when the
    signal is published; :meth:`stop_price` turns it into a tick-rounded level for a price.
    """

    trading_date: date
    side: Side
    r1: Decimal
    entry_window_start: datetime
    entry_window_end: datetime
    exit_at: datetime
    stop_fraction: Decimal
    params_version: str
    reason: str
    supporting_features: Mapping[str, str]
    invalidations: tuple[str, ...]
    expected_holding: timedelta
    targets: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "supporting_features", MappingProxyType(dict(self.supporting_features))
        )

    def stop_price(self, entry_price: Decimal, spec: InstrumentSpec) -> Decimal:
        return stop_level(entry_price, self.side, self.stop_fraction, spec)


@dataclass(frozen=True, slots=True)
class NoTrade:
    trading_date: date
    reason: NoTradeReason
    r1: Decimal | None = None
