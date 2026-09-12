"""Per-source liveness and budget — the numbers ``hb:meme:radar`` carries since
T4.2c and ``GET /meme/sources`` renders. Pure: no IO, injectable clock.

The adendo's finding was that the heartbeat had ``ts/last_success/errors/version``
and nothing an operator could read a degraded source from. Every counter here
answers one question over a **sliding window** (:class:`RollingCounter`): how many
requests did a budget spend in the last 60 s, how many frames were malformed, how
many errors in the last hour, how far behind the source's clock is ours. A source
that is switched off says ``enabled = false``; a source that never spoke says
``last_observed_at = null`` — never a zero that looks like health.

``RollingCounter``/``SourceStats`` moved to ``source_stats.py`` in T4.16b (the
350-line budget) and are re-exported here so nothing that imported them from
this module has to move.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from hunter_meme_worker.source_stats import RollingCounter, SourceStats, iso_or_none

__all__ = ["RollingCounter", "SourceStats", "SourcesState"]

PUMPPORTAL_WS = "pumpportal_ws"
PUMPFUN_REST = "pumpfun_rest"
SOLANA_RPC = "solana_rpc"
TRENCHES_WS = "trenches_ws"
SWAP_API = "swap_api"
INDEXER_RISK = "indexer_risk"
SOURCE_NAMES: tuple[str, ...] = (
    PUMPPORTAL_WS,
    PUMPFUN_REST,
    SOLANA_RPC,
    TRENCHES_WS,
    SWAP_API,
    INDEXER_RISK,
)


def _pct(part: int | None, whole: int | None) -> float | None:
    """``part`` over ``whole`` in percent, one decimal; unknown (or an empty
    minute) is ``None`` — never a ``0`` that reads as "nothing covered"."""
    if part is None or not whole:
        return None
    return round(100.0 * part / whole, 1)


@dataclass
class SourcesState:
    """Every source the radar has, plus the three radar-wide rolling counts."""

    sources: dict[str, SourceStats] = field(
        default_factory=lambda: {name: SourceStats(name) for name in SOURCE_NAMES}
    )
    gaps_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    ws_malformed_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    trenches_patches_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    new_board_entries_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    new_board_non_pump_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    """The declared blindness (T4.2d, item 3): listings on the site's ``new``
    board in the last hour, and how many of them run on a program other than
    ``pump`` — coins ``subscribeNewToken`` never announces and this radar never
    tracks, by construction (8/50 were ``raydium_launchpad`` at 05:51 BRT)."""
    last_snapshot_observed_at: datetime | None = None
    last_snapshot_received_at: datetime | None = None
    fold_minute: datetime | None = None
    fold_rows: int | None = None
    fold_rows_with_tape: int | None = None
    fold_rows_with_progress: int | None = None
    """T4.2e: the last folded minute and how many of its rows carried a tape
    and a progress — ``tape_coverage_pct``/``progress_coverage_pct`` in the
    heartbeat. ``None`` until the first fold: an unknown, never ``0 %``."""
    tape_cycle_s: float | None = None
    tape_planned: int | None = None
    tape_tracked_mints: int | None = None
    tape_covered_mints: int | None = None
    tape_never_pulled: int | None = None
    tape_deferred_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    """The tape puller's last cycle (``trades.py``): how long it took, how many
    mints it planned, how many of the tracked set are covered, and how many
    due mints the cap left out in the last minute (each ``not_polled``)."""
    mayhem_pending: int | None = None
    mayhem_written_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    mayhem_refused_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    """The Mayhem loop (``mayhem.py``): tracked Mayhem mints still without a
    denominator, denominators written in the last minute, refusals in the hour."""
    chain_cycle_s: float | None = None
    chain_tracked_mints: int | None = None
    chain_read_mints: int | None = None
    chain_calls_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    chain_refused_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    chain_block_time_missing_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    """The chain loop (T4.2f, ``chain.py``): the last cycle's duration, how many
    mints it asked for and read, RPC calls in the minute, refusals in the hour,
    readings whose slot had no block time (``observed_at = received_at``)."""
    swap_api_effective_budget_60s: int | None = None
    swap_api_measured_60s: int | None = None
    swap_api_429_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    swap_api_blocked_until: datetime | None = None
    """The tape budget as the edge enforces it (T4.2f, ``tape_budget.py``): the
    effective budget, the successes counted before the last real 429, real 429s
    in the hour, and until when the IP is blocked."""
    fast_lane_mints: int | None = None
    fast_lane_cycle_s: float | None = None
    fast_lane_reads_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    fast_lane_calls_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    tracked_pinned: int | None = None
    tracked_capped_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    """T4.16b: how many of the tracked set are pinned right now (an open paper
    bet, an open live position or a pending proposal — never evicted by the
    cap or the window, ``tracker.py``), and how many *un*-pinned mints the cap
    dropped in the last minute (``tracker.prune``'s ``capped``)."""
    _sampled: dict[str, int] = field(default_factory=dict[str, int])

    def __getitem__(self, name: str) -> SourceStats:
        return self.sources[name]

    def record_fold(
        self, minute: datetime, *, rows: int, with_tape: int, with_progress: int
    ) -> None:
        self.fold_minute = minute
        self.fold_rows = rows
        self.fold_rows_with_tape = with_tape
        self.fold_rows_with_progress = with_progress

    def record_tape_cycle(
        self,
        at: datetime,
        *,
        duration_s: float,
        planned: int,
        deferred: int,
        tracked: int,
        covered: int,
        never_pulled: int,
    ) -> None:
        self.tape_cycle_s = duration_s
        self.tape_planned = planned
        self.tape_tracked_mints = tracked
        self.tape_covered_mints = covered
        self.tape_never_pulled = never_pulled
        self.tape_deferred_60s.add(at, deferred)

    def record_chain_cycle(
        self,
        at: datetime,
        *,
        duration_s: float,
        tracked: int,
        read: int,
        calls: int,
        refused: int,
        block_time_missing: int,
    ) -> None:
        self.chain_cycle_s = duration_s
        self.chain_tracked_mints = tracked
        self.chain_read_mints = read
        self.chain_calls_60s.add(at, calls)
        self.chain_refused_1h.add(at, refused)
        self.chain_block_time_missing_60s.add(at, block_time_missing)

    def record_tape_budget(
        self,
        at: datetime,
        *,
        effective: int,
        measured: int | None,
        refused_429: int,
        blocked_until: datetime | None,
    ) -> None:
        self.swap_api_effective_budget_60s = effective
        self.swap_api_measured_60s = measured
        self.swap_api_429_1h.add(at, refused_429)
        self.swap_api_blocked_until = blocked_until

    def record_fast_cycle(
        self, at: datetime, *, mints: int, read: int, calls: int, duration_s: float
    ) -> None:
        self.fast_lane_mints = mints
        self.fast_lane_cycle_s = duration_s
        self.fast_lane_reads_60s.add(at, read)
        self.fast_lane_calls_60s.add(at, calls)

    def record_tracker_prune(self, at: datetime, *, pinned: int, capped: int) -> None:
        """T4.16b: the poll loop's own ``tracker.prune`` — a gauge (how many
        pinned mints the tracker holds right now) beside a rolling count (how
        many un-pinned mints the cap dropped in the last minute)."""
        self.tracked_pinned = pinned
        self.tracked_capped_60s.add(at, capped)

    def record_new_listing(self, at: datetime, *, in_scope: bool) -> None:
        """One first sighting on the ``new`` board; ``in_scope`` = program ``pump``."""
        self.new_board_entries_1h.add(at)
        if not in_scope:
            self.new_board_non_pump_1h.add(at)

    def blind_share_1h(self, now: datetime) -> float | None:
        """Non-``pump`` listings over all listings in the last hour; ``None`` when
        the board listed nothing — an empty hour is unknown, not full coverage."""
        total = self.new_board_entries_1h.total(now)
        if total == 0:
            return None
        return round(self.new_board_non_pump_1h.total(now) / total, 4)

    def sample_counter(self, key: str, value: int, at: datetime, into: RollingCounter) -> int:
        """Turn a monotonic counter (a client's ``state.malformed``) into events:
        the increase since the last sample lands in the rolling window."""
        previous = self._sampled.get(key, 0)
        delta = max(0, value - previous)
        self._sampled[key] = value
        into.add(at, delta)
        return delta

    def record_snapshot(self, *, observed_at: datetime, received_at: datetime) -> None:
        if self.last_snapshot_observed_at is None or observed_at >= self.last_snapshot_observed_at:
            self.last_snapshot_observed_at = observed_at
            self.last_snapshot_received_at = received_at

    def heartbeat_fields(self, now: datetime, *, tracked: int) -> dict[str, str]:
        """The flat fields the adendo names, plus one JSON field per source."""
        lag = (
            None
            if self.last_snapshot_observed_at is None or self.last_snapshot_received_at is None
            else round(
                (self.last_snapshot_received_at - self.last_snapshot_observed_at).total_seconds(),
                3,
            )
        )
        trenches = self.sources[TRENCHES_WS]
        fields: dict[str, object] = {
            "tracked": tracked,
            "budget_used_60s": self.sources[PUMPFUN_REST].used_60s.total(now),
            "budget_60s": self.sources[PUMPFUN_REST].budget_60s,
            "gaps_60s": self.gaps_60s.total(now),
            "ws_malformed_60s": self.ws_malformed_60s.total(now),
            "last_snapshot_observed_at": iso_or_none(self.last_snapshot_observed_at),
            "lag_s": lag,
            "trenches_connected": "disabled"
            if not trenches.enabled
            else ("true" if trenches.connected else "false"),
            "trenches_patches_60s": self.trenches_patches_60s.total(now),
            "swap_api_used_60s": self.sources[SWAP_API].used_60s.total(now),
            "swap_api_budget_60s": self.sources[SWAP_API].budget_60s,
            "new_board_entries_1h": self.new_board_entries_1h.total(now),
            "new_board_non_pump_1h": self.new_board_non_pump_1h.total(now),
            "blind_share_1h": self.blind_share_1h(now),
            # T4.2e: the coverage of the last folded minute and the tape cycle.
            "progress_coverage_pct": _pct(self.fold_rows_with_progress, self.fold_rows),
            "tape_coverage_pct": _pct(self.fold_rows_with_tape, self.fold_rows),
            "fold_minute": iso_or_none(self.fold_minute),
            "fold_rows": self.fold_rows,
            "tape_cycle_s": self.tape_cycle_s,
            "tape_planned": self.tape_planned,
            "tape_tracked_mints": self.tape_tracked_mints,
            "tape_covered_mints": self.tape_covered_mints,
            "tape_never_pulled": self.tape_never_pulled,
            "tape_deferred_60s": self.tape_deferred_60s.total(now),
            "mayhem_pending": self.mayhem_pending,
            "mayhem_written_60s": self.mayhem_written_60s.total(now),
            "mayhem_refused_1h": self.mayhem_refused_1h.total(now),
            # T4.2f: the chain loop and the tape budget as the edge enforces it.
            "chain_cycle_s": self.chain_cycle_s,
            "chain_tracked_mints": self.chain_tracked_mints,
            "chain_read_mints": self.chain_read_mints,
            "chain_calls_60s": self.chain_calls_60s.total(now),
            "chain_refused_1h": self.chain_refused_1h.total(now),
            "chain_block_time_missing_60s": self.chain_block_time_missing_60s.total(now),
            "swap_api_effective_budget_60s": self.swap_api_effective_budget_60s,
            "swap_api_measured_60s": self.swap_api_measured_60s,
            "swap_api_429_1h": self.swap_api_429_1h.total(now),
            "swap_api_blocked_until": iso_or_none(self.swap_api_blocked_until),
            "fast_lane_mints": self.fast_lane_mints,
            "fast_lane_cycle_s": self.fast_lane_cycle_s,
            "fast_lane_reads_60s": self.fast_lane_reads_60s.total(now),
            "fast_lane_calls_60s": self.fast_lane_calls_60s.total(now),
            # T4.16b: the pinned set the tracker's cap and window may not touch.
            "tracked_pinned": self.tracked_pinned,
            "tracked_capped_60s": self.tracked_capped_60s.total(now),
            "sources_at": now.isoformat(),
            "sources": json.dumps(
                {name: stats.as_fields(now) for name, stats in self.sources.items()},
                sort_keys=True,
            ),
        }
        return {key: "" if value is None else str(value) for key, value in fields.items()}
