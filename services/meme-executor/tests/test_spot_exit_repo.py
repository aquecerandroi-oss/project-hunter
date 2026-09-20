"""T4.74-5 — ``spot_exit_repo`` against the recording fake session of
``test_spot_repo``: one statement per call, parameters bound by name, and the
predicates the exits and the reconcile rely on."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from hunter_meme_executor import spot_exit_repo as repo

from .test_spot_repo import FakeSession


def _session(rows: list[dict[str, Any]] | None = None) -> tuple[FakeSession, Any]:
    fake = FakeSession(rows=rows or [])
    return fake, cast(Any, fake)


def _only(session: FakeSession) -> tuple[str, dict[str, Any]]:
    assert len(session.calls) == 1, "one statement per call"
    sql, params = session.calls[0]
    return sql, params or {}


pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)


async def test_sell_attempts_counts_every_sell_row_of_the_position() -> None:
    fake, session = _session([{"n": 3, "hard": 1}])
    assert await repo.sell_attempts(session, "p1") == repo.SellAttempts(3, 1)
    sql, params = _only(fake)
    assert "side = 'sell'" in sql and "position_id = :position_id" in sql
    assert params == {"position_id": "p1"}
    for prefix in repo.TRANSIENT_EXIT_REFUSALS:
        assert f"reason NOT LIKE '{prefix}%'" in sql, "the SQL and the constant name the same set"


async def test_set_exit_pending_names_the_order_on_an_open_position_only() -> None:
    fake, session = _session([{"id": "p1"}])
    assert await repo.set_exit_pending(
        session, "p1", order_id="o1", reason="stop", attempt=2, now=NOW
    )
    sql, params = _only(fake)
    assert "exit_order_id = :order_id" in sql and "status = 'open'" in sql
    intent = json.loads(params["intent"])
    assert intent["status"] == "submitted_unconfirmed" and intent["attempt"] == 2
    assert intent["reason"] == "stop" and intent["order_id"] == "o1"


async def test_clear_exit_pending_only_clears_the_named_order() -> None:
    fake, session = _session([])
    cleared = await repo.clear_exit_pending(
        session, "p1", order_id="o1", outcome="failed:x", now=NOW
    )
    assert cleared is False
    sql, params = _only(fake)
    assert "exit_order_id = NULL" in sql and "exit_order_id = :order_id" in sql
    assert params["order_id"] == "o1" and json.loads(params["intent"])["status"] == "failed:x"


def _row(**over: Any) -> dict[str, Any]:
    base = {
        "id": "o1",
        "side": "buy",
        "status": "submitted_unconfirmed",
        "signal_id": "s1",
        "position_id": None,
        "market_symbol": "UNIUSDT",
        "mint": "M",
        "tx_signature": "sig",
        "last_valid_block_height": 7,
        "submitted_at": NOW,
        "intent": {"a": 1},
        "admission": None,
        "quote": None,
        "fill": {"filled_atoms": 1},
    }
    return {**base, **over}


async def test_unconfirmed_rows_are_read_by_status_with_a_signature_and_a_limit() -> None:
    fake, session = _session([_row()])
    (row,) = await repo.unconfirmed_spot_orders(session)
    sql, _ = _only(fake)
    assert "status = 'submitted_unconfirmed'" in sql and "tx_signature IS NOT NULL" in sql
    assert "LIMIT 50" in sql
    assert row.id == "o1" and row.last_valid_block_height == 7 and row.admission == {}
    assert row.fill == {"filled_atoms": 1} and row.position_id is None


async def test_the_orphan_and_abandoned_reads_name_their_predicates() -> None:
    fake, session = _session([])
    await repo.confirmed_buys_without_position(session)
    sql, _ = _only(fake)
    assert "side = 'buy'" in sql and "status = 'confirmed'" in sql
    assert "NOT EXISTS (SELECT 1 FROM spot_positions p WHERE p.entry_order_id = o.id)" in sql
    fake, session = _session([])
    await repo.confirmed_sells_still_pending(session)
    sql, _ = _only(fake)
    assert "p.exit_order_id = o.id AND p.status = 'open'" in sql and "side = 'sell'" in sql
    fake, session = _session([])
    await repo.abandoned_orders(session, before=NOW)
    sql, params = _only(fake)
    assert "status IN ('admitted', 'simulated')" in sql and "signing_at IS NULL" in sql
    assert "received_at < :before" in sql and params == {"before": NOW}


async def test_fail_abandoned_never_touches_a_row_that_signed() -> None:
    fake, session = _session([{"id": "o1"}])
    assert await repo.fail_abandoned(session, "o1", reason="abandoned_before_signing", now=NOW)
    sql, params = _only(fake)
    assert "status = 'failed'" in sql and "signing_at IS NULL" in sql
    assert "status IN ('admitted', 'simulated')" in sql
    assert params["reason"] == "abandoned_before_signing"


async def test_enabled_market_count_and_open_position_by_id() -> None:
    fake, session = _session([{"n": 40}])
    assert await repo.enabled_market_count(session) == 40
    assert "WHERE enabled" in _only(fake)[0]
    fake, session = _session([])
    assert await repo.open_position_by_id(session, "p1") is None
    sql, params = _only(fake)
    assert "id = :id AND status = 'open'" in sql and params == {"id": "p1"}
