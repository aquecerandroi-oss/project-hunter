"""``hunter_indicators.meme.fast`` — the 15-second series folded into one
instant's features (T4.16): the 60 s delta and slope, the progress delta, the
holders trend, every ``None`` with its name — and the look-ahead proof: a
photo received after ``as_of`` changes nothing."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.fast import (
    DENOMINATOR_UNKNOWN,
    FAST_DEFINITIONS,
    NO_HOLDERS_READER,
    NO_SNAPSHOT,
    TOO_FEW_POINTS,
    TOO_FEW_READINGS,
    FastPoint,
    HoldersPoint,
    compute_fast,
    holders_trend,
    usable_fast_points,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 17, 0, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(seconds=2)
INITIAL = Decimal("793100000")
SERIES: dict[int, tuple[str, str]] = {
    -75: ("29", "780000000"),
    -60: ("30", "779000000"),
    -45: ("31", "778000000"),
    -30: ("33", "776000000"),
    -15: ("34", "775000000"),
    0: ("36", "773000000"),
}
"""``(mcap_sol, real_token_reserves)`` per second offset from ``T0``; each
photo reaches us one second after its block time."""


def _points(*extra: FastPoint) -> list[FastPoint]:
    base = [
        FastPoint(
            observed_at=T0 + timedelta(seconds=s),
            received_at=T0 + timedelta(seconds=s + 1),
            mcap_sol=Decimal(mcap),
            real_token_reserves=Decimal(reserves),
        )
        for s, (mcap, reserves) in SERIES.items()
    ]
    return [*base, *extra]


def test_the_definitions_are_registered_once_each_at_version_one() -> None:
    keys = [d.key for d in FAST_DEFINITIONS]
    assert keys == ["mcap_delta_60s", "mcap_slope_60s", "progress_delta_60s", "holders_rising"]
    assert all(d.version == 1 and d.params["delta_s"] == 60 for d in FAST_DEFINITIONS)


def test_the_delta_and_the_slope_are_taken_against_the_photo_at_least_60_s_older() -> None:
    row = compute_fast(_points(), as_of=AS_OF, initial_real_token_reserves=INITIAL)
    assert row.snapshot_observed_at == T0 and row.snapshots_120s == 6
    assert row.mcap_sol == Decimal("36.0000000000")
    assert row.mcap_delta_60s == Decimal("6.0000000000"), "36 at 0 s minus 30 at -60 s"
    assert row.window_reason is None
    # OLS of ln(mcap) against minutes since the reference, five points 0..1 min.
    xs = [0.0, 0.25, 0.5, 0.75, 1.0]
    ys = [math.log(v) for v in (30.0, 31.0, 33.0, 34.0, 36.0)]
    mx, my = sum(xs) / 5, sum(ys) / 5
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mx) ** 2 for x in xs
    )
    assert row.mcap_slope_60s == Decimal(repr(slope)).quantize(Decimal("0.000001"))
    assert row.mcap_slope_60s > 0
    # Progress: 1 - real/initial, newest minus the reference.
    now = (Decimal(1) - Decimal("773000000") / INITIAL).quantize(Decimal("0.000001"))
    ref = (Decimal(1) - Decimal("779000000") / INITIAL).quantize(Decimal("0.000001"))
    assert row.curve_progress_pct == now and row.progress_delta_60s == now - ref
    assert row.progress_rising is True and row.progress_reason is None


def test_a_photo_received_after_as_of_does_not_exist_for_that_instant() -> None:
    before = compute_fast(_points(), as_of=AS_OF, initial_real_token_reserves=INITIAL)
    late_newer = FastPoint(
        observed_at=T0 + timedelta(seconds=1),
        received_at=AS_OF + timedelta(seconds=1),
        mcap_sol=Decimal("90"),
        real_token_reserves=Decimal("700000000"),
    )
    late_older = FastPoint(
        observed_at=T0 - timedelta(seconds=5),
        received_at=AS_OF + timedelta(seconds=1),
        mcap_sol=Decimal("1"),
        real_token_reserves=Decimal("790000000"),
    )
    after = compute_fast(
        _points(late_newer, late_older), as_of=AS_OF, initial_real_token_reserves=INITIAL
    )
    assert after == before, "the future is not an input of the present"
    # Received one second later, the same photos are inputs — and they move the row.
    moved = compute_fast(
        _points(late_newer), as_of=AS_OF + timedelta(seconds=1), initial_real_token_reserves=INITIAL
    )
    assert moved.mcap_sol == Decimal("90.0000000000") and moved.snapshot_observed_at == (
        T0 + timedelta(seconds=1)
    )


def test_usable_points_keep_the_last_120_s_one_per_instant_and_drop_unpriced_photos() -> None:
    dup = FastPoint(T0, T0 + timedelta(seconds=2), Decimal("37"), Decimal("772000000"))
    unpriced = FastPoint(T0 - timedelta(seconds=20), T0, None, None)
    old = FastPoint(T0 - timedelta(seconds=130), T0, Decimal("5"), Decimal("790000000"))
    window = usable_fast_points(_points(dup, unpriced, old), as_of=AS_OF)
    assert [p.observed_at for p in window] == [T0 + timedelta(seconds=s) for s in SERIES]
    assert window[-1].mcap_sol == Decimal("37"), "the last received photo of an instant wins"


def test_fewer_than_60_s_of_photos_is_too_few_points_and_no_photo_is_no_snapshot() -> None:
    young = [
        FastPoint(T0 - timedelta(seconds=15), T0, Decimal("30"), Decimal("779000000")),
        FastPoint(T0, T0 + timedelta(seconds=1), Decimal("36"), Decimal("773000000")),
    ]
    row = compute_fast(young, as_of=AS_OF, initial_real_token_reserves=INITIAL)
    assert row.mcap_sol == Decimal("36.0000000000") and row.snapshots_120s == 2
    assert (row.mcap_delta_60s, row.mcap_slope_60s, row.window_reason) == (
        None,
        None,
        TOO_FEW_POINTS,
    )
    assert row.curve_progress_pct is not None and row.progress_delta_60s is None
    assert row.progress_rising is None and row.progress_reason == TOO_FEW_POINTS
    empty = compute_fast([], as_of=AS_OF, initial_real_token_reserves=INITIAL)
    assert empty.window_reason == NO_SNAPSHOT and empty.progress_reason == NO_SNAPSHOT
    assert empty.snapshots_120s == 0 and empty.mcap_sol is None


def test_an_unknown_denominator_names_itself_and_keeps_the_market_cap_columns() -> None:
    row = compute_fast(_points(), as_of=AS_OF, initial_real_token_reserves=None)
    assert row.mcap_delta_60s == Decimal("6.0000000000") and row.window_reason is None
    assert row.curve_progress_pct is None and row.progress_reason == DENOMINATOR_UNKNOWN
    assert row.progress_delta_60s is None and row.progress_rising is None


def test_holders_rise_only_over_two_consecutive_readings_received_in_time() -> None:
    def reading(seconds: int, holders: int | None, *, late: bool = False) -> HoldersPoint:
        observed = T0 + timedelta(seconds=seconds)
        return HoldersPoint(
            observed_at=observed,
            received_at=AS_OF + timedelta(seconds=1) if late else observed + timedelta(seconds=1),
            holders=holders,
        )

    assert holders_trend([], as_of=AS_OF).holders_reason == NO_HOLDERS_READER
    one = holders_trend([reading(-30, 3)], as_of=AS_OF)
    assert (one.holders, one.holders_prev, one.holders_rising) == (3, None, None)
    assert one.holders_reason == TOO_FEW_READINGS
    rising = holders_trend([reading(-30, 3), reading(-15, 5)], as_of=AS_OF)
    assert (rising.holders, rising.holders_prev, rising.holders_rising) == (5, 3, True)
    assert rising.holders_reason is None
    flat = holders_trend([reading(-30, 5), reading(-15, 5)], as_of=AS_OF)
    assert flat.holders_rising is False
    falling = holders_trend([reading(-30, 5), reading(-15, 4)], as_of=AS_OF)
    assert falling.holders_rising is False
    # A reading stamped inside the window but received after as_of is not there yet.
    unseen = holders_trend(
        [reading(-30, 3), reading(-15, 5), reading(0, 2, late=True)], as_of=AS_OF
    )
    assert unseen == rising
    # A reading with no holders count is not a reading of holders.
    blank = holders_trend([reading(-30, 3), reading(-15, None)], as_of=AS_OF)
    assert blank.holders_reason == TOO_FEW_READINGS
