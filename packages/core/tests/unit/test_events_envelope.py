"""Unit tests for hunter_core.events: envelope round-trip and stream registry."""

import pytest

from hunter_core.events import DEFAULT_MAXLEN, EventEnvelope, Streams

pytestmark = pytest.mark.unit


def test_envelope_round_trips_through_orjson() -> None:
    envelope = EventEnvelope(
        type="opportunities.updated",
        producer="scanner-worker@host:123",
        key="binance:BTCUSDT",
        payload={"score": 82.5, "direction": "long"},
    )

    restored = EventEnvelope.from_bytes(envelope.to_bytes())

    assert restored == envelope
    assert restored.event_id == envelope.event_id
    assert restored.ts == envelope.ts
    assert restored.payload == {"score": 82.5, "direction": "long"}


def test_envelope_defaults_event_id_and_ts() -> None:
    envelope = EventEnvelope(type="t", producer="p", key="k", payload={})
    assert envelope.event_id.version == 7
    assert envelope.ts.tzinfo is not None


def test_every_pipeline_stream_has_a_default_maxlen() -> None:
    documented_streams = [
        Streams.MARKET_TICKS,
        Streams.MARKET_CANDLES_CLOSED,
        Streams.MARKET_DERIVATIVES,
        Streams.MARKET_LIQUIDATIONS,
        Streams.MARKET_UNIVERSE_CHANGED,
        Streams.MARKET_CANDLES_BACKFILLED,
        Streams.FEATURES_UPDATED,
        Streams.ANOMALIES_DETECTED,
        Streams.REGIME_CHANGED,
        Streams.OPPORTUNITIES_UPDATED,
        Streams.SIGNALS_EMITTED,
        Streams.PROPOSALS_DECIDED,
        Streams.EXECUTIONS_COMPLETED,
        Streams.POSITIONS_UPDATED,
        Streams.RISK_EVENTS,
        Streams.KILL_SWITCH_CHANGED,
        Streams.AUDIT,
    ]
    for stream in documented_streams:
        assert stream in DEFAULT_MAXLEN
        assert DEFAULT_MAXLEN[stream] > 0


def test_stream_names_match_pipeline_md() -> None:
    assert Streams.MARKET_TICKS == "market.ticks"
    assert Streams.MARKET_CANDLES_CLOSED == "market.candles.closed"
    assert Streams.MARKET_CANDLES_BACKFILLED == "market.candles.backfilled"
    assert Streams.KILL_SWITCH_CHANGED == "kill_switch.changed"
    assert Streams.RISK_EVENTS == "risk.events"
