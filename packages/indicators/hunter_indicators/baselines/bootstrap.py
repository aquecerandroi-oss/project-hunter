"""Seven days of baselines from **persisted candles**, with the T2.2 calculators.

The scanner never calls an exchange (``docs/plans/M2.md`` §REST): a market that
has no baseline yet is bootstrapped from the candles the market-worker already
stored, by replaying :func:`compute_features` once per closed minute. Same
calculators, same context type, same anti-look-ahead cut — which is the only
reason a bootstrap number and a live number can be compared at all.

**What is deliberately left out.** A feature whose inputs are not candles has no
historical source: there is no stored order book, no stored tape. Those features
are excluded with a *structured* reason, not with prose, and the exclusion is
part of the result so the operator can see which baselines are "under
construction" and why:

- ``historical_source_unavailable`` — book, trades and derivative history;
- ``semantic_equivalence_unproven`` — ``trade_velocity_1m``. The joint decision
  admits it only if the candle's ``trade_count`` has the *same semantics and
  window* as the live tape feature, proven byte for byte. It does not: one counts
  exchange-aggregated trades per minute, the other counts tape events in a
  rolling 60 s window (``.claude/state/notes-T2.2.md`` §11);
- ``partial_candle_not_reproducible`` — every ``_live`` feature. Its window
  includes the minute still forming, and a stored candle series cannot say what
  the partial minute looked like at an arbitrary instant.

**Warm-up is not part of the seven days.** ``relative_volume_1h`` needs 1440
prior minutes for each reading, so the candle history handed in has to reach
further back than the window being sampled or the first day silently produces
nothing (Astra, T2.3 design review, item 10).
"""

from __future__ import annotations

import bisect
import uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime

from hunter_core.domain.enums import BaselineSource
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import ensure_utc
from hunter_indicators.baselines.collect import ObservationCollector
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    BaselineRevision,
    BaselineUnavailable,
)
from hunter_indicators.features.context import INPUT_ATR_STATE, INPUT_CANDLES, build_context
from hunter_indicators.features.definitions import LIVE_SUFFIX, FeatureRegistry
from hunter_indicators.features.engine import DEFAULT_REGISTRY, compute_features
from hunter_indicators.features.state import EMPTY_STATE, FeatureState
from hunter_indicators.features.vector import FeatureVector

BOOTSTRAP_ALGO_VERSION = ALGO_VERSION
"""The bootstrap uses the same statistic as the live refresh — the *source*
column is what tells the two apart, not the algorithm."""

REASON_HISTORICAL_SOURCE_UNAVAILABLE = "historical_source_unavailable"
REASON_SEMANTICS_UNPROVEN = "semantic_equivalence_unproven"
REASON_PARTIAL_CANDLE = "partial_candle_not_reproducible"

CANDLE_ONLY_INPUTS = frozenset({INPUT_CANDLES, INPUT_ATR_STATE})
"""What a bootstrap can actually feed: the stored minute series and the ATR
checkpoint the replay itself advances."""

BUFFER_MINUTES = 1500
"""The hot-state ring the live scanner reads (``notes-T2.2.md`` §5). The replay
hands each cut the same depth, or the two paths would see different windows."""

_UNPROVEN_EQUIVALENCE = frozenset({"trade_velocity_1m"})


@dataclass(frozen=True, slots=True)
class BootstrapExclusion:
    """A feature the bootstrap does not produce, and the reason it does not."""

    feature: str
    reason: str


def bootstrap_feature_keys(registry: FeatureRegistry = DEFAULT_REGISTRY) -> tuple[str, ...]:
    """The features a candle replay may legitimately produce, ordered by key."""
    return tuple(
        definition.key
        for definition in registry.definitions()
        if not definition.is_live and set(definition.inputs) <= CANDLE_ONLY_INPUTS
    )


def bootstrap_exclusions(
    registry: FeatureRegistry = DEFAULT_REGISTRY,
) -> tuple[BootstrapExclusion, ...]:
    """Every registered feature that stays "under construction", with its reason."""
    eligible = set(bootstrap_feature_keys(registry))
    out: list[BootstrapExclusion] = []
    for definition in registry.definitions():
        if definition.key in eligible:
            continue
        if definition.key in _UNPROVEN_EQUIVALENCE:
            reason = REASON_SEMANTICS_UNPROVEN
        elif definition.key.endswith(LIVE_SUFFIX):
            reason = REASON_PARTIAL_CANDLE
        else:
            reason = REASON_HISTORICAL_SOURCE_UNAVAILABLE
        out.append(BootstrapExclusion(feature=definition.key, reason=reason))
    return tuple(out)


