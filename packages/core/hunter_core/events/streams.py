"""Stream names and default ``MAXLEN`` (trim target), from PIPELINE.md §10."""

from __future__ import annotations


class Streams:
    """Every Redis Stream named in PIPELINE.md §10."""

    MARKET_TICKS = "market.ticks"
    MARKET_CANDLES_CLOSED = "market.candles.closed"
    MARKET_DERIVATIVES = "market.derivatives"
    MARKET_LIQUIDATIONS = "market.liquidations"
    MARKET_UNIVERSE_CHANGED = "market.universe.changed"
    FEATURES_UPDATED = "features.updated"
    ANOMALIES_DETECTED = "anomalies.detected"
    REGIME_CHANGED = "regime.changed"
    OPPORTUNITIES_UPDATED = "opportunities.updated"
    SIGNALS_EMITTED = "signals.emitted"
    PROPOSALS_DECIDED = "proposals.decided"
    EXECUTIONS_COMPLETED = "executions.completed"
    POSITIONS_UPDATED = "positions.updated"
    RISK_EVENTS = "risk.events"
    KILL_SWITCH_CHANGED = "kill_switch.changed"
    AUDIT = "audit"


DEFAULT_MAXLEN: dict[str, int] = {
    Streams.MARKET_TICKS: 100_000,
    Streams.MARKET_CANDLES_CLOSED: 50_000,
    Streams.MARKET_DERIVATIVES: 20_000,
    Streams.MARKET_LIQUIDATIONS: 20_000,
    Streams.MARKET_UNIVERSE_CHANGED: 1_000,
    Streams.FEATURES_UPDATED: 100_000,
    Streams.ANOMALIES_DETECTED: 20_000,
    Streams.REGIME_CHANGED: 1_000,
    Streams.OPPORTUNITIES_UPDATED: 50_000,
    Streams.SIGNALS_EMITTED: 20_000,
    Streams.PROPOSALS_DECIDED: 20_000,
    Streams.EXECUTIONS_COMPLETED: 20_000,
    Streams.POSITIONS_UPDATED: 50_000,
    Streams.RISK_EVENTS: 10_000,
    Streams.KILL_SWITCH_CHANGED: 1_000,
    Streams.AUDIT: 10_000,
}
