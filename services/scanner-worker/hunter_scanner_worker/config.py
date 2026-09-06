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

    consume_batch: int = 500
    """Messages one ``XREADGROUP`` of a notification stream may bring back.

    A ceiling, not a wait: the read returns what is there. The number is what
    the T2.5c measurement asks for -- 151 ticks/s produced against 71 consumed,
    a backlog of ~95 000 -- and at one round trip per batch it drains that
    backlog in seconds instead of never. Handling stays a dict touch per market
    after coalescence, so a full batch is microseconds of work, far inside the
    30 s idle time that would let another consumer reclaim it."""

    max_markets: int = 400
    """Guard rail on the evaluated universe. 200 is the configured size; twice
    that is a bug somewhere upstream, and evaluating it silently would blow the
    latency budget instead of saying so."""

    backfill_days: int = 7
    """History the baseline bootstrap wants before it declares a bucket."""

    baseline_window_days: int = 7
    """Days of history a baseline bucket is computed from. 420 observations per
    ``(market, feature, UTC hour)`` — the joint M2 decision's expected size."""

    bootstrap_budget_s: float = 120.0
    """Wall time one visit spends on one market's replay before the loop looks at
    the clock again. It bounds how late the hourly refresh can be, which is the
    only reason the bootstrap is sliced at all."""

    bootstrap_duty: float = 0.4
    """Share of wall time the replay may hold. A market is ~10 000 cuts at tens of
    milliseconds each; taking the whole loop would stall live evaluation for
    minutes, and taking too little would never finish. Overridable per deployment
    (``SCANNER_BOOTSTRAP_DUTY``) because the right split depends on how far behind
    the live loop already is."""

    baseline_ready_ratio: float = 0.80
    """Share of the universe that must have a *declared* baseline state — usable
    or under construction with a reason — for readiness to go green."""

    deriv_refresh_s: float = 300.0
    """How often the durable open-interest history is re-read. The collector
    samples every 5 minutes, so anything faster only re-reads the same rows."""


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _clamped_duty(raw: float) -> float:
    """``duty`` outside ``(0, 1]`` is a typo, not a policy: 0 divides by zero."""
    return min(1.0, max(0.05, raw))


def build_config() -> ScannerConfig:
    """The run's cadences, with the two bootstrap knobs an operator may tune.

    Only cadences are read from the environment. Thresholds never are: they are
    versioned in ``opportunity_weights`` so a decision can be replayed against the
    numbers that produced it.
    """
    return ScannerConfig(
        exchange=exchange_code(),
        bootstrap_budget_s=max(1.0, _env_float("SCANNER_BOOTSTRAP_BUDGET_S", 120.0)),
        bootstrap_duty=_clamped_duty(_env_float("SCANNER_BOOTSTRAP_DUTY", 0.4)),
    )


__all__ = [
    "CONSUMER_GROUP",
    "DEFAULT_EXCHANGE_CODE",
    "ScannerConfig",
    "build_config",
    "exchange_code",
    "group_for",
]
