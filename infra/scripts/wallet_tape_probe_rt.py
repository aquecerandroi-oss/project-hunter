"""Wave 0 of "seguir carteiras que ganham de verdade" — the shared runtime state of the probe's network
half (queues, counters, the independent audits' accumulators). No logic beyond bookkeeping."""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from wallet_tape_probe_core import AMM, PUMP
from wallet_tape_probe_stats import ProbeStats

PUBLIC_WS = "wss://api.mainnet-beta.solana.com"
PUBLIC_HTTP = "https://api.mainnet-beta.solana.com"
PROGRAMS = {"pump": PUMP, "amm": AMM}
BACKOFF_BASE_S, BACKOFF_MAX_S, IDLE_S, QUEUE_MAX = 2.0, 30.0, 60.0, 200_000
AUDIT_SLOT_LAG = 60  # ~24 s behind the HTTP tip
SETTLE_AFTER_S = 180.0  # the verdict on a block comes this long after its fetch
HTTP: Counter[str] = Counter()
HTTP_EVENTS: list[dict[str, Any]] = []


class Runtime:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.t0 = time.time()
        self.stats = ProbeStats(self.t0)
        self.queues: dict[str, asyncio.Queue[tuple[float, str]]] = {}
        self.queue_max: Counter[str] = Counter()
        self.queue_dropped: Counter[str] = Counter()
        self.received: Counter[str] = Counter()  # frames at the socket, before the queue
        self.received_bytes: Counter[str] = Counter()
        self.processed: Counter[str] = Counter()
        self.busy_s: defaultdict[str, float] = defaultdict(float)
        self.malformed: Counter[str] = Counter()
        self.force_reconnect: set[str] = set()
        self.sample_frames: dict[str, list[str]] = {"pump": [], "amm": []}
        self.sample_candidates: deque[tuple[float, str, str, dict[str, int], int]] = deque(
            maxlen=400
        )
        self.sampler: dict[str, Any] = {
            "compared": 0,
            "equal": 0,
            "diff": [],
            "unavailable": 0,
            "slot_delta": Counter(),
        }
        self.sigs: dict[str, dict[int, set[str]]] = {"pump": {}, "amm": {}}
        self.http_tip: int | None = None
        self.slots_per_s: float | None = (
            None  # measured (getRecentPerformanceSamples), never assumed
        )
        self.audit_pending: list[dict[str, Any]] = []
        self.audit: dict[str, Any] = {
            "blocks_requested": 0,
            "blocks_skipped_or_unavailable": 0,
            "blocks_before_both_subscriptions_flowed": 0,
            "pending_censored_at_end": 0,
            "at_fetch": {sub: {"txs": 0, "received": 0} for sub in PROGRAMS},
            "settled": {"clean": _audit_bucket(), "affected_by_reconnect": _audit_bucket()},
            "truth": {
                "blocks_ok": 0,
                **{sub: {"txs": 0, "success_txs": 0, "events": {}} for sub in PROGRAMS},
            },
            "per_block": [],  # [slot, tainted, [pump txs, missed settled, missed at fetch], [amm ...]]
            "missed_examples": [],
        }
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)


def _audit_bucket() -> dict[str, Any]:
    return {
        "blocks": 0,
        **{sub: {"txs": 0, "received": 0, "missed": 0, "missed_failed": 0} for sub in PROGRAMS},
    }
