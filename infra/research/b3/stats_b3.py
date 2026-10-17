"""Statistics of the WIN family (contract item h of H-039): monthly-block bootstrap, side
permutation within strata, halves and Holm.

Floats on purpose (``docs/RESEARCH.md`` "Numerário"): the inputs are net bp per trade,
already computed in ``Decimal`` by the simulator; Monte Carlo error dominates any
representation error here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

import numpy as np

from infra.research.stats import adjust_family

REPS = 10_000
SEED = 20261019
CI_TAIL = 0.05 / 3 / 2
"""Individual Bonferroni intervals: nominal 95 % family coverage for the three means."""
_CELLS = 2_000_000


def monthly_bootstrap_ci(
    values: np.ndarray,
    months: np.ndarray,
    *,
    blocks: np.ndarray | None = None,
    reps: int = REPS,
    seed: int = SEED,
    tail: float = CI_TAIL,
) -> tuple[float, float]:
    """Percentile CI of the trade-weighted mean, resampling whole months with replacement.

    ``blocks`` is the universe of months to resample (the months with at least one
    operation); a month in it without any value is an empty block, not dropped. A replicate
    that draws only empty blocks has no mean and is left out of the quantiles.
    """
    y = np.asarray(values, dtype=np.float64)
    if y.size == 0:
        return math.nan, math.nan
    month_ids = np.asarray(months)
    universe = np.unique(month_ids if blocks is None else np.asarray(blocks))
    if not np.isin(month_ids, universe).all():
        raise ValueError("a value's month is outside the block universe")
    gid = np.searchsorted(universe, month_ids)
    k = int(universe.size)
    sums = np.bincount(gid, weights=y, minlength=k)
    counts = np.bincount(gid, minlength=k).astype(np.float64)
    rng = np.random.default_rng(seed)
    per = max(1, _CELLS // k)
    means: list[np.ndarray] = []
    done = 0
    while done < reps:
        m = min(per, reps - done)
        draw = rng.integers(0, k, size=(m, k))
        n = counts[draw].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            means.append(np.where(n > 0, sums[draw].sum(1) / np.where(n > 0, n, 1), np.nan))
        done += m
    stats = np.concatenate(means)
    stats = stats[np.isfinite(stats)]
    if stats.size == 0:
        return math.nan, math.nan
    return float(np.quantile(stats, tail)), float(np.quantile(stats, 1 - tail))


def side_permutation_p(
    y_rule: np.ndarray,
    y_flip: np.ndarray,
    rule_is_buy: np.ndarray,
    strata: np.ndarray,
    *,
    reps: int = REPS,
    seed: int = SEED,
) -> float:
    """p = (1 + #{permuted means ≥ observed}) / (reps + 1), sides shuffled within strata.

    ``y_rule`` is each trade's net bp on the side the rule chose, ``y_flip`` on the other
    side (mirrored geometry). Shuffling keeps the number of buys in each stratum.
    """
    rule = np.asarray(y_rule, dtype=np.float64)
    flip = np.asarray(y_flip, dtype=np.float64)
    buy = np.asarray(rule_is_buy, dtype=bool)
    n = rule.size
    if n == 0:
        return math.nan
    y_buy = np.where(buy, rule, flip)
    y_sell = np.where(buy, flip, rule)
    diff = y_buy - y_sell
    base = y_sell.sum()
    observed = rule.mean()
    _, sid = np.unique(np.asarray(strata), return_inverse=True)
    order = np.argsort(sid, kind="stable")
    sorted_sid = sid[order]
    starts = np.searchsorted(sorted_sid, sorted_sid, side="left")
    buys_in = np.bincount(sid, weights=buy.astype(np.float64)).astype(np.int64)
    take = (np.arange(n) - starts) < buys_in[sorted_sid]
    rng = np.random.default_rng(seed)
    per = max(1, _CELLS // n)
    hits = 0
    done = 0
    while done < reps:
        m = min(per, reps - done)
        keys = sid[None, :] + rng.random((m, n))
        perm = np.argsort(keys, axis=1, kind="stable")
        means = (base + diff[perm][:, take].sum(1)) / n
        # float ties (relative difference < 1e-9, emenda 1) count as ≥ the observed mean
        hits += int(np.count_nonzero(means >= observed - 1e-9 * abs(observed)))
        done += m
    return (1 + hits) / (reps + 1)


def half_cut(dates: Sequence[date]) -> date | None:
    """Last date of the first half: the ⌈n/2⌉-th distinct date (the median date included)."""
    distinct = sorted(set(dates))
    return distinct[math.ceil(len(distinct) / 2) - 1] if distinct else None


def first_half_mask(dates: Sequence[date], cut: date | None = None) -> np.ndarray:
    """True for trades on or before ``cut`` (default: the half cut of ``dates`` themselves)."""
    limit = half_cut(dates) if cut is None else cut
    return np.array([limit is not None and d <= limit for d in dates], dtype=bool)


def holm(p: Sequence[float]) -> list[float]:
    return list(adjust_family(p).holm_adjusted)
