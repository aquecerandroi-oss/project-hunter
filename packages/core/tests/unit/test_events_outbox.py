"""Unit tests for the generic transactional outbox (T2.9).

Everything here is pure: identity, the row <-> envelope mapping and the
readiness verdict. The failure-injection matrix (before the commit, between
the commit and the ``XADD``, after the ``XADD`` and before the mark, a
consumer that dies before its ACK, a trimmed stream) needs a real Postgres
and a real Redis and lives in ``tests/integration/test_outbox_integration.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.outbox import STALE_SWEEP_FACTOR, OutboxHealth
from hunter_core.events.outbox_store import (
    build_envelope,
    envelope_from_row,
    event_id_for,
    outbox_row,
)

pytestmark = pytest.mark.unit


def test_event_id_is_deterministic_for_the_same_business_key() -> None:
    first = event_id_for("market.candles.closed", "binance", "BTCUSDT", "1m", "2026-09-05T12:00:00")
    second = event_id_for(
        "market.candles.closed", "binance", "BTCUSDT", "1m", "2026-09-05T12:00:00"
    )
    assert first == second
    assert isinstance(first, UUID)


def test_event_id_separates_streams_and_parts() -> None:
    candle = event_id_for("market.candles.closed", "binance", "BTCUSDT")
    deriv = event_id_for("market.derivatives", "binance", "BTCUSDT")
    other = event_id_for("market.candles.closed", "binance", "ETHUSDT")
    assert len({candle, deriv, other}) == 3


def test_event_id_of_an_aware_datetime_is_normalized_to_utc() -> None:
    """The same instant expressed in another offset is the same event."""
    utc = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    sao_paulo = datetime(2026, 9, 5, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert utc == sao_paulo
    assert event_id_for("s", utc) == event_id_for("s", sao_paulo)


def test_event_id_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        event_id_for("s", datetime(2026, 9, 5, 12, 0))  # noqa: DTZ001


def test_the_row_stores_the_whole_envelope_and_mirrors_its_identity() -> None:
    envelope = build_envelope(
        "market.candles.closed",
        event_id_for("market.candles.closed", "binance", "BTCUSDT"),
        {"symbol": "BTCUSDT", "close": "100.5"},
        producer="market-worker@1",
        key="binance:BTCUSDT",
    )
    row = outbox_row(envelope)
    assert row["event_id"] == envelope.event_id
    assert row["stream"] == "market.candles.closed"
    assert row["payload"]["event_id"] == str(envelope.event_id)
    assert row["payload"]["payload"]["close"] == "100.5"


def test_the_envelope_survives_a_jsonb_round_trip_byte_for_byte() -> None:
    """JSONB does not preserve key order, so the dispatcher must rebuild the
    envelope through the model (fixed field order) rather than re-serializing
    whatever order Postgres hands back — otherwise the same event republished
    after a crash would be different bytes on the stream."""
    envelope = build_envelope(
        "market.candles.closed",
        event_id_for("market.candles.closed", "binance", "BTCUSDT"),
        {"b": 2, "a": 1},
        producer="market-worker@1",
        key="binance:BTCUSDT",
    )
    stored = outbox_row(envelope)["payload"]
    shuffled = dict(reversed(list(stored.items())))
    assert envelope_from_row(shuffled).to_bytes() == envelope.to_bytes()


def test_the_envelope_ts_is_the_enqueue_instant_and_is_utc() -> None:
    at = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    envelope = build_envelope("s", event_id_for("s", "x"), {}, producer="p", key="k", ts=at)
    assert envelope.ts == at
    assert envelope_from_row(outbox_row(envelope)["payload"]).ts == at


def test_build_envelope_rejects_a_naive_ts() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_envelope(
            "s",
            event_id_for("s", "x"),
            {},
            producer="p",
            key="k",
            ts=datetime(2026, 9, 5, 12, 0),  # noqa: DTZ001
        )


def test_envelope_from_row_rejects_a_payload_that_is_not_an_envelope() -> None:
    with pytest.raises(ValueError, match="envelope"):
        envelope_from_row({"symbol": "BTCUSDT"})


def test_health_is_green_when_nothing_is_pending() -> None:
    health = OutboxHealth()
    assert health.ready(max_pending=100, max_lag_s=30.0) is True
    assert health.lag_s(now=datetime(2026, 9, 5, 12, 0, tzinfo=UTC)) == 0.0


def test_health_is_red_on_too_many_pending() -> None:
    health = OutboxHealth(pending=101)
    assert health.ready(max_pending=100, max_lag_s=30.0) is False


def test_health_is_red_on_an_aged_pending_row() -> None:
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    health = OutboxHealth(pending=1, oldest_pending=now - timedelta(seconds=31))
    assert health.lag_s(now=now) == pytest.approx(31.0)
    assert health.ready(max_pending=100, max_lag_s=30.0, now=now) is False
    assert health.ready(max_pending=100, max_lag_s=60.0, now=now) is True


def test_health_is_green_during_the_startup_grace_but_not_forever() -> None:
    """A boot that never manages one successful observation must go red.

    ``last_sweep_at is None`` means "no verdict yet", which is right for the
    first seconds of a process. But if the backlog query itself keeps failing
    -- a missing grant on ``outbox_events``, say, while the database health
    check and the producers' own inserts still work -- the dispatcher only
    logs and retries, and this check would answer green forever from a
    snapshot that was never taken (Astra, T2.9 retomada).
    """
    started = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    health = OutboxHealth(started_at=started)
    grace = 30.0 * STALE_SWEEP_FACTOR

    assert health.ready(max_pending=100, max_lag_s=30.0, now=started) is True
    inside = started + timedelta(seconds=grace - 1)
    assert health.ready(max_pending=100, max_lag_s=30.0, now=inside) is True
    outside = started + timedelta(seconds=grace + 1)
    assert health.ready(max_pending=100, max_lag_s=30.0, now=outside) is False

    # One successful observation is what ends the grace, not the clock.
    health.last_sweep_at = outside
    assert health.ready(max_pending=100, max_lag_s=30.0, now=outside) is True


def test_an_envelope_rebuilt_from_a_row_keeps_the_declared_type() -> None:
    envelope = EventEnvelope(
        event_id=event_id_for("s", "x"), type="s", producer="p", key="k", payload={}
    )
    assert envelope_from_row(outbox_row(envelope)["payload"]).type == "s"


def test_a_batch_of_envelopes_collapses_duplicates_before_the_insert() -> None:
    """One multi-row statement per flush, and the same identity twice in one
    batch is one row: a single-statement ``DO NOTHING`` keeps the first
    occurrence, so sending both would only cost a round trip."""
    envelope = build_envelope("s", event_id_for("s", "x"), {"n": 1}, producer="p", key="k")
    other = build_envelope("s", event_id_for("s", "y"), {"n": 2}, producer="p", key="k")
    rows = {e.event_id: outbox_row(e) for e in [envelope, other, envelope]}
    assert len(rows) == 2
