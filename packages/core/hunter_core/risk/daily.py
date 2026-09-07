"""The trading day in ``America/Sao_Paulo`` and the peak that never falls.

Pure by construction: every function here takes the persisted row, an equity
observation and the instant, and returns what should be written. No session, so
the rules are a table of cases (``tests/unit/test_risk_daily.py``) rather than
something only a container can answer.

**The rule that earns this module its own file.** The day's opening is a
*measurement of midnight*, not "whatever the equity was when we got round to
looking". The first draft adopted the current equity if the evaluation ran within
one sampling cadence of the turn, and Astra's review of this diff produced the
number that kills it: patrimony 20.000 at midnight, 19.500 thirty seconds later,
adopted as the opening — a 2,5 % daily loss reported as 0 %, with the 2 % block
never firing.

So the opening is the newest equity point observed **at or before** the turn
(:class:`EquityObservation`, supplied by the caller from the durable equity
curve), and nothing else is accepted. No point before the turn, or one too far
before it, means the reference is **unknown** — which the schema represents on
purpose (``equity_day_start`` and ``day_reference_observed_at`` are nullable
together, DATABASE.md §18.7). Unknown blocks new entries and preserves
protections; it never invents a number. The Postgres guard says the same thing
from its side: "a day reference above the curve invents the loss of the day.
Write the equity point first".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from hunter_core.domain.types import ensure_utc
from hunter_risk import sao_paulo_day_start_utc
from hunter_risk.exposure import SAO_PAULO

__all__ = [
    "DAY_OPENING_MAX_LAG_S",
    "DayReference",
    "DayReferenceReason",
    "EquityObservation",
    "PersistedRiskState",
    "next_peak",
    "resolve_day_reference",
]

DAY_OPENING_MAX_LAG_S = 60
"""How far **before** the turn the anchoring observation may have been taken.

The equity curve is written every minute (PIPELINE.md §8.5), so this is exactly
**one sample**: the opening is the last point of the curve before midnight, and
the residual approximation is one sampling period — the same honesty the peak
already declares about itself ("amostrado, com a cadência declarada", §5).

It was 300 s in the first version of this fix, and Astra's second round gave the
number that shrank it: last point 23:55 = 19.500, real patrimony at midnight
20.000, 19.500 again at 00:00:30 — a 2,5 % daily loss reported as zero. Five
minutes is not a measurement of midnight; one is an approximation whose size is
published (:attr:`DayReference.anchored_on`). Zero tolerance is not on offer,
because the curve is sampled and midnight is not one of its samples.

A wallet whose newest point before midnight is older than this was not being
marked at midnight, and its opening is genuinely unknown — the restart case §5
names, "sem conseguir reconstruí-la o estado fica indisponível".
"""


class DayReferenceReason(StrEnum):
    """Why the reference is what it is — published, never inferred by the reader."""

    CARRIED = "carried"
    """The day did not change and its opening was already persisted."""
    ROLLED = "rolled"
    """A new São Paulo day, anchored on the last equity observed before the turn."""
    ADOPTED = "adopted"
    """The day was known and its opening was not; this evaluation filled it in."""
    UNAVAILABLE_NO_OBSERVATION = "unavailable_no_observation_before_the_turn"
    """No equity point at or before midnight, so there is nothing to anchor on."""
    UNAVAILABLE_STALE_OBSERVATION = "unavailable_stale_observation"
    """The newest point before the turn is older than :data:`DAY_OPENING_MAX_LAG_S`.
    The wallet was not being marked at midnight; its opening is unknown, and a
    number from hours earlier is not a measurement of it."""


@dataclass(frozen=True, slots=True)
class EquityObservation:
    """One point of the durable equity curve, with the instant it was taken."""

    equity: Decimal
    observed_at: datetime
    cash: Decimal | None = None
    """Carried for the callers that rebuild a whole ``PortfolioState`` from a
    point of the curve. The day's anchor does not need it and leaves it ``None``
    rather than pretending the cash of midnight is known."""


@dataclass(frozen=True, slots=True)
class PersistedRiskState:
    """One ``portfolio_risk_state`` row, as read under the lock."""

    organization_id: uuid.UUID
    portfolio_id: uuid.UUID
    trading_day: date | None
    trading_day_timezone: str
    trading_day_start_utc: datetime | None
    equity_day_start: Decimal | None
    day_reference_observed_at: datetime | None
    peak_equity: Decimal
    peak_equity_at: datetime
    peak_sampling_interval_s: int


@dataclass(frozen=True, slots=True)
class DayReference:
    """What the row should say about the day after this evaluation."""

    trading_day: date
    day_start_utc: datetime
    equity_day_start: Decimal | None
    observed_at: datetime | None
    """The instant this reference was *evaluated* — DATABASE.md §18.7 defines the
    column that way, so a late evaluation stays visible. Where the number itself
    came from is :attr:`anchored_on`, and the two are deliberately different
    facts: evaluating at 03:17 does not make the equity of 03:17 the equity of
    midnight, and this pair is what makes that inspectable rather than assumed."""
    anchored_on: datetime | None
    """When the anchoring equity point was observed. Always at or before
    :attr:`day_start_utc` when the reference is available."""
    rolled: bool
    """True when this evaluation is the first of a new São Paulo day. It is the
    only moment a WARNING may clear itself (RISK_ENGINE.md §5)."""
    writes: bool
    """Whether the row needs an ``UPDATE``. False is the common case: within a
    day the persisted opening is authoritative and is never rewritten."""
    reason: DayReferenceReason

    @property
    def available(self) -> bool:
        """Whether the day's loss is measurable at all."""
        return self.equity_day_start is not None