def replay_vectors(
    *,
    exchange: str,
    symbol: str,
    candles: Sequence[NormalizedCandle],
    cuts: Iterable[datetime],
    registry: FeatureRegistry = DEFAULT_REGISTRY,
    buffer_minutes: int = BUFFER_MINUTES,
) -> Iterator[tuple[FeatureVector, FeatureState]]:
    """One ``(vector, state)`` per cut, exactly as the live engine would produce.

    ``candles`` must be sorted by ``open_time``; each cut sees the same 1500-minute
    depth the hot state would have held, and the ATR checkpoint is carried forward
    across cuts — the anchored recursion is state, and re-anchoring per cut would
    produce a different (and unrepeatable) number.
    """
    ordered = sorted(candles, key=lambda candle: candle.open_time)
    closes = [candle.close_time for candle in ordered]
    state = EMPTY_STATE
    for raw_cut in cuts:
        cut = ensure_utc(raw_cut)
        end = bisect.bisect_right(closes, cut)
        # The ring holds the last ``buffer_minutes`` **entries**, which is not the
        # same as "every close inside the last buffer_minutes": the latter admits
        # 1501 candles on a continuous series, and the replay would then see one
        # minute the live hot state never held (Astra, T2.3 diff review,
        # must-fix 6). Counting entries also matches how the loader decides
        # ``truncated`` (``features/hotstate.py``).
        start = max(0, end - buffer_minutes)
        ctx = build_context(
            exchange=exchange,
            symbol=symbol,
            as_of=cut,
            candles=ordered[start:end],
            candles_truncated=end - start >= buffer_minutes,
        )
        result = compute_features(ctx, state, registry=registry)
        state = result.state
        yield result.vector, state


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """The revisions a bootstrap produced, and everything it refused to produce."""

    revisions: tuple[BaselineRevision | BaselineUnavailable, ...]
    exclusions: tuple[BootstrapExclusion, ...]
    rejections: dict[str, dict[str, int]]
    sampled: int
    """How many cuts were evaluated — the denominator of the rejection counts."""


def bootstrap_observations(
    *,
    market_id: uuid.UUID,
    exchange: str,
    symbol: str,
    candles: Sequence[NormalizedCandle],
    cuts: Iterable[datetime],
    registry: FeatureRegistry = DEFAULT_REGISTRY,
    buffer_minutes: int = BUFFER_MINUTES,
) -> tuple[ObservationCollector, int]:
    """Replay ``cuts`` over ``candles`` into a collector of valid observations."""
    collector = ObservationCollector(market_id, bootstrap_feature_keys(registry))
    sampled = 0
    for vector, _state in replay_vectors(
        exchange=exchange,
        symbol=symbol,
        candles=candles,
        cuts=cuts,
        registry=registry,
        buffer_minutes=buffer_minutes,
    ):
        collector.add(vector)
        sampled += 1
    return collector, sampled


def bootstrap_revisions(
    *,
    market_id: uuid.UUID,
    exchange: str,
    symbol: str,
    candles: Sequence[NormalizedCandle],
    cuts: Iterable[datetime],
    window_start: datetime,
    window_end: datetime,
    available_at: datetime,
    expected_size: int,
    registry: FeatureRegistry = DEFAULT_REGISTRY,
    buffer_minutes: int = BUFFER_MINUTES,
) -> BootstrapResult:
    """The full bootstrap of one market: revisions, exclusions and rejections.

    ``available_at`` is when *this* computation becomes usable, never the age of
    the candles it read.
    """
    collector, sampled = bootstrap_observations(
        market_id=market_id,
        exchange=exchange,
        symbol=symbol,
        candles=candles,
        cuts=cuts,
        registry=registry,
        buffer_minutes=buffer_minutes,
    )
    versions = {
        definition.key: definition.version
        for definition in registry.definitions()
        if definition.key in set(collector.features)
    }
    revisions = collector.revisions(
        window_start=window_start,
        window_end=window_end,
        available_at=available_at,
        source=BaselineSource.BOOTSTRAP,
        expected_size=expected_size,
        feature_versions=versions,
        algo_version=BOOTSTRAP_ALGO_VERSION,
    )
    return BootstrapResult(
        revisions=revisions,
        exclusions=bootstrap_exclusions(registry),
        rejections={feature: dict(reasons) for feature, reasons in collector.rejections().items()},
        sampled=sampled,
    )


__all__ = [
    "BOOTSTRAP_ALGO_VERSION",
    "BUFFER_MINUTES",
    "CANDLE_ONLY_INPUTS",
    "REASON_HISTORICAL_SOURCE_UNAVAILABLE",
    "REASON_PARTIAL_CANDLE",
    "REASON_SEMANTICS_UNPROVEN",
    "BootstrapExclusion",
    "BootstrapResult",
    "bootstrap_exclusions",
    "bootstrap_feature_keys",
    "bootstrap_observations",
    "bootstrap_revisions",
    "replay_vectors",
]
