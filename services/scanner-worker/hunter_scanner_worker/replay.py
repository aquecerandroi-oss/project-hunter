"""Replaying the candles we already have into baseline revisions, one market at a time.

Without this a fresh install is a week away from its first anomaly, and the
operational proof of T2.5 showed exactly that: 30 minutes of real data, zero
usable baselines, zero scores, zero Radar rows — all of it correct behaviour of a
pipeline with nothing to compare against (``.claude/state/t25-proof.md`` §5).

Two properties this module exists to hold:

**One pass per minute, not one per feature.** ``replay_vectors`` computes the
whole vector once per cut and a single :class:`ObservationCollector` fans it out
to every bucket, so the cost is proportional to the number of *minutes* replayed
and not to features × minutes. Nothing here loops over features.

**Cooperative, because the loop it shares is already saturated.** A market is
10 080 cuts and a cut costs tens of milliseconds, so the replay yields on a
wall-clock budget checked *per vector* (``settings.slice_s``) and then sleeps for
the complement of its duty cycle. Blocking the event loop for a whole market
would stall the consumers, the persistence cycle and ``/ready`` — the bootstrap
must never be the reason live evaluation stops.

The replay starts from ``EMPTY_STATE`` while the live scanner carries its own ATR
checkpoint, so the two anchors differ. Wilder's recursion forgets its seed
geometrically (13/14 per 15-minute bar): after the warm-up prefix the seed's
weight is already below 10⁻³ and after a day it is numerically gone. The
bootstrap therefore never writes its replay state into the live checkpoint — the
anchors are allowed to differ, the *numbers* converge, and claiming byte equality
would be a claim nobody proved (Astra, T2.5b design review, must-fix 5).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.enums import BaselineSource
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_indicators.baselines import BaselineRevision, ObservationCollector
from hunter_indicators.baselines.bootstrap import (
    BOOTSTRAP_ALGO_VERSION,
    bootstrap_feature_keys,
    replay_vectors,
)
from hunter_indicators.features import DEFAULT_REGISTRY
from hunter_scanner_worker.bootstrap import (
    BootstrapSettings,
    BootstrapWindow,
)
from hunter_scanner_worker.metrics import (
    scanner_bootstrap_cuts_total,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hunter_core.domain.market import NormalizedCandle
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

__all__ = ["BootstrapJob"]


_IDLE_S = 0.05
"""How long a suspended replay sleeps between two looks at the backlog when the
duty cycle leaves no pause of its own (``duty = 1``)."""


class BootstrapJob:
    """One market's replay, resumable across slices so the loop stays responsive."""

    __slots__ = (
        "_collector",
        "_cuts",
        "_finished",
        "_reported",
        "_vectors",
        "candles",
        "gaps",
        "ref",
        "settings",
        "total_cuts",
        "window",
    )

    def __init__(
        self,
        ref: MarketRef,
        *,
        window: BootstrapWindow,
        settings: BootstrapSettings,
        candles: Sequence[NormalizedCandle],
        gaps: Sequence[tuple[datetime, datetime]] = (),
    ) -> None:
        self.ref = ref
        self.window = window
        self.settings = settings
        self.candles = candles
        self.gaps = tuple(gaps)
        self.total_cuts = int((window.end - window.start).total_seconds() // 60)
        self._cuts = 0
        self._reported = 0
        self._finished = False
        self._collector = ObservationCollector(ref.market_id, bootstrap_feature_keys())
        self._vectors = replay_vectors(
            exchange=ref.exchange,
            symbol=ref.symbol,
            candles=candles,
            cuts=window.cuts(),
            buffer_minutes=settings.buffer_minutes,
        )

    @property
    def cuts_done(self) -> int:
        return self._cuts

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def progress(self) -> float:
        return 0.0 if not self.total_cuts else self._cuts / self.total_cuts

    async def run_slice(
        self, budget_s: float | None = None, *, pressure: Callable[[], bool] | None = None
    ) -> bool:
        """Replay for at most ``budget_s`` of wall time. ``True`` when finished.

        ``pressure`` is asked at every cooperative boundary -- including before
        the first cut -- whether the evaluation loop is behind; while it says so
        the replay sleeps instead of taking its duty share. Checking only on
        entry would let a visit hold its 120 s budget through a backlog that
        started one cut later (Astra, T2.5c design review).
        """
        started = time.perf_counter()
        if await self._stand_aside(pressure, started, budget_s):
            return False
        slice_started = time.perf_counter()
        for vector, _state in self._vectors:
            self._collector.add(vector)
            self._cuts += 1
            now = time.perf_counter()
            if now - slice_started < self.settings.slice_s:
                continue
            if budget_s is not None and now - started >= budget_s:
                self._report_cuts()
                return False
            await asyncio.sleep(self.settings.pause_s)
            if await self._stand_aside(pressure, started, budget_s):
                return False
            slice_started = time.perf_counter()
        self._finished = True
        self._report_cuts()
        return True

    async def _stand_aside(
        self, pressure: Callable[[], bool] | None, started: float, budget_s: float | None
    ) -> bool:
        """Sleep while the live loop is late. ``True`` when this visit is over.

        The job itself is untouched: the generator and the collector survive, so
        coming back costs nothing and re-anchors nothing.
        """
        if pressure is None:
            return False
        while pressure():
            self._report_cuts()
            if budget_s is None or time.perf_counter() - started >= budget_s:
                return True
            await asyncio.sleep(self.settings.pause_s or _IDLE_S)
        return False

    def _report_cuts(self) -> None:
        """Only the cuts this slice added. A counter is monotonic, not cumulative:
        incrementing by the running total once per slice would multiply the cost
        of every market that took more than one."""
        scanner_bootstrap_cuts_total.inc(self._cuts - self._reported)
        self._reported = self._cuts

    def revisions(self, *, available_at: datetime) -> tuple[BaselineRevision, ...]:
        """The revisions of every non-empty bucket, dropping the unavailable ones.

        ``available_at`` is when *this* computation becomes usable — never
        back-dated to the age of the candles it read (``docs/DATABASE.md``
        section 17.2).
        """
        versions = {
            definition.key: definition.version
            for definition in DEFAULT_REGISTRY.definitions()
            if definition.key in set(self._collector.features)
        }
        produced = self._collector.revisions(
            window_start=self.window.start,
            window_end=self.window.end,
            available_at=ensure_utc(available_at),
            source=BaselineSource.BOOTSTRAP,
            expected_size=self.settings.expected_size,
            feature_versions=versions,
            algo_version=BOOTSTRAP_ALGO_VERSION,
        )
        return tuple(item for item in produced if isinstance(item, BaselineRevision))

    def rejections(self) -> dict[str, dict[str, int]]:
        return {feature: dict(reasons) for feature, reasons in self._collector.rejections().items()}
