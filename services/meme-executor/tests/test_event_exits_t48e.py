"""T4.8e, pure (no Docker): the event-driven exits no longer go blind on a ``TradeEvent`` they
cannot read.

After the pump program's redeploy of 2026-10-02 every real ``TradeEvent`` was undecodable and
``trade_events_from_logs`` dropped it silently: a watched position's creator sell, carried by
exactly that event, would never have fired ``creator_dump`` — with nothing on the heartbeat to
say so. The account notifications (the mark, the trailing stop) keep their own path.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

import hunter_meme_executor.event_exits as event_exits
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
from hunter_meme_executor.event_exits_stats import EventExitsStats, heartbeat_fields

from .test_event_exits import NOW, Db, _logs_frame, _position, _runtime, _watched, _wire

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
_PREFIX = "Program data: "


def _real_post_upgrade_logs() -> tuple[str, ...]:
    tx = json.loads((FIXTURES / "t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json").read_text())
    return tuple(tx["meta"]["logMessages"])


def _undecodable_logs(extra: int = 7) -> tuple[str, ...]:
    lines = list(_real_post_upgrade_logs())
    i = next(i for i, line in enumerate(lines) if line.startswith(_PREFIX))
    raw = base64.b64decode(lines[i][len(_PREFIX) :])
    lines[i] = _PREFIX + base64.b64encode(raw + b"\x00" * extra).decode()
    return tuple(lines)


def _frame(logs: tuple[str, ...]) -> LogsNotification:
    return replace(_logs_frame(3), logs=logs)  # the watched mint's own subscription id


async def test_an_undecodable_trade_event_is_counted_and_never_a_healthy_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, Db(positions=[_position()]))
    rt = _runtime()
    await _watched(rt)
    assert await event_exits.handle_notification(rt, _frame(_undecodable_logs()), now=NOW) is None
    assert rt.stats.undecodable_trades_total == 1
    assert "31 trailing bytes" in rt.stats.last_undecodable_error
    assert rt.stats.updates_60s(NOW) == 0  # the exit watch did not "see" anything


async def test_a_decodable_post_upgrade_event_of_another_mint_loses_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real post-upgrade sell of a mint nobody watches: read fine, ignored by the mint
    filter, and not mistaken for a loss."""
    _wire(monkeypatch, Db(positions=[_position()]))
    rt = _runtime()
    await _watched(rt)
    assert (
        await event_exits.handle_notification(rt, _frame(_real_post_upgrade_logs()), now=NOW)
        is None
    )
    assert rt.stats.undecodable_trades_total == 0


async def test_the_heartbeat_publishes_the_count_and_the_last_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, Db(positions=[_position()]))
    rt = _runtime()
    await _watched(rt)
    quiet = heartbeat_fields(rt.stats, now=NOW, enabled=True)
    assert quiet["event_exits_undecodable_trades"] == "0"
    assert quiet["event_exits_last_undecodable_error"] == ""
    for _ in range(3):
        await event_exits.handle_notification(rt, _frame(_undecodable_logs()), now=NOW)
    loud = heartbeat_fields(rt.stats, now=NOW, enabled=True)
    assert loud["event_exits_undecodable_trades"] == "3"
    assert "trailing bytes" in loud["event_exits_last_undecodable_error"]


def test_the_log_is_rate_limited_but_the_counter_is_exact() -> None:
    stats = EventExitsStats()
    assert stats.record_undecodable(NOW, 1, "boom") is True
    assert stats.record_undecodable(NOW + timedelta(seconds=1), 2, "boom") is False
    assert stats.record_undecodable(NOW + timedelta(seconds=31), 1, "boom") is True
    assert stats.undecodable_trades_total == 4
