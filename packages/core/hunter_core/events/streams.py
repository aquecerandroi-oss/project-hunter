"""Stream names and default ``MAXLEN`` (trim target), from PIPELINE.md §10."""

from __future__ import annotations


class Streams:
    """Every Redis Stream named in PIPELINE.md §10."""

    MARKET_TICKS = "market.ticks"
    MARKET_CANDLES_CLOSED = "market.candles.closed"
    MARKET_DERIVATIVES = "market.derivatives"
    MARKET_LIQUIDATIONS = "market.liquidations"
    MARKET_UNIVERSE_CHANGED = "market.universe.changed"
    MARKET_BACKFILL_REQUESTED = "market.backfill.requested"
    """A consumer asking the collector for history it does not have.

    The joint M2 decision gives REST to the market-worker alone, so a worker that
    needs older candles states the need on this stream and the collector -- which
    owns the rate limit, the gap table and the recovery loop -- decides how and
    when to fetch them. Deliberately a *request*, never a command: the payload
    describes a window, and the identity is the window, so asking twice is one
    gap."""

    MARKET_CANDLES_BACKFILLED = "market.candles.backfilled"
    """One aggregated announcement per REST-recovered *history*-tier chunk
    (T2.9c), instead of one ``market.candles.closed`` per backfilled minute.

    The market-worker's two-tier recovery (PIPELINE.md §1b item 7) already
    tells "live collection" apart from "history" by the age of the gap's
    window, not by who asked for it -- a gap the periodic detection itself
    created can age into the history tier if REST (or the worker) is down
    long enough, so this stream's ``reason`` is a description of *that*
    (``historical_recovery``), never a claim that someone requested the
    window. Publishing a whole 240-minute chunk as one event instead of up to
    240 kept the history tier's own output from becoming the outbox's
    bottleneck: at ``MAX_HISTORY_GAPS_PER_CYCLE`` chunks per cycle, the
    previous per-minute scheme could enqueue up to 1,440 rows/cycle ahead of
    live candles in the dispatcher's ``(created_at, id)`` order (notes-T2.5.md
    §28, §31; notes-T2.9.md T2.9c). ``market.candles.closed`` keeps announcing
    every live-tier minute individually -- WS ingest and REST recovery of
    recent gaps alike -- so no existing consumer changes behaviour."""

    FEATURES_UPDATED = "features.updated"
    ANOMALIES_DETECTED = "anomalies.detected"
    REGIME_CHANGED = "regime.changed"
    OPPORTUNITIES_UPDATED = "opportunities.updated"
    SIGNALS_EMITTED = "signals.emitted"
    SHADOW_SIGNALS_EMITTED = "shadow.signals.emitted"
    """Shadow Lab decisions (SHADOW-LAB.md §10). Deliberately **not**
    ``signals.emitted``: a shadow signal carries ``purpose = research_only`` and
    must never reach the proposal builder, and the cheapest way to guarantee
    that is for it to travel on a stream that pipeline nobody subscribes to."""
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
    Streams.MARKET_BACKFILL_REQUESTED: 5_000,
    Streams.MARKET_CANDLES_BACKFILLED: 5_000,
    Streams.FEATURES_UPDATED: 100_000,
    Streams.ANOMALIES_DETECTED: 20_000,
    Streams.REGIME_CHANGED: 1_000,
    Streams.OPPORTUNITIES_UPDATED: 50_000,
    Streams.SIGNALS_EMITTED: 20_000,
    Streams.SHADOW_SIGNALS_EMITTED: 20_000,
    Streams.PROPOSALS_DECIDED: 20_000,
    Streams.EXECUTIONS_COMPLETED: 20_000,
    Streams.POSITIONS_UPDATED: 50_000,
    Streams.RISK_EVENTS: 10_000,
    Streams.KILL_SWITCH_CHANGED: 1_000,
    Streams.AUDIT: 10_000,
}
