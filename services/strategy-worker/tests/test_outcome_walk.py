"""The outcome model, bar by bar — SHADOW-LAB.md "Decisão conjunta" §3 and §5.

A pure fold over closed 1-minute bars: entry at a chosen open, gap-at-the-open
before intrabar touches, stop before target when both are inside one bar,
expiration at the exact horizon open, invalidation observed at a close and paid
at the next open, and excursions that stay **null** when OHLC cannot tell where
the extreme happened.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, Timeframe
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.walker import Bar, Progress, TrackingPlan, walk

pytestmark = pytest.mark.unit

FREE = AssumedCosts(
    spread_bps=Decimal("0"),
    slippage_bps=Decimal("0"),
    fee_bps=Decimal("0"),
    max_entry_delay_s=120,
)
REAL = AssumedCosts(
    spread_bps=Decimal("2"),
    slippage_bps=Decimal("5"),
    fee_bps=Decimal("4"),
    max_entry_delay_s=120,
)
ENTRY_OPEN = datetime(2026, 9, 5, 12, 1, tzinfo=UTC)


def bar(minute: int, o: str, h: str, low: str, c: str) -> Bar:
    return Bar(
        open_time=ENTRY_OPEN + timedelta(minutes=minute),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
    )


def plan(
    *,
    stop: str = "99",
    target1: str = "102",
    horizon_s: int = 7200,
    costs: AssumedCosts = FREE,
    invalidation: str | None = None,
) -> TrackingPlan:
    return TrackingPlan(
        entry_bar_open=ENTRY_OPEN,
        stop=Decimal(stop),
        target1=Decimal(target1),
        horizon_s=horizon_s,
        costs=costs,
        invalidation_level=None if invalidation is None else Decimal(invalidation),
        invalidation_timeframe=None if invalidation is None else Timeframe.M5,
    )


class TestEntry:
    def test_the_entry_is_the_open_of_the_chosen_bar_plus_the_assumed_costs(self) -> None:
        after = walk(plan(costs=REAL), Progress.start(), [bar(0, "100", "100.5", "99.5", "100.2")])
        assert after.tracking_state is ShadowTrackingState.ACTIVE
        assert after.entry == Decimal("100.06")
        assert after.entry_ts == ENTRY_OPEN
        assert after.last_bar_open == ENTRY_OPEN

    def test_geometry_is_revalidated_against_the_entry_price_after_a_gap(self) -> None:
        """The frozen levels are intact; the *entry* moved past target1, so
        ``stop < P_entry < target1`` no longer holds: no_entry, never a trade
        with a negative reward."""
        after = walk(plan(costs=REAL), Progress.start(), [bar(0, "103", "104", "102", "103.5")])
        assert after.tracking_state is ShadowTrackingState.NO_ENTRY
        assert after.no_entry_reason == "geometry"
        assert after.entry is None

    def test_a_gap_below_the_stop_also_fails_the_geometry_check(self) -> None:
        after = walk(plan(costs=REAL), Progress.start(), [bar(0, "98", "99.5", "97", "98.5")])
        assert after.tracking_state is ShadowTrackingState.NO_ENTRY
        assert after.no_entry_reason == "geometry"


class TestExits:
    def test_stop_and_target_in_the_same_bar_resolve_as_stop(self) -> None:
        """The versioned pessimistic convention (SHADOW-LAB.md §3)."""
        after = walk(plan(), Progress.start(), [bar(0, "100", "103", "98", "101")])
        assert after.result is OutcomeResult.STOP
        assert after.exit_base == Decimal("99")
        assert after.tracking_state is ShadowTrackingState.TERMINAL

    def test_a_gap_below_the_stop_exits_at_the_open_not_at_the_stop(self) -> None:
        after = walk(
            plan(),
            Progress.start(),
            [bar(0, "100", "100.5", "99.5", "100"), bar(1, "97", "97.5", "96", "96.5")],
        )
        assert after.result is OutcomeResult.STOP
        assert after.exit_base == Decimal("97")
        assert after.exit_ts == ENTRY_OPEN + timedelta(minutes=1)

    def test_a_gap_above_the_target_gets_no_credit_beyond_target1(self) -> None:
        after = walk(
            plan(),
            Progress.start(),
            [bar(0, "100", "100.5", "99.5", "100"), bar(1, "105", "106", "104", "105")],
        )
        assert after.result is OutcomeResult.TARGET
        assert after.exit_base == Decimal("102")

    def test_expiration_happens_at_the_exact_horizon_open(self) -> None:
        horizon_s = 180
        bars = [
            bar(0, "100", "100.4", "99.5", "100"),
            bar(1, "100", "100.4", "99.5", "100"),
            bar(2, "100", "100.4", "99.5", "100"),
            bar(3, "100.3", "101", "100", "100.8"),
        ]
        after = walk(plan(horizon_s=horizon_s), Progress.start(), bars)
        assert after.result is OutcomeResult.EXPIRED
        assert after.exit_base == Decimal("100.3")
        assert after.exit_ts == ENTRY_OPEN + timedelta(seconds=horizon_s)

    def test_no_extreme_after_the_horizon_can_reach_the_excursions(self) -> None:
        after = walk(
            plan(horizon_s=120),
            Progress.start(),
            [
                bar(0, "100", "100.4", "99.5", "100"),
                bar(1, "100", "100.4", "99.5", "100"),
                bar(2, "100.3", "101.9", "100", "101.5"),
            ],
        )
        assert after.exit_base == Decimal("100.3")
        assert after.exit_at_open is True
        assert after.complete_high == Decimal("100.4")

    def test_an_invalidation_seen_at_a_close_exits_at_the_next_open(self) -> None:
        """The 5m bar ending 12:05 is the 1m bar opening 12:04; its close below
        the level is *observed* there and *paid* at the 12:05 open."""
        bars = [bar(minute, "100", "100.4", "99.5", "100") for minute in range(3)] + [
            bar(3, "100", "100.2", "99.6", "99.7"),
            bar(4, "99.8", "100", "99.5", "99.9"),
        ]
        after = walk(plan(invalidation="99.8"), Progress.start(), bars)
        assert after.result is OutcomeResult.INVALIDATED
        assert after.exit_base == Decimal("99.8")
        assert after.exit_ts == ENTRY_OPEN + timedelta(minutes=4)

    def test_a_close_below_the_level_off_the_boundary_is_not_an_invalidation(self) -> None:
        """Only closes of the invalidation timeframe count: 12:03 is not a 5m
        close, so the same candle body proves nothing."""
        bars = [
            bar(0, "100", "100.4", "99.5", "100"),
            bar(1, "100", "100.2", "99.6", "99.7"),
            bar(2, "99.8", "100", "99.5", "99.9"),
        ]
        after = walk(plan(invalidation="99.8"), Progress.start(), bars)
        assert after.tracking_state is ShadowTrackingState.ACTIVE
        assert after.pending_invalidation is False

    def test_an_invalidation_below_the_stop_is_still_a_stop_first(self) -> None:
        bars = [bar(minute, "100", "100.4", "99.5", "100") for minute in range(3)] + [
            bar(3, "100", "100.2", "99.6", "99.7"),
            bar(4, "98", "98.5", "97", "97.5"),
        ]
        after = walk(plan(invalidation="99.8"), Progress.start(), bars)
        assert after.result is OutcomeResult.STOP
        assert after.exit_base == Decimal("98")

    def test_expiry_outranks_a_pending_invalidation_on_the_same_open(self) -> None:
        """The declared priority is ``stop > target > expired > invalidated``
        (``notes-S2.md`` §9). Price is identical either way — what differs is
        the name of what happened, and S3 counts by that name, so the code and
        the note have to agree.

        12:04 closes a 5m bar below the level (invalidation observed) and 12:05
        is exactly the horizon open, so both rules fire at the same open.
        """
        bars = [bar(minute, "100", "100.4", "99.5", "100") for minute in range(3)] + [
            bar(3, "100", "100.2", "99.6", "99.7"),
            bar(4, "99.9", "100", "99.5", "99.9"),
        ]
        after = walk(plan(invalidation="99.8", horizon_s=240), Progress.start(), bars)
        assert after.result is OutcomeResult.EXPIRED
        assert after.exit_base == Decimal("99.9")
        assert after.exit_ts == ENTRY_OPEN + timedelta(seconds=240)

    def test_a_terminal_tracking_never_reopens(self) -> None:
        after = walk(plan(), Progress.start(), [bar(0, "100", "103", "98", "101")])
        again = walk(plan(), after, [bar(1, "110", "111", "109", "110")])
        assert again == after


class TestIdempotence:
    def test_a_bar_already_folded_in_is_ignored(self) -> None:
        first = walk(plan(), Progress.start(), [bar(0, "100", "100.5", "99.5", "100")])
        replayed = walk(plan(), first, [bar(0, "100", "100.5", "99.5", "100")])
        assert replayed == first

    def test_a_bar_out_of_sequence_is_refused_instead_of_silently_skipped(self) -> None:
        first = walk(plan(), Progress.start(), [bar(0, "100", "100.5", "99.5", "100")])
        with pytest.raises(ValueError, match="contiguous"):
            walk(plan(), first, [bar(2, "100", "100.5", "99.5", "100")])

    def test_the_progress_round_trips_through_json(self) -> None:
        after = walk(
            plan(),
            Progress.start(),
            [bar(0, "100", "100.5", "99.5", "100"), bar(1, "100", "100.9", "99.6", "100.5")],
        )
        assert Progress.from_jsonable(after.to_jsonable()) == after


class TestExcursions:
    def test_the_guiding_ambiguous_scenario(self) -> None:
        """SHADOW-LAB.md §5: entry 100, stop 99, target 102, one bar low 98 /
        high 103 -> mfe is NULL, bounds.mfe = [0, 3], ambiguous."""
        after = walk(plan(), Progress.start(), [bar(0, "100", "103", "98", "101")])
        excursions = after.excursions(plan())
        assert excursions["ambiguous"] is True
        assert excursions["mfe"] is None
        assert excursions["bounds"]["mfe"] == [Decimal("0"), Decimal("3")]
        assert excursions["bounds"]["mae"] == [Decimal("1"), Decimal("2")]
        assert excursions["mfe_complete_bars"] is None
        assert excursions["method"] == "ohlc_complete_bars_v1"

    def test_an_exit_at_an_open_determines_both_excursions(self) -> None:
        """The exit bar contributes only the exit price itself; everything
        before it is complete, so nothing is ambiguous."""
        after = walk(
            plan(horizon_s=120),
            Progress.start(),
            [
                bar(0, "100", "100.4", "99.5", "100"),
                bar(1, "100", "100.8", "99.2", "100.5"),
                bar(2, "100.3", "101.9", "100", "101.5"),
            ],
        )
        excursions = after.excursions(plan())
        assert excursions["ambiguous"] is False
        assert excursions["mfe"] == Decimal("0.8")
        assert excursions["mae"] == Decimal("0.8")
        assert excursions["coverage"] == {"bars_known": 2, "bars_total": 2}

    def test_the_extreme_carries_its_bar_never_an_invented_instant(self) -> None:
        """OHLC gives the value of a bar's high, not the second it happened in."""
        after = walk(
            plan(horizon_s=120),
            Progress.start(),
            [
                bar(0, "100", "100.4", "99.5", "100"),
                bar(1, "100", "100.8", "99.2", "100.5"),
                bar(2, "100.3", "101.9", "100", "101.5"),
            ],
        )
        excursions = after.excursions(plan())
        assert excursions["mfe_ts"] is None
        assert excursions["mae_ts"] is None
        assert excursions["mfe_bar"] == ENTRY_OPEN + timedelta(minutes=1)

    def test_an_unfinished_tracking_has_no_upper_bound(self) -> None:
        """The rest of the trade has not happened yet; the largest extreme seen
        so far is a floor, never the answer."""
        after = walk(
            plan(),
            Progress.start(),
            [bar(0, "100", "100.4", "99.5", "100"), bar(1, "100", "100.8", "99.2", "100.5")],
        )
        excursions = after.excursions(plan())
        assert excursions["mfe"] is None
        assert excursions["bounds"]["mfe"] == [Decimal("0.8"), None]
        assert excursions["ambiguous"] is True
        assert excursions["coverage"]["bars_total"] is None

    def test_a_censored_tracking_never_reports_full_coverage(self) -> None:
        """The minute that could not be recovered may hold either extreme."""
        after = walk(plan(), Progress.start(), [bar(0, "100", "101", "99.5", "100.5")])
        censored = after.censor("gap:test")
        excursions = censored.excursions(plan())
        assert excursions["mfe"] is None
        assert excursions["mae"] is None
        assert excursions["bounds"]["mfe"] == [Decimal("1"), None]
        assert excursions["coverage"]["bars_total"] is None
        assert excursions["mfe_complete_bars"] == Decimal("1")

    def test_a_target_exit_bounds_the_favourable_excursion_from_below(self) -> None:
        """Reaching target1 is proven; anything above it may have come after."""
        after = walk(plan(), Progress.start(), [bar(0, "100", "103", "99.5", "102.5")])
        excursions = after.excursions(plan())
        assert excursions["bounds"]["mfe"] == [Decimal("2"), Decimal("3")]
        assert excursions["mfe"] is None

    def test_a_favourable_gap_is_measured_at_the_observed_open(self) -> None:
        """The trade is credited at target1 (no credit beyond it), but the
        market really opened at 105 and the position lived through that."""
        after = walk(
            plan(),
            Progress.start(),
            [bar(0, "100", "100.5", "99.5", "100"), bar(1, "105", "106", "104", "105")],
        )
        assert after.exit_base == Decimal("102")
        assert after.exit_observed == Decimal("105")
        excursions = after.excursions(plan())
        assert excursions["mfe"] == Decimal("5")

    def test_mae_is_a_positive_magnitude_and_never_negative(self) -> None:
        after = walk(
            plan(horizon_s=120),
            Progress.start(),
            [
                bar(0, "100", "101", "100.5", "100.9"),
                bar(1, "100.6", "101", "100.5", "100.8"),
                bar(2, "100.7", "101", "100.6", "100.9"),
            ],
        )
        assert after.result is OutcomeResult.EXPIRED
        assert after.excursions(plan())["mae"] == Decimal("0")

    def test_without_complete_bars_the_partial_reading_is_unavailable_not_zero(self) -> None:
        after = walk(plan(), Progress.start(), [bar(0, "100", "103", "98", "101")])
        assert after.excursions(plan())["mae_complete_bars"] is None
