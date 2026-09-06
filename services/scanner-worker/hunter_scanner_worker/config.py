"""What the scanner runs on: cadences, consumer groups and the exchange.

Every number here is a **cadence**, never a threshold: the thresholds that decide
a stage, a status or an anomaly are versioned in ``opportunity_weights`` and read
by the pure engines (T2.2-T2.4). Changing anything in this file changes how often
the scanner looks, never what it concludes.

The cadences are the joint M2 decision's (``docs/plans/M2.md``, "Custo"):
tick features throttled to 1 s per *dirty* market, the scorer to 2 s, the regime
every minute, the minute snapshot at the minute close. The persist cycle is the
one addition: writes are batched into a single transaction per second so 200
markets cost one transaction, not two hundred.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_EXCHANGE_CODE = "binance"

CONSUMER_GROUP = "scanner-worker"
"""Base name; each stream gets ``scanner-worker.<stream>`` so one slow stream
cannot hold back the pending list of another."""


def exchange_code() -> str:
    """Which exchange this scanner evaluates (``MARKET_EXCHANGE_CODE``)."""
    return os.environ.get("MARKET_EXCHANGE_CODE", DEFAULT_EXCHANGE_CODE).strip().lower()


def group_for(stream: str) -> str:
    return f"{CONSUMER_GROUP}.{stream}"


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    """Cadences and budgets. Immutable; built once at startup."""

    exchange: str = DEFAULT_EXCHANGE_CODE

    feature_throttle_s: float = 1.0
    """Minimum interval between two feature vectors of the same market."""

    score_throttle_s: float = 2.0
    """Minimum interval between two scores of the same market."""

    cycle_s: float = 0.25
    """How often the evaluation loop wakes. Below the throttles on purpose: the
    loop's job is to notice a market became dirty, and the throttles decide
    whether it is due. A 1 s loop would add up to 1 s of pure waiting to the
    tick->opportunity budget before any work started (Astra, design review:
    independent timers must not each spend the p99 budget)."""

    persist_s: float = 1.0
    regime_s: float = 60.0
    watchdog_s: float = 60.0
    baseline_check_s: float = 300.0
    """How often the hourly refresh checks whether an hour has closed."""

    registry_refresh_s: float = 300.0
    heartbeat_s: float = 5.0

    consume_block_ms: int = 2_000
    """Under ``hunter_core.redis``'s 5 s socket timeout: a block that runs its
    whole budget on a quiet stream would expire the read deadline itself."""

    max_markets: int = 400
    """Guard rail on the evaluated universe. 200 is the configured size; twice
    that is a bug somewhere upstream, and evaluating it silently would blow the
    latency budget instead of saying so."""

    backfill_days: int = 7
    """History the baseline bootstrap wants before it declares a bucket."""


__all__ = ["CONSUMER_GROUP", "DEFAULT_EXCHANGE_CODE", "ScannerConfig", "exchange_code", "group_for"]
