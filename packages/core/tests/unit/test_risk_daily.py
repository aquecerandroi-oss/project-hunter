"""The durable daily reference and the monotonic peak — RISK_ENGINE.md §5.

Everything here is a function of its arguments: the row as Postgres holds it, an
equity observation, and the instant. No session, so the rules can be stated as a
table of cases and read without a container.

The rule that costs the most to get wrong is the one Astra's review of this diff
produced a number for: **the day's opening is a measurement of midnight, not the
equity of whenever the evaluation happened to run.** Opening 20.000 at midnight,
19.500 thirty seconds later; adopting 19.500 as the opening reports a 2,5 % daily
loss as 0 % and the 2 % block never fires. So only an observation taken *at or
before* the turn may anchor the day, and "no such observation" is a state the
engine represents rather than papers over.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.risk.daily import (
    DAY_OPENING_MAX_LAG_S,
    DayReferenceReason,
    EquityObservation,
    PersistedRiskState,
    next_peak,
    resolve_day_reference,
)

ORG = uuid.uuid4()
PORTFOLIO = uuid.uuid4()

# Sao Paulo is UTC-3 and has no DST today: midnight there is 03:00 UTC.
DAY = date(2026, 9, 6)
DAY_START = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)
NEXT_DAY = date(2026, 9, 7)
NEXT_DAY_START = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)


def row(
    *,
    trading_day: date | None = DAY,
    day_start: datetime | None = DAY_START,
    equity_day_start: Decimal | None = Decimal(20000),
    observed_at: datetime | None = DAY_START,
    peak: Decimal = Decimal(20000),
    peak_at: datetime = DAY_START,
    cadence: int = 60,
) -> PersistedRiskState:
    return PersistedRiskState(
        organization_id=ORG,
        portfolio_id=PORTFOLIO,
        trading_day=trading_day,
        trading_day_timezone="America/Sao_Paulo",
        trading_day_start_utc=day_start,
        equity_day_start=equity_day_start,
        day_reference_observed_at=observed_at,
        peak_equity=peak,
        peak_equity_at=peak_at,
        peak_sampling_interval_s=cadence,
    )


def observation(equity: str, at: datetime) -> EquityObservation:
    return EquityObservation(equity=Decimal(equity), observed_at=at)


class TestTheReferenceWithinTheDay:
    def test_the_persisted_opening_is_carried_untouched(self) -> None:
        now = DAY_START + timedelta(hours=8)

        reference = resolve_day_reference(
            row(), opening=observation("19500", now - timedelta(minutes=1)), now=now
        )

        assert reference.equity_day_start == Decimal(20000)
        assert reference.observed_at == DAY_START
        assert reference.rolled is False
        assert reference.writes is False
        assert reference.reason is DayReferenceReason.CARRIED
        assert reference.available is True

    def test_an_unknown_reference_is_filled_from_a_point_before_the_turn(self) -> None:
        """The row knows the day but not its opening; the curve has the answer."""
        now = DAY_START + timedelta(hours=3)

        reference = resolve_day_reference(
            row(equity_day_start=None, observed_at=None),
            opening=observation("20000", DAY_START - timedelta(seconds=20)),
            now=now,
        )

        assert reference.equity_day_start == Decimal(20000)
        assert reference.anchored_on == DAY_START - timedelta(seconds=20)
        assert reference.observed_at == now, "the instant of the evaluation, per §18.7"
        assert reference.writes is True
        assert reference.reason is DayReferenceReason.ADOPTED


class TestTheTurnOfTheDay:
    def test_a_new_day_is_anchored_on_the_last_point_before_the_turn(self) -> None:
        now = NEXT_DAY_START + timedelta(seconds=5)

        reference = resolve_day_reference(
            row(), opening=observation("19800", NEXT_DAY_START - timedelta(seconds=30)), now=now
        )

        assert reference.trading_day == NEXT_DAY
        assert reference.day_start_utc == NEXT_DAY_START
        assert reference.equity_day_start == Decimal(19800)
        assert reference.anchored_on == NEXT_DAY_START - timedelta(seconds=30)
        assert reference.rolled is True
        assert reference.writes is True
        assert reference.reason is DayReferenceReason.ROLLED

    def test_an_observation_after_the_turn_may_not_anchor_the_day(self) -> None:
        """Astra, review of this diff: 20.000 at midnight, 19.500 at 00:00:30.

        Anchoring on the later point reports a 2,5 % daily loss as 0 % and the
        2 % block never fires. Thirty seconds is not "close enough to midnight";
        it is *after* midnight, which is a different fact.
        """
        now = NEXT_DAY_START + timedelta(seconds=30)

        reference = resolve_day_reference(row(), opening=observation("19500", now), now=now)

        assert reference.equity_day_start is None
        assert reference.available is False
        assert reference.reason is DayReferenceReason.UNAVAILABLE_NO_OBSERVATION
        assert reference.rolled is True
        assert reference.writes is True, "the day itself is recorded; only the equity is unknown"

    def test_a_rollover_with_no_observation_at_all_leaves_the_opening_unknown(self) -> None:
        """The restart case: nothing was being marked when the day turned."""
        now = NEXT_DAY_START + timedelta(hours=3, minutes=17)

        reference = resolve_day_reference(row(), opening=None, now=now)

        assert reference.trading_day == NEXT_DAY
        assert reference.equity_day_start is None
        assert reference.observed_at is None
        assert reference.available is False
        assert reference.reason is DayReferenceReason.UNAVAILABLE_NO_OBSERVATION

    def test_an_observation_too_far_before_the_turn_is_not_a_measurement_of_it(self) -> None:
        stale = NEXT_DAY_START - timedelta(seconds=DAY_OPENING_MAX_LAG_S + 1)
        fresh = NEXT_DAY_START - timedelta(seconds=DAY_OPENING_MAX_LAG_S)

        refused = resolve_day_reference(
            row(), opening=observation("19800", stale), now=NEXT_DAY_START + timedelta(seconds=5)
        )
        accepted = resolve_day_reference(
            row(), opening=observation("19800", fresh), now=NEXT_DAY_START + timedelta(seconds=5)
        )

        assert refused.available is False
        assert refused.reason is DayReferenceReason.UNAVAILABLE_STALE_OBSERVATION
        assert accepted.available is True

    def test_a_late_evaluation_still_anchors_correctly_and_says_it_was_late(self) -> None:
        """Lateness moves ``observed_at``, never the number it records."""
        anchor_at = NEXT_DAY_START - timedelta(seconds=10)
        now = NEXT_DAY_START + timedelta(hours=6)

        reference = resolve_day_reference(row(), opening=observation("19800", anchor_at), now=now)

        assert reference.equity_day_start == Decimal(19800)
        assert reference.anchored_on == anchor_at
        assert reference.observed_at == now

    def test_a_wallet_with_no_day_at_all_is_a_rollover(self) -> None:
        reference = resolve_day_reference(
            row(trading_day=None, day_start=None, equity_day_start=None, observed_at=None),
            opening=observation("20000", DAY_START - timedelta(seconds=5)),
            now=DAY_START + timedelta(seconds=1),
        )

        assert reference.rolled is True
        assert reference.equity_day_start == Decimal(20000)

    def test_a_stale_day_start_for_the_same_date_is_rewritten(self) -> None:
        """A tzdata correction moves the instant; the date alone is not the anchor."""
        reference = resolve_day_reference(
            row(day_start=DAY_START + timedelta(hours=1)),
            opening=observation("20000", DAY_START - timedelta(seconds=5)),
            now=DAY_START + timedelta(seconds=10),
        )

        assert reference.day_start_utc == DAY_START
        assert reference.writes is True

    def test_a_naive_instant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="naive|tz"):
            resolve_day_reference(row(), opening=None, now=datetime(2026, 9, 6, 12))  # noqa: DTZ001


class TestThePeak:
    def test_the_peak_only_rises(self) -> None:
        now = DAY_START + timedelta(hours=5)

        raised = next_peak(row(peak=Decimal(20000)), equity=Decimal(21000), now=now)
        kept = next_peak(row(peak=Decimal(20000)), equity=Decimal(19000), now=now)

        assert raised == (Decimal(21000), now, True)
        assert kept == (Decimal(20000), DAY_START, False)

    def test_the_turn_of_the_day_does_not_reset_the_peak(self) -> None:
        """Directive §5: "manter o maior patrimônio histórico sem resets"."""
        reference = resolve_day_reference(
            row(peak=Decimal(25000)),
            opening=observation("23000", NEXT_DAY_START - timedelta(seconds=5)),
            now=NEXT_DAY_START,
        )
        peak, _at, changed = next_peak(
            row(peak=Decimal(25000)), equity=Decimal(23000), now=NEXT_DAY_START
        )

        assert reference.rolled is True
        assert peak == Decimal(25000)
        assert changed is False
