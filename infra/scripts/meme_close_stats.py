"""The ruler of the daily close — IC 95 % by hour blocks, the paired contrast,
terciles. Pure; no database, no clock.

Why blocks of an hour: the bets of the same hour share the same tape, the same
creation wave and the same gate state (the ``blocos90.py`` argument, one level
down — a day has no "days" to resample). Bets inside a block are not
independent, so the interval resamples **whole blocks** with replacement,
seed ``20260912`` (EXP-M1's rule of success), 2 000 draws. The contrast pairs
the two groups on the same draw of blocks, because they share the calendar.

Nothing here is money persisted, so the bootstrap runs in ``float``; what is
reported (means, totals, bounds) is turned back into ``Decimal`` at 4 places
and never fed to another computation.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

SEED = 20260912
RESAMPLES = 2_000
MIN_N = 30
"""Below this many closed bets a lesson is "insuficiente" and changes nothing."""
MIN_CELL_N = 10
MIN_BLOCKS = 3
MIN_VALID_DRAWS = 100
PLACES = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class Sample:
    """Values with the block each one belongs to (the Brasília hour of entry)."""

    blocks: tuple[str, ...]
    values: tuple[Decimal, ...]

    def by_block(self) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for block, value in zip(self.blocks, self.values, strict=True):
            out.setdefault(block, []).append(float(value))
        return out


@dataclass(frozen=True, slots=True)
class Interval:
    n: int
    blocks: int
    mean: Decimal | None
    total: Decimal
    ci95: tuple[Decimal, Decimal] | None
    """``None`` with fewer than two blocks: one block cannot be resampled."""


@dataclass(frozen=True, slots=True)
class Contrast:
    n_a: int
    n_b: int
    blocks: int
    mean_a: Decimal | None
    mean_b: Decimal | None
    delta: Decimal | None
    ci95: tuple[Decimal, Decimal] | None
    valid_draws: int


def fmt(value: Decimal | None, *, places: int = 4) -> str:
    if value is None:
        return "—"
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _dec(value: float) -> Decimal:
    return Decimal(repr(value)).quantize(PLACES)


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return None if not values else (sum(values, Decimal(0)) / len(values)).quantize(PLACES)


def _percentile(sorted_values: list[float], p: float) -> float:
    position = p * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _bounds(draws: list[float]) -> tuple[Decimal, Decimal]:
    draws.sort()
    return _dec(_percentile(draws, 0.025)), _dec(_percentile(draws, 0.975))


def block_ci(sample: Sample, *, resamples: int = RESAMPLES, seed: int = SEED) -> Interval:
    """IC 95 % of the mean, resampling whole blocks with replacement."""
    n = len(sample.values)
    buckets = sample.by_block()
    keys = sorted(buckets)
    interval = Interval(n, len(keys), _mean(sample.values), sum(sample.values, Decimal(0)), None)
    if len(keys) < 2:
        return interval
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        chosen = [v for key in rng.choices(keys, k=len(keys)) for v in buckets[key]]
        draws.append(sum(chosen) / len(chosen))
    return Interval(n, len(keys), interval.mean, interval.total, _bounds(draws))


def block_contrast(
    a: Sample, b: Sample, *, resamples: int = RESAMPLES, seed: int = SEED
) -> Contrast:
    """Δ = mean(A) − mean(B), both groups drawn on the **same** resample of blocks."""
    buckets_a, buckets_b = a.by_block(), b.by_block()
    keys = sorted(set(buckets_a) | set(buckets_b))
    mean_a, mean_b = _mean(a.values), _mean(b.values)
    delta = None if mean_a is None or mean_b is None else (mean_a - mean_b).quantize(PLACES)
    if len(keys) < 2 or delta is None:
        return Contrast(len(a.values), len(b.values), len(keys), mean_a, mean_b, delta, None, 0)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(resamples):
        chosen = rng.choices(keys, k=len(keys))
        side_a = [v for key in chosen for v in buckets_a.get(key, ())]
        side_b = [v for key in chosen for v in buckets_b.get(key, ())]
        if side_a and side_b:
            draws.append(sum(side_a) / len(side_a) - sum(side_b) / len(side_b))
    ci95 = _bounds(draws) if len(draws) >= MIN_VALID_DRAWS else None
    return Contrast(
        len(a.values), len(b.values), len(keys), mean_a, mean_b, delta, ci95, len(draws)
    )


def passes_ruler(contrast: Contrast, *, total_n: int) -> bool:
    """The evidence a lesson needs before it may become an ``M-L`` row: n ≥ 30
    closed bets, ≥ 3 blocks, both cells ≥ 10, and an interval that excludes 0."""
    if total_n < MIN_N or contrast.blocks < MIN_BLOCKS or contrast.ci95 is None:
        return False
    if contrast.n_a < MIN_CELL_N or contrast.n_b < MIN_CELL_N:
        return False
    low, high = contrast.ci95
    return low > 0 or high < 0


def tercile_edges(values: Sequence[Decimal]) -> tuple[Decimal, Decimal] | None:
    """The values that close the lower and the middle third (``⌊n/3⌋``-th and
    ``⌊2n/3⌋``-th of the sorted known values); ``None`` below three values."""
    ordered = sorted(values)
    n = len(ordered)
    if n < 3:
        return None
    return ordered[n // 3 - 1], ordered[2 * n // 3 - 1]


def tercile_label(value: Decimal | None, edges: tuple[Decimal, Decimal] | None) -> str:
    if value is None:
        return "desconhecido"
    if edges is None:
        return "conhecido"
    low, high = edges
    if value <= low:
        return f"baixo (≤ {fmt(low)})"
    if value <= high:
        return f"médio ({fmt(low)}–{fmt(high)})"
    return f"alto (> {fmt(high)})"
