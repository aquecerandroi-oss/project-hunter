"""The instantaneous features of a coin younger than five minutes (T4.16,
EXP-M5 — "o relógio de 15 s nos primeiros 5 minutos").

A 15-second photo of the curve is not a minute, so this module folds the
**series of photos of the last 120 s** into what the gate needs to judge one
photo, as pure functions of points that carry both clocks:

- ``mcap_delta_60s`` — market cap of the newest photo minus the market cap of
  the newest photo observed **at least 60 s before it** (the reference);
- ``mcap_slope_60s`` — the OLS slope of ``ln(mcap)`` against minutes over the
  photos between the reference and the newest one (a growth fraction per
  minute, :func:`hunter_indicators.meme.lines.log_slope`);
- ``progress_delta_60s`` — curve progress of the newest photo minus the
  progress at the reference, both ``1 − real/initial`` over the observed
  denominator (never a constant), and ``progress_rising`` = that delta > 0;
- ``holders_rising`` — the newest holders reading above the one before it
  ("holders crescendo em duas leituras seguidas").

**Non-anticipation is decided here.** Every point and every reading carries
``received_at``; one that reached us after ``as_of`` is not an input of that
instant, however early its ``observed_at`` says the curve was read — the rule
the tape, the boards and the lines already follow. ``test_meme_fast.py``
proves it: a photo received one second after ``as_of`` changes nothing.

Every ``None`` has a name (``window_reason`` / ``progress_reason`` /
``holders_reason``): ``no_snapshot`` (no usable photo by ``as_of``),
``too_few_points`` (no photo at least 60 s before the newest one — the window
is not a minute yet), ``out_of_range`` (a slope the column cannot hold),
``denominator_unknown``, ``no_holders_reader``, ``too_few_readings``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.definitions import FeatureDefinition
from hunter_indicators.meme.lines import LinePoint, log_slope

__all__ = [
    "DELTA_S",
    "DENOMINATOR_UNKNOWN",
    "FAST_DEFINITIONS",
    "FAST_REASONS",
    "NO_HOLDERS_READER",
    "NO_SNAPSHOT",
    "OUT_OF_RANGE",
    "TOO_FEW_POINTS",
    "TOO_FEW_READINGS",
    "WINDOW_S",
    "FastFeatures",
    "FastPoint",
    "HoldersPoint",
    "HoldersTrend",
    "compute_fast",
    "holders_trend",
    "usable_fast_points",
]

WINDOW_S: Final = 120
DELTA_S: Final = 60
"""The brief's frozen windows: the series of the last 60/120 s."""

NO_SNAPSHOT: Final = "no_snapshot"
TOO_FEW_POINTS: Final = "too_few_points"
OUT_OF_RANGE: Final = "out_of_range"
DENOMINATOR_UNKNOWN: Final = "denominator_unknown"
NO_HOLDERS_READER: Final = "no_holders_reader"
TOO_FEW_READINGS: Final = "too_few_readings"
FAST_REASONS: Final = frozenset(
    {
        NO_SNAPSHOT,
        TOO_FEW_POINTS,
        OUT_OF_RANGE,
        DENOMINATOR_UNKNOWN,
        NO_HOLDERS_READER,
        TOO_FEW_READINGS,
    }
)

_MONEY = Decimal("0.0000000001")
_FRACTION = Decimal("0.000001")

_INPUTS: Final = (
    "meme_curve_snapshots.mcap_sol",
    "meme_curve_snapshots.real_token_reserves",
    "meme_curve_snapshots.observed_at",
    "meme_curve_snapshots.received_at",
    "meme_tokens.initial_real_token_reserves",
    "meme_board_observations.holders",
    "meme_risk_snapshots.holders",
)
_PARAMS: Final = {"window_s": WINDOW_S, "delta_s": DELTA_S}


def _definition(key: str, category: FeatureCategory, description: str) -> FeatureDefinition:
    return FeatureDefinition(
        key=key,
        version=1,
        category=category,
        inputs=_INPUTS,
        description=description,
        params=_PARAMS,
    )


FAST_DEFINITIONS: Final[tuple[FeatureDefinition, ...]] = (
    _definition(
        "mcap_delta_60s",
        FeatureCategory.PRICE,
        "Market cap of the newest photo minus that of the newest photo at least 60 s older, "
        "over photos received by as_of (SOL).",
    ),
    _definition(
        "mcap_slope_60s",
        FeatureCategory.MOMENTUM,
        "OLS slope of ln(mcap_sol) against minutes between the 60 s reference and the newest "
        "photo (fraction/min).",
    ),
    _definition(
        "progress_delta_60s",
        FeatureCategory.PRICE,
        "Curve progress (1 - real/initial, observed denominator) of the newest photo minus the "
        "progress at the 60 s reference (fraction).",
    ),
    _definition(
        "holders_rising",
        FeatureCategory.MICROSTRUCTURE,
        "The newest holders reading received by as_of is above the reading before it.",
    ),
)
"""Registered as features are (key, version, params, description, inputs):
a different window is a different version, never an edit."""


@dataclass(frozen=True, slots=True)
class FastPoint:
    """One curve photo as the 15-second series reads it."""

    observed_at: datetime
    received_at: datetime
    mcap_sol: Decimal | None
    real_token_reserves: Decimal | None = None