def resolve_day_reference(
    row: PersistedRiskState, *, opening: EquityObservation | None, now: datetime
) -> DayReference:
    """The daily reference for ``now``, given what is already persisted.

    ``opening`` is the newest equity point the caller found **at or before** the
    São Paulo turn. It is only ever *offered*: an observation after the turn, or
    one older than :data:`DAY_OPENING_MAX_LAG_S`, is refused, and the reference
    stays unknown rather than becoming a number nobody measured at midnight.
    """
    instant = ensure_utc(now)
    day_start = sao_paulo_day_start_utc(instant)
    trading_day = day_start.astimezone(SAO_PAULO).date()
    # The date alone is not the anchor: the resolved instant is, so a row whose
    # ``trading_day_start_utc`` no longer matches the zone's answer is rewritten
    # rather than trusted (DATABASE.md §18.7 declines a CHECK for the same reason).
    same_day = row.trading_day == trading_day and row.trading_day_start_utc == day_start

    if same_day and row.equity_day_start is not None:
        return DayReference(
            trading_day=trading_day,
            day_start_utc=day_start,
            equity_day_start=row.equity_day_start,
            observed_at=row.day_reference_observed_at,
            anchored_on=None,
            rolled=False,
            writes=False,
            reason=DayReferenceReason.CARRIED,
        )

    anchor = _usable(opening, day_start)
    if anchor is None:
        reason = (
            DayReferenceReason.UNAVAILABLE_NO_OBSERVATION
            if opening is None or opening.observed_at > day_start
            else DayReferenceReason.UNAVAILABLE_STALE_OBSERVATION
        )
        return DayReference(
            trading_day=trading_day,
            day_start_utc=day_start,
            equity_day_start=None,
            observed_at=None,
            anchored_on=None,
            rolled=not same_day,
            # The new day is recorded even with no opening to record: the row then
            # says "this is today, and today's reference is unknown", which is the
            # state §5 asks for. Within a day there is nothing new to write.
            writes=not same_day,
            reason=reason,
        )
    return DayReference(
        trading_day=trading_day,
        day_start_utc=day_start,
        equity_day_start=anchor.equity,
        observed_at=instant,
        anchored_on=anchor.observed_at,
        rolled=not same_day,
        writes=True,
        reason=DayReferenceReason.ROLLED if not same_day else DayReferenceReason.ADOPTED,
    )


def _usable(opening: EquityObservation | None, day_start: datetime) -> EquityObservation | None:
    """The observation, if it can honestly stand for the equity of midnight."""
    if opening is None or opening.equity <= 0:
        return None
    observed_at = ensure_utc(opening.observed_at)
    if observed_at > day_start:
        return None
    if day_start - observed_at > timedelta(seconds=DAY_OPENING_MAX_LAG_S):
        return None
    return EquityObservation(equity=opening.equity, observed_at=observed_at, cash=opening.cash)


def next_peak(
    row: PersistedRiskState, *, equity: Decimal, now: datetime
) -> tuple[Decimal, datetime, bool]:
    """``(peak, observed_at, raised)`` — monotonic, never reset, sampled.

    Directive §5: "manter o maior patrimônio histórico sem resets". The turn of
    the day is not an argument here, and that is the point: a drawdown-triggered
    WARNING outlives midnight because the peak does.
    """
    if equity > row.peak_equity:
        return equity, ensure_utc(now), True
    return row.peak_equity, row.peak_equity_at, False
