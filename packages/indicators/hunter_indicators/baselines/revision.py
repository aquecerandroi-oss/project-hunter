"""One immutable baseline revision, its counts and the gate that judges it.

The joint M2 decision (``docs/plans/M2.md`` §Baselines) fixes the shape: per
minute observations, 420 expected per ``(market, feature, UTC hour)`` bucket over
seven days, and a baseline that is only **usable** with >= 3 distinct days AND
>= 120 valid observations. Two things follow, and both are deliberate:

- **the gate belongs to the reader, not to the row.** ``feature_baselines``
  stores ``sample_size``/``expected_size``/``distinct_days``/``coverage`` raw
  (``docs/DATABASE.md`` §17.2) and the thresholds live in
  ``opportunity_weights.weights["baseline_gate"]``. A thin bucket is a revision
  that exists and is refused, never a row that is missing: "under construction"
  is a state the Radar shows;
- **"insufficient history" is not "stale source".** They are different facts
  about different things — the maturity of the population versus the freshness
  of the current reading — and they never collapse into one reason string.

Every statistic is quantised to the resolution of the column that will hold it
before anyone reads it (``NUMERIC(28,10)`` for median/MAD, ``NUMERIC(9,6)`` for
coverage). A ``MAD`` of ``1e-12`` in memory is ``0`` in Postgres, and a replay
that reads it back would take the ``mad_zero`` branch the live evaluation did
not (Astra, T2.3 design review).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT

ALGO_VERSION = "median_mad_v1"
"""Version of the baseline algorithm itself — ``feature_baselines.algo_version``.