@dataclass(frozen=True, slots=True)
class HoldersPoint:
    """One holders reading (a board entry or a risk read) with its two clocks."""

    observed_at: datetime
    received_at: datetime
    holders: int | None


@dataclass(frozen=True, slots=True)
class FastFeatures:
    """One instant's worth of columns — every ``None`` beside its reason."""

    snapshot_observed_at: datetime | None
    snapshots_120s: int
    mcap_sol: Decimal | None
    mcap_delta_60s: Decimal | None
    mcap_slope_60s: Decimal | None
    window_reason: str | None
    curve_progress_pct: Decimal | None
    progress_delta_60s: Decimal | None
    progress_rising: bool | None
    progress_reason: str | None


@dataclass(frozen=True, slots=True)
class HoldersTrend:
    holders: int | None
    holders_prev: int | None
    holders_rising: bool | None
    holders_reason: str | None


def usable_fast_points(points: Sequence[FastPoint], *, as_of: datetime) -> list[FastPoint]:
    """Photos that had **reached us** by ``as_of`` with a positive market cap,
    inside ``(newest − WINDOW_S, newest]``, one per instant (last received wins)."""
    by_instant: dict[datetime, FastPoint] = {}
    for point in sorted(points, key=lambda p: (p.observed_at, p.received_at)):
        if point.received_at > as_of or point.mcap_sol is None or point.mcap_sol <= 0:
            continue
        by_instant[point.observed_at] = point
    if not by_instant:
        return []
    newest = max(by_instant)
    start = newest - timedelta(seconds=WINDOW_S)
    return [by_instant[t] for t in sorted(by_instant) if start < t <= newest]


def _progress(point: FastPoint, initial: Decimal | None) -> Decimal | None:
    if initial is None or initial == 0 or point.real_token_reserves is None:
        return None
    return (Decimal(1) - point.real_token_reserves / initial).quantize(_FRACTION, ROUND_HALF_EVEN)


def compute_fast(
    points: Sequence[FastPoint], *, as_of: datetime, initial_real_token_reserves: Decimal | None
) -> FastFeatures:
    """Fold the series known at ``as_of``. Total: every input yields a row."""
    window = usable_fast_points(points, as_of=as_of)
    if not window:
        return FastFeatures(None, 0, None, None, None, NO_SNAPSHOT, None, None, None, NO_SNAPSHOT)
    newest = window[-1]
    assert newest.mcap_sol is not None
    mcap = newest.mcap_sol.quantize(_MONEY, ROUND_HALF_EVEN)
    progress = _progress(newest, initial_real_token_reserves)
    progress_reason = None if progress is not None else DENOMINATOR_UNKNOWN
    cutoff = newest.observed_at - timedelta(seconds=DELTA_S)
    references = [p for p in window if p.observed_at <= cutoff]
    if not references:
        return FastFeatures(
            newest.observed_at,
            len(window),
            mcap,
            None,
            None,
            TOO_FEW_POINTS,
            progress,
            None,
            None,
            progress_reason or TOO_FEW_POINTS,
        )
    reference = references[-1]
    assert reference.mcap_sol is not None
    delta = (newest.mcap_sol - reference.mcap_sol).quantize(_MONEY, ROUND_HALF_EVEN)
    slope = log_slope(
        [
            LinePoint(p.observed_at, p.received_at, p.mcap_sol)
            for p in window
            if p.observed_at >= reference.observed_at
        ],
        origin=reference.observed_at,
    )
    if slope is None:
        delta, window_reason = None, OUT_OF_RANGE
    else:
        window_reason = None
    progress_ref = _progress(reference, initial_real_token_reserves)
    if progress is None or progress_ref is None:
        progress_delta, rising = None, None
    else:
        progress_delta = (progress - progress_ref).quantize(_FRACTION, ROUND_HALF_EVEN)
        rising = progress_delta > 0
    return FastFeatures(
        snapshot_observed_at=newest.observed_at,
        snapshots_120s=len(window),
        mcap_sol=mcap,
        mcap_delta_60s=delta,
        mcap_slope_60s=slope,
        window_reason=window_reason,
        curve_progress_pct=progress,
        progress_delta_60s=progress_delta,
        progress_rising=rising,
        progress_reason=progress_reason,
    )


def holders_trend(readings: Sequence[HoldersPoint], *, as_of: datetime) -> HoldersTrend:
    """The last two holders readings received by ``as_of`` (distinct instants),
    and whether the newest is above the previous one."""
    usable = sorted(
        (r for r in readings if r.received_at <= as_of and r.holders is not None),
        key=lambda r: (r.observed_at, r.received_at),
    )
    by_instant: dict[datetime, HoldersPoint] = {r.observed_at: r for r in usable}
    ordered = [by_instant[t] for t in sorted(by_instant)]
    if not ordered:
        return HoldersTrend(None, None, None, NO_HOLDERS_READER)
    newest = ordered[-1]
    if len(ordered) < 2:
        return HoldersTrend(newest.holders, None, None, TOO_FEW_READINGS)
    previous = ordered[-2]
    assert newest.holders is not None and previous.holders is not None
    return HoldersTrend(newest.holders, previous.holders, newest.holders > previous.holders, None)
