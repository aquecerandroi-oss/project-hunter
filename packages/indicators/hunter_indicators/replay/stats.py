"""Paired contrasts with the dependence this population actually has.

The signals are **not** independent: many altcoins react to the same BTC move
inside the same hour, so the unit of resampling is a **block of time**, not a
signal and not a market (KB-0051). One block is one UTC day of the entry.

Three deliberate choices, all declared before any result was looked at:

1. **The estimand is the mean per signal**, ``sum(S_b) / sum(n_b)`` over blocks,
   not the mean of daily means: days hold different numbers of entries and
   averaging averages would silently change what is being estimated (Astra, R1
   design review).
2. **The interval** comes from resampling whole blocks with replacement
   (percentile), and is refused — ``None`` with a reason — when there is a
   single block: ``[effect, effect]`` is not precision, it is a tautology.
3. **The p-value** comes from flipping the sign of whole blocks, enumerated
   exactly while ``2^B`` is small. It is **exploratory**: sign flipping needs
   symmetry of the block effects, which nothing here has established, and with
   few blocks it is bounded from below (``B = 6`` cannot go under ``2/64``, so
   no Holm rejection at 5% over seven contrasts is even possible). Reported as
   descriptive, never as confirmation.

Holm then adjusts over the **declared family of seven**, whatever subset ran.
Holm tolerates arbitrary dependence between valid p-values; it does not repair
p-values that were not valid to begin with.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

import numpy as np

from hunter_core.domain.types import ensure_utc

__all__ = [
    "EXACT_MAX_BLOCKS",
    "ContrastResult",
    "Pair",
    "blocks_of",
    "contrast",
    "holm",
    "paired_estimate",
    "sign_flip_p",
]

EXACT_MAX_BLOCKS: Final = 12
"""Above ``2^12`` sign vectors the enumeration is replaced by a seeded sample."""

_SAMPLED_FLIPS: Final = 20_000
_TOLERANCE: Final = 1e-12


@dataclass(frozen=True, slots=True)
class Pair:
    """One signal's paired difference, tagged with the time block it belongs to."""

    block: str
    delta: Decimal


def blocks_of(entry_ts: datetime) -> str:
    """The block label of an entry — its UTC day."""
    return ensure_utc(entry_ts).date().isoformat()


def paired_estimate(pairs: Sequence[Pair]) -> Decimal | None:
    """Mean difference per signal, in Decimal. ``None`` when there are no pairs."""
    if not pairs:
        return None
    total = sum((pair.delta for pair in pairs), start=Decimal(0))
    return total / Decimal(len(pairs))


def _block_arrays(pairs: Sequence[Pair]) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Per-block sums and counts, blocks in sorted order (stable across runs)."""
    labels = sorted({pair.block for pair in pairs})
    index = {label: i for i, label in enumerate(labels)}
    sums = np.zeros(len(labels), dtype=np.float64)
    counts = np.zeros(len(labels), dtype=np.float64)
    for pair in pairs:
        i = index[pair.block]
        sums[i] += float(pair.delta)
        counts[i] += 1.0
    return labels, sums, counts


def _sign_matrix(n_blocks: int, seed: int) -> tuple[np.ndarray, str]:
    if n_blocks <= EXACT_MAX_BLOCKS:
        total = 1 << n_blocks
        bits = (np.arange(total)[:, None] >> np.arange(n_blocks)[None, :]) & 1
        return 1.0 - 2.0 * bits.astype(np.float64), "sign_flip_exact"
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 2, size=(_SAMPLED_FLIPS, n_blocks))
    return 1.0 - 2.0 * draws.astype(np.float64), "sign_flip_sampled"


def sign_flip_p(pairs: Sequence[Pair], *, seed: int = 0) -> tuple[float, str, int]:
    """Two-sided p by flipping the sign of whole blocks. Exploratory (see module)."""
    if not pairs:
        return 1.0, "no_pairs", 0
    _labels, sums, counts = _block_arrays(pairs)
    n_blocks = len(sums)
    observed = abs(float(sums.sum()) / float(counts.sum()))
    signs, method = _sign_matrix(n_blocks, seed)
    stats = np.abs(signs @ sums) / float(counts.sum())
    hits = int(np.count_nonzero(stats >= observed - _TOLERANCE))
    draws = int(signs.shape[0])
    if method == "sign_flip_sampled":
        # (hits + 1) / (draws + 1): a sample that happened not to exceed the
        # observed statistic is not evidence of p = 0 (Astra, R1 diff review).
        return (hits + 1) / float(draws + 1), method, n_blocks
    return hits / float(draws), method, n_blocks


def _bootstrap_ci(
    sums: np.ndarray, counts: np.ndarray, *, seed: int, resamples: int, alpha: float
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(sums), size=(resamples, len(sums)))
    ratios = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    lo, hi = np.quantile(ratios, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(lo), float(hi)


@dataclass(frozen=True, slots=True)
class ContrastResult:
    """One contrast, with everything needed to read it honestly."""

    key: str
    n_pairs: int
    blocks: int
    estimate: Decimal | None
    ci_low: float | None
    ci_high: float | None
    ci_reason: str | None
    p_value: float | None
    p_method: str
    seed: int
    resamples: int


def contrast(
    key: str,
    pairs: Sequence[Pair],
    *,
    seed: int,
    resamples: int,
    alpha: float = 0.05,
) -> ContrastResult:
    """Estimate, block-bootstrap interval and sign-flip p for one contrast."""
    estimate = paired_estimate(pairs)
    if not pairs:
        return ContrastResult(key, 0, 0, None, None, None, "no_pairs", None, "no_pairs", seed, 0)
    _labels, sums, counts = _block_arrays(pairs)
    n_blocks = len(sums)
    p_value, method, _ = sign_flip_p(pairs, seed=seed)
    if n_blocks < 2:
        return ContrastResult(
            key,
            len(pairs),
            n_blocks,
            estimate,
            None,
            None,
            "single_block",
            p_value,
            method,
            seed,
            0,
        )
    lo, hi = _bootstrap_ci(sums, counts, seed=seed, resamples=resamples, alpha=alpha)
    return ContrastResult(
        key, len(pairs), n_blocks, estimate, lo, hi, None, p_value, method, seed, resamples
    )


def holm(pvalues: Mapping[str, float], *, family_size: int) -> dict[str, float]:
    """Holm-adjusted p-values over a family of ``family_size`` tests.

    ``family_size`` is the *declared* family, not ``len(pvalues)``: running a
    subset of the block must not lighten the penalty. Adjusted values are made
    monotone and capped at 1.
    """
    if family_size < len(pvalues):
        raise ValueError("family_size cannot be smaller than the number of tests run")
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    for position, (key, raw) in enumerate(ordered):
        candidate = (family_size - position) * raw
        running = min(1.0, max(running, candidate))
        adjusted[key] = running
    return adjusted