A median produced by another algorithm is another population, not a newer value
of the same one, so a reader selects revisions by *compatible* versions. A change
to the statistic, to the bucketing or to the quantisation is a new string here.
"""

STAT_QUANTUM = Decimal("0.0000000001")
"""``NUMERIC(28,10)`` — the resolution of ``median`` and ``mad``."""

COVERAGE_QUANTUM = Decimal("0.000001")
"""``NUMERIC(9,6)`` — the resolution of ``coverage``."""

REASON_NO_OBSERVATIONS = "no_observations"
"""The bucket held nothing: there is no median to write, not even a thin one."""

REASON_INSUFFICIENT_HISTORY = "insufficient_history"
"""The revision exists and is below the gate — maturity, never freshness."""


def quantize_stat(value: Decimal) -> Decimal:
    """``value`` at the resolution ``feature_baselines.median``/``mad`` holds."""
    with localcontext(CONTEXT):
        return value.quantize(STAT_QUANTUM)


def quantize_coverage(value: Decimal) -> Decimal:
    """``value`` at the resolution ``feature_baselines.coverage`` holds."""
    with localcontext(CONTEXT):
        return value.quantize(COVERAGE_QUANTUM)


@dataclass(frozen=True, slots=True)
class BaselineKey:
    """The bucket: one market, one feature, one UTC hour of the day."""

    market_id: uuid.UUID
    feature: str
    hour_of_day: int

    def __post_init__(self) -> None:
        if not 0 <= self.hour_of_day <= 23:
            raise ValueError(f"hour_of_day {self.hour_of_day} is not a UTC hour bucket")

    def as_wire(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "feature": self.feature,
            "hour_of_day": self.hour_of_day,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    """One per-minute reading of one feature that was **valid** when it was taken.

    Only ``quality == ok`` values reach here (``collect.py``): a degraded reading
    says an input was late, and folding our own collection health into the
    market's distribution would make the baseline describe the scanner.
    """

    ts: datetime
    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", ensure_utc(self.ts))


@dataclass(frozen=True, slots=True)
class BaselineGate:
    """The versioned usability thresholds, read from the active weight vector."""

    min_distinct_days: int
    min_valid_observations: int
    expected_size: int

    @classmethod
    def from_weights(cls, weights: Mapping[str, Any]) -> BaselineGate:
        """Read ``weights["baseline_gate"]`` — never a default in code.

        Raises ``KeyError`` when the block is absent: a scorer that invents a
        gate would decide with thresholds nobody published.
        """
        block: Mapping[str, Any] = weights["baseline_gate"]
        return cls(
            min_distinct_days=int(block["min_distinct_days"]),
            min_valid_observations=int(block["min_valid_observations"]),
            expected_size=int(block["expected_size"]),
        )


@dataclass(frozen=True, slots=True)
class BaselineRevision:
    """One row of ``feature_baselines``, before it has an id.

    The id is assigned by whoever appends it: an ``ON CONFLICT DO NOTHING`` that
    collides must return the id that is actually stored, not the one this process
    generated (Astra, T2.3 design review, must-fix 1).
    """

    key: BaselineKey
    feature_version: int
    algo_version: str
    sampling: BaselineSampling
    source: BaselineSource
    window_start: datetime
    window_end: datetime
    available_at: datetime
    median: Decimal
    mad: Decimal
    sample_size: int
    expected_size: int
    distinct_days: int
    coverage: Decimal
    input_fingerprint: str

    def __post_init__(self) -> None:
        """The row refuses what ``feature_baselines`` refuses.

        The CHECKs (``sample_size <= expected_size``, ``coverage BETWEEN 0 AND
        1``) are the last line, not the only one: the adapter inserts a market
        in one batch, so a row built by hand that breaks one of them aborts the
        whole transaction and no bucket is written. Astra built exactly that in
        the review of the fix-pass and the INSERT compiled happily.
        """
        if self.expected_size <= 0:
            raise ValueError(f"{self.key}: expected_size {self.expected_size} is not positive")
        if self.sample_size < 0 or self.sample_size > self.expected_size:
            raise ValueError(
                f"{self.key}: sample_size {self.sample_size} is outside "
                f"[0, expected_size {self.expected_size}]"
            )
        if not Decimal(0) <= self.coverage <= Decimal(1):
            raise ValueError(f"{self.key}: coverage {self.coverage} is outside [0, 1]")
        if self.distinct_days < 0 or self.distinct_days > self.sample_size:
            raise ValueError(
                f"{self.key}: distinct_days {self.distinct_days} exceeds the "
                f"{self.sample_size} observations it would have to come from"
            )

    def usable_under(self, gate: BaselineGate) -> bool:
        return (
            self.distinct_days >= gate.min_distinct_days
            and self.sample_size >= gate.min_valid_observations
        )

    def gate_reason(self, gate: BaselineGate) -> str | None:
        """``None`` when usable, else why — maturity, never freshness."""
        return None if self.usable_under(gate) else REASON_INSUFFICIENT_HISTORY

    def as_row(self) -> dict[str, Any]:
        """The ``feature_baselines`` row this revision writes (no ``id``)."""
        return {
            "market_id": self.key.market_id,
            "feature": self.key.feature,
            "feature_version": self.feature_version,
            "algo_version": self.algo_version,
            "hour_of_day": self.key.hour_of_day,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "available_at": self.available_at,
            "median": self.median,
            "mad": self.mad,
            "sample_size": self.sample_size,
            "expected_size": self.expected_size,
            "distinct_days": self.distinct_days,
            "coverage": self.coverage,
            "source": self.source,
            "sampling": self.sampling,
            "input_fingerprint": self.input_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class BaselineUnavailable:
    """No revision could be computed — the counts survive, the median does not."""

    key: BaselineKey
    reason: str
    sample_size: int
    expected_size: int
    distinct_days: int
    coverage: Decimal


@dataclass(frozen=True, slots=True)
class StoredBaseline:
    """A revision that is in the archive, with the id the archive gave it."""

    baseline_id: uuid.UUID
    revision: BaselineRevision

    @property
    def selection_key(self) -> tuple[datetime, datetime, uuid.UUID]:
        """The deterministic order two revisions of a bucket are ranked by.

        Shared by the in-memory store and the SQL one, and it must stay shared:
        Postgres orders ``uuid`` byte-wise and ``uuid.UUID`` compares by ``int``,
        which is the same order, so ``ORDER BY available_at DESC, window_end
        DESC, id DESC`` and ``max(..., key=selection_key)`` pick the same row.
        """
        return (self.revision.available_at, self.revision.window_end, self.baseline_id)


__all__ = [
    "ALGO_VERSION",
    "COVERAGE_QUANTUM",
    "REASON_INSUFFICIENT_HISTORY",
    "REASON_NO_OBSERVATIONS",
    "STAT_QUANTUM",
    "BaselineGate",
    "BaselineKey",
    "BaselineRevision",
    "BaselineUnavailable",
    "Observation",
    "StoredBaseline",
    "quantize_coverage",
    "quantize_stat",
]
