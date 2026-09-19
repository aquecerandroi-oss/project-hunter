"""T4.67b — the counters of the launch lane and their heartbeat fields.

One object per process (``ExecutorContext.launch``), written by
``launch_entries.py`` / ``exit_settle.py`` and read by ``heartbeat.py``:
``launch_lane_mode`` (what the flag reads), ``launch_open`` (launch positions
open now, from the rows), ``launch_buys_total`` / ``launch_sells_total``
(confirmed fills of this process), ``proposal_to_submit_ms_p50`` / ``_p95``
(``meme_proposals.proposed_at`` → the buy's ``submitted_at``, launch only — the
number EXP-M18 lives or dies by), ``launch_refusals`` by reason and the
blockhash cache's own four numbers. Memory only, bounded; a restart starts at
zero, never at a guess.
"""

from __future__ import annotations

import json
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_meme_executor.event_exits_stats import percentile
from hunter_meme_executor.launch_send import BlockhashCache

if TYPE_CHECKING:
    from hunter_meme_executor.launch_config import LaunchConfig
    from hunter_risk_meme import MemeLimits

__all__ = ["LaunchStats", "launch_heartbeat_fields"]

_LATENCY_MAXLEN = 200


@dataclass(slots=True)
class LaunchStats:
    seen_total: int = 0
    """Launch proposals this process picked up (``on`` only)."""
    buys_total: int = 0
    sells_total: int = 0
    refusals: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    claim_lost_total: int = 0
    """Proposals another writer moved first (the claim's rowcount was 0)."""
    submit_latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=_LATENCY_MAXLEN))
    blockhash: BlockhashCache = field(default_factory=BlockhashCache)

    def record_refusal(self, reason: str) -> None:
        self.refusals[reason] = self.refusals.get(reason, 0) + 1

    def record_submit_latency_ms(self, ms: float) -> None:
        self.submit_latencies_ms.append(max(0.0, ms))


def launch_heartbeat_fields(
    stats: LaunchStats,
    config: LaunchConfig,
    *,
    now: datetime,
    open_launch: int,
    limits: MemeLimits | None = None,
) -> dict[str, str]:
    """The ``launch_*`` fields of ``hb:meme:executor`` — published in every
    mode, so a desk that expects them sees ``off``, not "missing"."""
    latencies = list(stats.submit_latencies_ms)
    fields = {
        "launch_lane_mode": config.mode,
        "launch_open": str(open_launch),
        "launch_seen_total": str(stats.seen_total),
        "launch_buys_total": str(stats.buys_total),
        "launch_sells_total": str(stats.sells_total),
        "launch_claim_lost_total": str(stats.claim_lost_total),
        "proposal_to_submit_ms_p50": (
            "" if not latencies else f"{statistics.median(latencies):.0f}"
        ),
        "proposal_to_submit_ms_p95": "" if not latencies else f"{percentile(latencies, 0.95):.0f}",
        "launch_refusals": json.dumps(stats.refusals, sort_keys=True),
        "launch_config": json.dumps(config.as_json(limits), sort_keys=True),
    }
    fields.update(stats.blockhash.describe(now))
    return fields
