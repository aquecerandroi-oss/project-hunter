"""``compute_beta`` — the regression, the validity protocol, the invalidation.

Pure: no IO, no clock, no session. ``as_of`` is an argument because the caller
owns the clock (the same rule ``Strategy.evaluate`` follows), which is what makes
two runs of this function byte-identical and a replay of last month reproducible.

**The estimator is ordinary least squares with an intercept**, on centred
returns:

    Sxx = sum (x - x̄)^2      Sxy = sum (x - x̄)(y - ȳ)      Syy = sum (y - ȳ)^2
    beta = Sxy / Sxx          alpha = ȳ - beta·x̄            R^2 = Sxy^2 / (Sxx·Syy)

Regression through the origin was the alternative and it loses, for a reason
that is algebra rather than taste:
``beta_origin = beta_ols + alpha·sum(x)/sum(x^2)``. An asset that fell all month
while the BTC rose gets its slope pulled by its own drift — the intercept is
exactly the parameter that keeps the *sensitivity to variation* apart from the
*mean the slope does not explain*. It is also what ``regr_slope`` computes, so
the operational number remains comparable to the two measurements already
published (KB-0060, KB-0071).

**R^2 is reported, never a gate.** KB-0060 measured a median R^2 of 0.152 on the
established memes and 0.021 on the rest; a minimum R^2 would keep most of the
universe in shadow forever under the directive's §4 rule, and — more to the
point — a low R^2 does not make a slope wrong, it makes the factor a small part
of the variance. The consumer applies ``|notional × beta|`` and keeps its other
limits (Astra, T3.2 opinion: no automatic margin from R^2; an uncertainty
policy, if one is ever wanted, is its own versioned decision).

**Why there is no NumPy here.** The brief allowed ``float64`` over *returns*.
The window is at most 720 pairs, so the arithmetic is free either way, and
``float64`` buys a real risk: NumPy's pairwise summation and SIMD width are not
contractual, so the same input can differ in the last bits between the Windows
dev box and the Linux VPS — and a value sitting on a quantisation boundary then
serialises to two different canonical byte strings. ``M2`` demands byte-for-byte
reproducibility, so every accumulation below is ``Decimal`` under
``hunter_core.strategies.numeric.CONTEXT``, two passes, chronological order.
Prices never become floats anywhere; neither do returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.beta.model import (
    DEFAULT_SPEC,
    REASON_BTC_MISSING,
    REASON_DEGENERATE_VARIANCE,
    REASON_GAPS,
    REASON_INSUFFICIENT_HISTORY,
    BetaEstimate,
    BetaEstimator,
    BetaSpec,
    HourlyReturn,
    beta_version,
)
from hunter_indicators.beta.returns import floor_bar, window_bounds

_ZERO = Decimal(0)
_ONE = Decimal(1)

Pair = tuple[datetime, Decimal, Decimal]


@dataclass(frozen=True, slots=True)
class _Fit:
    beta: Decimal | None
    alpha: Decimal | None
    r_squared: Decimal | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class _Coverage:
    n: int
    contiguous_bars: int
    reason: str | None


def _checked(
    returns: Sequence[HourlyReturn], *, start: datetime, end: datetime, spec: BetaSpec, label: str
) -> tuple[HourlyReturn, ...]:
    """``returns`` inside the window, refusing anything that is not a clean series.

    Unordered, duplicated, misaligned or post-cut bars raise instead of being
    silently dropped: they mean the caller built the series wrong, and a beta
    quietly computed on the survivors would be a number nobody could reproduce.
    """
    previous: datetime | None = None
    for item in returns:
        hour = item.hour_start
        if floor_bar(hour, spec) != hour:
            raise ValueError(f"{label} bar {hour.isoformat()} is not aligned to the bar boundary")
        if previous is not None and hour <= previous:
            raise ValueError(f"{label} bars must be strictly increasing, got {hour.isoformat()}")
        if hour + spec.bar > end:
            raise ValueError(f"{label} bar {hour.isoformat()} ends after the cut {end.isoformat()}")
        previous = hour
    return tuple(item for item in returns if item.hour_start >= start)


def _pair(asset: Sequence[HourlyReturn], reference: Sequence[HourlyReturn]) -> tuple[Pair, ...]:
    """Bars present in **both** series, oldest first — strict pairing, no sliding."""
    by_hour = {item.hour_start: item.value for item in reference}
    return tuple(
        (item.hour_start, item.value, by_hour[item.hour_start])
        for item in asset
        if item.hour_start in by_hour
    )


def _run_length(pairs: Sequence[Pair], *, spec: BetaSpec) -> int:
    """Unbroken bars at the end of ``pairs`` (each exactly one bar after the last)."""
    run = 1
    for index in range(len(pairs) - 1, 0, -1):
        if pairs[index][0] - pairs[index - 1][0] != spec.bar:
            break
        run += 1
    return run


def _coverage(
    pairs: Sequence[Pair], *, end: datetime, spec: BetaSpec, has_reference: bool
) -> _Coverage:
    """Whether the pairs carry the maturity the directive asks for, and why not.

    The order of the tests is the meaning of the answers: no reference at all is
    ``btc_missing``; history whose **reach** (oldest pair to the cut) is shorter
    than the required run is ``insufficient_history``; history that reaches back
    but whose recent run is broken — or that stops before the cut — is ``gaps``.
    The two have different cures, which is the whole point: one waits, the other
    needs a backfill.

    It borrows the vocabulary of ``features/windows.py`` but **not** its rule,
    and the difference is declared (Astra, T3.2 diff review): there, a hole
    inside a history that does reach back is a gap; here, reach is measured
    first, so a hundred hours with a hole in them are reported as
    ``insufficient_history`` — "could not have matured yet" — rather than as
    damage. With no pairs at all the two are simply indistinguishable from these
    arguments, and warm-up is the weaker claim of the two.
    """
    if not has_reference:
        return _Coverage(n=0, contiguous_bars=0, reason=REASON_BTC_MISSING)
    if not pairs:
        return _Coverage(n=0, contiguous_bars=0, reason=REASON_INSUFFICIENT_HISTORY)
    reach = (end - pairs[0][0]) // spec.bar
    run = _run_length(pairs, spec=spec)
    if reach < spec.required_bars:
        return _Coverage(n=len(pairs), contiguous_bars=run, reason=REASON_INSUFFICIENT_HISTORY)
    lag = (end - (pairs[-1][0] + spec.bar)) // spec.bar
    reason = REASON_GAPS if run < spec.required_bars or lag > spec.max_bar_lag else None
    return _Coverage(n=len(pairs), contiguous_bars=run, reason=reason)


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    """``value`` at the storage resolution, with ``-0`` normalised to ``0``."""
    with localcontext(CONTEXT):
        result = value.quantize(quantum)
        return _ZERO.quantize(quantum) if result == 0 else result


def _constant(values: Sequence[Decimal]) -> bool:
    """Whether every value is the same number, decided **before** any arithmetic.

    Testing ``Sxx == 0`` instead was a bug Astra reproduced (T3.2 diff review,
    must-fix 1): 720 copies of a 28-digit constant sum to a mean that rounds, the
    centred differences come out non-zero, and two flat series were scored
    ``beta = 1``, ``R^2 = 1``, **valid**. Constancy is a property of the input, so
    it is decided on the input — exactly, with no epsilon.
    """
    return all(value == values[0] for value in values)


def _fit(pairs: Sequence[Pair], spec: BetaSpec) -> _Fit:
    """OLS with an intercept, in ``Decimal``, two passes, chronological order."""
    with localcontext(CONTEXT):
        if _constant([pair[2] for pair in pairs]):
            # No dispersion in the factor: the slope is not identifiable. Never
            # zero, never one — the question has no answer on this window.
            return _Fit(beta=None, alpha=None, r_squared=None, reason=REASON_DEGENERATE_VARIANCE)
        size = Decimal(len(pairs))
        mean_x = sum((pair[2] for pair in pairs), _ZERO) / size
        mean_y = sum((pair[1] for pair in pairs), _ZERO) / size
        if _constant([pair[1] for pair in pairs]):
            # The slope *is* identifiable and it is exactly zero, but R^2 is 0/0.
            # Reported apart, and still refused: a market whose hourly close did
            # not move for the whole window is a dead feed, not a hedge.
            return _Fit(
                beta=_quantize(_ZERO, spec.beta_quantum),
                alpha=_quantize(mean_y, spec.beta_quantum),
                r_squared=None,
                reason=REASON_DEGENERATE_VARIANCE,
            )
        sxx = sxy = syy = _ZERO
        for _, y_value, x_value in pairs:
            dx = x_value - mean_x
            dy = y_value - mean_y
            sxx += dx * dx
            sxy += dx * dy
            syy += dy * dy
        if sxx == 0 or syy == 0:
            # A series that is not constant but whose dispersion vanishes at 28
            # digits. Kept as a backstop, never as the primary test.
            return _Fit(beta=None, alpha=None, r_squared=None, reason=REASON_DEGENERATE_VARIANCE)
        beta = sxy / sxx
        alpha = mean_y - beta * mean_x
        r_squared = sxy * sxy / (sxx * syy)
        r_squared = min(max(r_squared, _ZERO), _ONE)  # rounding may overshoot by 1e-28
        return _Fit(
            beta=_quantize(beta, spec.beta_quantum),
            alpha=_quantize(alpha, spec.beta_quantum),
            r_squared=_quantize(r_squared, spec.r2_quantum),
            reason=None,
        )


def compute_beta(
    asset_returns: Sequence[HourlyReturn],
    btc_returns: Sequence[HourlyReturn],
    *,
    as_of: datetime,
    spec: BetaSpec = DEFAULT_SPEC,
    market: str | None = None,
    reference: str | None = None,
) -> BetaEstimate:
    """The market's slope against the reference over the window ending at ``as_of``.

    Always returns an estimate: an unusable window is a ``valid=False`` row with
    a ``reason``, never an exception and never an invented number, so the Risk
    Engine can log *why* an asset stays in shadow.
    """
    as_of = ensure_utc(as_of)
    start, end = window_bounds(as_of, spec)
    asset = _checked(asset_returns, start=start, end=end, spec=spec, label="asset")
    btc = _checked(btc_returns, start=start, end=end, spec=spec, label="reference")
    pairs = _pair(asset, btc)
    coverage = _coverage(pairs, end=end, spec=spec, has_reference=bool(btc))
    fit = (
        _Fit(beta=None, alpha=None, r_squared=None, reason=coverage.reason)
        if coverage.reason is not None
        else _fit(pairs, spec)
    )
    return BetaEstimate(
        version=beta_version(spec),
        estimator=spec.estimator,
        as_of=as_of,
        window_start=start,
        window_end=end,
        input_start=start - spec.bar,
        last_pair_end=pairs[-1][0] + spec.bar if pairs else None,
        valid_until=end + spec.valid_for,
        beta=fit.beta,
        alpha=fit.alpha,
        r_squared=fit.r_squared,
        n=coverage.n,
        contiguous_bars=coverage.contiguous_bars,
        valid=fit.reason is None,
        reason=fit.reason,
        spec=spec,
        market=market,
        reference=reference,
    )


def reference_beta(
    *, as_of: datetime, market: str | None = None, spec: BetaSpec = DEFAULT_SPEC
) -> BetaEstimate:
    """The reference against itself: ``beta = 1`` **by definition**, not estimated.

    No window, no maturity gate and no ``R^2``: there is nothing to regress, so
    reporting ``R^2 = 1`` would dress a definition up as a measurement. ``n = 0``
    and ``estimator = definition`` say so on the row itself, which is what stops
    a consumer from averaging this 1 into a distribution of estimates.
    """
    as_of = ensure_utc(as_of)
    start, end = window_bounds(as_of, spec)
    return BetaEstimate(
        version=beta_version(spec),
        estimator=BetaEstimator.DEFINITION,
        as_of=as_of,
        window_start=start,
        window_end=end,
        input_start=start - spec.bar,
        last_pair_end=None,
        valid_until=end + spec.valid_for,
        beta=_quantize(_ONE, spec.beta_quantum),
        alpha=_quantize(_ZERO, spec.beta_quantum),
        r_squared=None,
        n=0,
        contiguous_bars=0,
        valid=True,
        reason=None,
        spec=spec,
        market=market,
        reference=market,
    )


def invalidates(estimate: BetaEstimate, gap_start: datetime, gap_end: datetime) -> bool:
    """Whether a newly detected gap touches the minutes ``estimate`` was built on.

    ``[gap_start, gap_end]`` is **inclusive at both ends**, the convention of
    ``ingestion_gaps`` (``backfill_plan.normalize_window`` is the one place that
    translates the scanner's half-open window into it). Any overlap discards the
    estimate before ``valid_until``: whether the gap means minutes were missing
    all along or a backfill is about to add them, the set of bars the regression
    saw is no longer the set of bars that exist, and the honest move is to
    recompute rather than to reason about which direction the number moved.

    The interval compared against is ``[input_start, window_end)``, **not** the
    reported window, and both ends were corrected in Astra's diff review:

    - it starts one bar early, at the anchor. A minute missing at
      ``window_start - 1min`` costs the window its first return, and backfilling
      it adds a pair — a dependency the reported window does not show, which is
      why :attr:`BetaEstimate.input_start` is published next to it;
    - it is **exclusive** at ``window_end``: the minute stamped ``window_end`` is
      the first minute of the bar that has not closed yet, so a gap starting
      there costs availability without protecting any observation that was used.
    """
    return not (
        ensure_utc(gap_end) < estimate.input_start or ensure_utc(gap_start) >= estimate.window_end
    )


__all__ = ["compute_beta", "invalidates", "reference_beta"]
