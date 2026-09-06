"""``compute_beta``: the estimator, the validity protocol and its identity.

The estimator is fed **returns**, never prices, so every expected number below is
exact arithmetic rather than a tolerance around a simulation. The synthetic
series is built so that the true OLS solution is known in closed form:

``x`` cycles over ``[+0.01, -0.01, +0.02, -0.02]`` and the residual ``e`` cycles
over ``[+0.005, +0.005, -0.005, -0.005]``. Over a whole number of cycles
``sum(x) = sum(e) = 0`` and ``sum(x*e) = 0`` — the residual is orthogonal to the
regressor — so for ``y = beta*x + e``:

- ``mean_x = mean_y = 0``, centring is a no-op and every sum below is exact;
- ``Sxy = beta*Sxx`` and therefore ``beta_hat = beta`` **exactly**, not within a
  tolerance;
- ``Syy = beta^2*Sxx + See``, so ``R^2 = beta^2*Sxx / (beta^2*Sxx + See)`` is a
  ratio of exact decimals.

With ``beta = 2.5``, per cycle ``Sxx = 0.001`` and ``See = 0.0001``:
``R^2 = 0.00625 / 0.00635 = 0.98425196850...`` -> ``0.984252`` at the declared
quantum. **Declared tolerance: zero.** The only rounding is the quantisation
itself, and that is the rounding of a known rational.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.beta import (
    BETA_METHOD_VERSION,
    REASON_BTC_MISSING,
    REASON_DEGENERATE_VARIANCE,
    REASON_GAPS,
    REASON_INSUFFICIENT_HISTORY,
    BetaEstimator,
    BetaSpec,
    HourlyReturn,
    beta_version,
    compute_beta,
    invalidates,
    is_known_version,
    reference_beta,
)

HOUR = timedelta(hours=1)
AS_OF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

X_CYCLE = (Decimal("0.01"), Decimal("-0.01"), Decimal("0.02"), Decimal("-0.02"))
E_CYCLE = (Decimal("0.005"), Decimal("0.005"), Decimal("-0.005"), Decimal("-0.005"))
BETA = Decimal("2.5")


def series(values: Sequence[Decimal], *, end: datetime = AS_OF) -> tuple[HourlyReturn, ...]:
    """``values`` as hourly returns, the newest one ending exactly at ``end``."""
    first = end - len(values) * HOUR
    return tuple(
        HourlyReturn(hour_start=first + index * HOUR, value=value)
        for index, value in enumerate(values)
    )


def synthetic(hours: int, *, beta: Decimal = BETA) -> tuple[list[Decimal], list[Decimal]]:
    """``hours`` paired returns whose exact OLS slope is ``beta``."""
    if hours % len(X_CYCLE):
        raise AssertionError("use a whole number of cycles or the closed form breaks")
    btc = [X_CYCLE[index % 4] for index in range(hours)]
    asset = [beta * x + E_CYCLE[index % 4] for index, x in enumerate(btc)]
    return asset, btc


def test_known_beta_and_r2_are_recovered_exactly() -> None:
    asset, btc = synthetic(720)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    assert estimate.valid is True
    assert estimate.reason is None
    assert estimate.beta == Decimal("2.50000000")
    assert estimate.r_squared == Decimal("0.984252")
    assert estimate.n == 720
    assert estimate.contiguous_bars == 720
    assert estimate.alpha == Decimal("0E-8")
    assert estimate.estimator == BetaEstimator.OLS_WITH_INTERCEPT


def test_intercept_absorbs_drift_that_regression_through_the_origin_would_not() -> None:
    """A drifting asset against a drifting BTC keeps the slope it was built with.

    Every asset return is shifted by +0.02 and every BTC return by +0.01, so the
    pair carries a mean the slope does not explain. With an intercept the answer
    is still 2.5; ``sum(x*y)/sum(x*x)`` on the same input is not — it is pulled
    towards ``alpha*sum(x)/sum(x^2)``, which is why ``beta_v1`` centres.
    """
    asset, btc = synthetic(720)
    drifted_asset = series([value + Decimal("0.02") for value in asset])
    drifted_btc = series([value + Decimal("0.01") for value in btc])
    estimate = compute_beta(drifted_asset, drifted_btc, as_of=AS_OF)
    assert estimate.beta == Decimal("2.50000000")
    assert estimate.alpha == Decimal("-0.00500000")  # 0.02 - 2.5*0.01

    through_origin = sum(
        (x.value * y.value for x, y in zip(drifted_btc, drifted_asset, strict=True)), Decimal(0)
    ) / sum((x.value * x.value for x in drifted_btc), Decimal(0))
    assert through_origin != BETA


def test_a_single_missing_hour_inside_the_run_is_a_gap() -> None:
    asset, btc = synthetic(720)
    full_asset, full_btc = series(asset), series(btc)
    hole = full_btc[400].hour_start
    gapped = tuple(item for item in full_btc if item.hour_start != hole)
    estimate = compute_beta(full_asset, gapped, as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_GAPS
    assert estimate.beta is None
    assert estimate.contiguous_bars == 719 - 400  # everything after the hole
    assert estimate.n == 719


def test_a_gap_older_than_the_required_run_still_validates() -> None:
    """20 contiguous days *inside* the 30 is the rule, not 30 clean ones."""
    asset, btc = synthetic(720)
    full_asset, full_btc = series(asset), series(btc)
    hole = full_btc[10].hour_start
    gapped = tuple(item for item in full_btc if item.hour_start != hole)
    estimate = compute_beta(full_asset, gapped, as_of=AS_OF)
    assert estimate.valid is True
    assert estimate.contiguous_bars == 709
    assert estimate.n == 719


def test_nineteen_days_is_warm_up_not_a_gap() -> None:
    asset, btc = synthetic(19 * 24)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_INSUFFICIENT_HISTORY
    assert estimate.n == 456
    assert estimate.contiguous_bars == 456


def test_twenty_days_exactly_is_enough() -> None:
    asset, btc = synthetic(20 * 24)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    assert estimate.valid is True
    assert estimate.beta == Decimal("2.50000000")
    assert estimate.contiguous_bars == 480


@pytest.mark.parametrize(("lag", "expected"), [(0, True), (1, True), (2, False), (3, False)])
def test_the_run_has_to_reach_the_cut_within_one_bar_of_slack(lag: int, expected: bool) -> None:
    """``max_bar_lag = 1``: one hour of slack, and the second hour is a gap.

    Zero slack would tie validity to persistence latency — a scanner firing at
    ``:00:02`` while the last minute lands would drop the asset out of the
    portfolio and take it back an hour later, every hour.
    """
    asset, btc = synthetic(720)
    end = AS_OF - lag * HOUR
    estimate = compute_beta(series(asset, end=end), series(btc, end=end), as_of=AS_OF)
    assert estimate.valid is expected
    assert estimate.reason == (None if expected else REASON_GAPS)
    assert estimate.last_pair_end == end


def test_btc_without_any_paired_hour_is_btc_missing() -> None:
    asset, _ = synthetic(720)
    estimate = compute_beta(series(asset), (), as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_BTC_MISSING
    assert estimate.n == 0


CONSTANT = Decimal("0.0001234567890123456789012345678")
"""A constant with more digits than ``CONTEXT.prec``, so that the *mean* of 720
copies of it rounds and the centred differences come out non-zero. Testing
``Sxx == 0`` therefore missed it, and two flat series were scored ``beta = 1``,
``R^2 = 1``, **valid** (Astra, T3.2 diff review, must-fix 1)."""


@pytest.mark.parametrize("flat_value", [Decimal(0), CONSTANT])
def test_constant_btc_has_no_identifiable_slope(flat_value: Decimal) -> None:
    flat = [flat_value] * 720
    asset, _ = synthetic(720)
    estimate = compute_beta(series(asset), series(flat), as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_DEGENERATE_VARIANCE
    assert estimate.beta is None
    assert estimate.r_squared is None


def test_two_constant_series_are_not_a_beta_of_one() -> None:
    """The exact regression Astra reproduced: it used to answer ``beta = 1``."""
    flat = series([CONSTANT] * 720)
    estimate = compute_beta(flat, flat, as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_DEGENERATE_VARIANCE
    assert estimate.beta is None
    assert estimate.r_squared is None


def test_a_constant_asset_against_a_moving_btc_is_still_degenerate() -> None:
    _, btc = synthetic(720)
    estimate = compute_beta(series([CONSTANT] * 720), series(btc), as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_DEGENERATE_VARIANCE
    assert estimate.beta == Decimal("0E-8")
    assert estimate.r_squared is None


def test_a_non_finite_return_is_refused_at_the_boundary() -> None:
    with pytest.raises(ValueError, match="finite"):
        HourlyReturn(hour_start=AS_OF - HOUR, value=Decimal("NaN"))


def test_constant_asset_has_a_slope_of_zero_and_no_r_squared() -> None:
    """``Syy = 0``: the slope is identifiable and it is zero; ``R^2`` is ``0/0``.

    It is still refused — a market whose hourly close did not move for thirty
    days is a broken feed or a dead market, not something to size against a
    factor — but the two facts are kept apart instead of fabricating ``R^2 = 1``.
    """
    _, btc = synthetic(720)
    estimate = compute_beta(series([Decimal(0)] * 720), series(btc), as_of=AS_OF)
    assert estimate.valid is False
    assert estimate.reason == REASON_DEGENERATE_VARIANCE
    assert estimate.beta == Decimal("0E-8")
    assert estimate.r_squared is None


def test_btc_against_btc_is_one_by_definition_never_estimated() -> None:
    estimate = reference_beta(as_of=AS_OF, market="BTCUSDT")
    assert estimate.beta == Decimal("1.00000000")
    assert estimate.estimator == BetaEstimator.DEFINITION
    assert estimate.valid is True
    assert estimate.reason is None
    assert estimate.n == 0
    assert estimate.r_squared is None  # nothing was regressed, so nothing is explained
    assert estimate.valid_until == AS_OF + HOUR


def test_a_series_regressed_on_itself_also_lands_on_one() -> None:
    """The definition and the estimator agree — the shortcut is not a fudge."""
    _, btc = synthetic(720)
    same = series(btc)
    estimate = compute_beta(same, same, as_of=AS_OF)
    assert estimate.beta == Decimal("1.00000000")
    assert estimate.r_squared == Decimal("1.000000")


def test_validity_expires_one_hour_after_the_window_not_after_the_job() -> None:
    asset, btc = synthetic(720)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    assert estimate.valid_until == AS_OF + HOUR
    assert estimate.window_end == AS_OF
    assert estimate.window_start == AS_OF - timedelta(days=30)
    assert estimate.input_start == estimate.window_start - HOUR
    assert estimate.last_pair_end == AS_OF


def test_a_late_run_does_not_buy_itself_extra_validity() -> None:
    """``valid_until`` is anchored to ``window_end``, so lateness costs, never pays.

    A job that runs at 12:37 for the 11:00-12:00 bar still expires at 13:00 —
    when the recomputation for the next closed hour is due. Anchoring on
    ``as_of`` (the brief's literal wording) would push it to 13:37 and let a
    beta outlive its own replacement (Astra, T3.2 diff review, must-fix 3).
    """
    asset, btc = synthetic(720)
    late = AS_OF + timedelta(minutes=37)
    estimate = compute_beta(series(asset), series(btc), as_of=late)
    assert estimate.window_end == AS_OF
    assert estimate.as_of == late
    assert estimate.valid_until == AS_OF + HOUR
    assert estimate.valid is True


def test_a_new_gap_inside_the_window_invalidates_the_estimate() -> None:
    asset, btc = synthetic(720)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    inside = AS_OF - timedelta(days=3)
    assert invalidates(estimate, inside, inside + timedelta(minutes=5)) is True
    before = estimate.input_start - timedelta(hours=2)
    assert invalidates(estimate, before, before + timedelta(minutes=5)) is False
    assert invalidates(estimate, before, estimate.input_start) is True  # inclusive end


def test_a_gap_in_the_anchor_bar_invalidates_too() -> None:
    """The bar before ``window_start`` is read, so a hole in it changes the answer.

    One missing minute at ``window_start - 1min`` costs the window its first
    return; backfilling it adds a pair. Comparing against ``window_start``
    answered ``False`` for both (Astra, T3.2 diff review, must-fix 2).
    """
    asset, btc = synthetic(720)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    minute = estimate.window_start - timedelta(minutes=1)
    assert invalidates(estimate, minute, minute) is True


def test_a_gap_starting_at_the_window_end_is_the_next_bar_not_this_one() -> None:
    asset, btc = synthetic(720)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF)
    assert invalidates(estimate, estimate.window_end, estimate.window_end) is False
    last_minute_read = estimate.window_end - timedelta(minutes=1)
    assert invalidates(estimate, last_minute_read, last_minute_read) is True


def test_the_estimate_is_reproducible_byte_for_byte() -> None:
    asset, btc = synthetic(720)
    first = compute_beta(series(asset), series(btc), as_of=AS_OF, market="PEPEUSDT")
    second = compute_beta(series(asset), series(btc), as_of=AS_OF, market="PEPEUSDT")
    assert first == second
    assert canonical_json(first.as_wire()) == canonical_json(second.as_wire())
    assert b'"beta":"2.5"' in canonical_json(first.as_wire())


def test_the_version_names_the_shipped_parameters_and_flags_any_override() -> None:
    assert beta_version(BetaSpec()) == BETA_METHOD_VERSION
    other = BetaSpec(min_contiguous_days=10)
    assert beta_version(other).startswith(f"{BETA_METHOD_VERSION}+")
    assert beta_version(other) != BETA_METHOD_VERSION
    assert beta_version(other) == beta_version(BetaSpec(min_contiguous_days=10))
    assert is_known_version(BETA_METHOD_VERSION) is True
    assert is_known_version(beta_version(other)) is False
    assert is_known_version("beta_v0") is False


def test_an_overridden_spec_travels_in_the_estimate() -> None:
    spec = BetaSpec(min_contiguous_days=10)
    asset, btc = synthetic(10 * 24)
    estimate = compute_beta(series(asset), series(btc), as_of=AS_OF, spec=spec)
    assert estimate.valid is True
    assert estimate.version == beta_version(spec)
    assert estimate.as_wire()["params"]["min_contiguous_days"] == 10


def test_a_naive_as_of_is_refused() -> None:
    with pytest.raises(ValueError, match="tz"):
        compute_beta((), (), as_of=datetime(2026, 9, 6, 12, 0))  # noqa: DTZ001


def test_unordered_or_duplicated_hours_are_refused() -> None:
    asset, btc = synthetic(8)
    ordered = series(btc)
    with pytest.raises(ValueError, match="strictly increasing"):
        compute_beta(series(asset), (ordered[1], ordered[0], *ordered[2:]), as_of=AS_OF)


def test_an_hour_after_the_cut_is_refused() -> None:
    asset, btc = synthetic(8)
    with pytest.raises(ValueError, match="after the cut"):
        compute_beta(series(asset, end=AS_OF + HOUR), series(btc), as_of=AS_OF)


def test_spec_rejects_a_window_shorter_than_the_run_it_requires() -> None:
    with pytest.raises(ValueError, match="window_days"):
        BetaSpec(window_days=10, min_contiguous_days=20)
