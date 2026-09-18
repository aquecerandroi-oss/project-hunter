"""T4.52b-3, pure/no Docker: subscription sync against a ``FakeWs`` and the
notification dispatch, replaying the T4.52b-1 fixtures (``rpc_ws.py``'s own
``_parse_frame``, reused rather than reimplemented).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_exchanges.pumpfun.rpc_ws_models import (
    AccountNotification,
    ConnectionState,
    LogsNotification,
    SlotNotification,
)
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.event_gate_config import EventGateConfig
from hunter_meme_worker.event_gate_eval import apply_notification
from hunter_meme_worker.event_gate_runtime import EventGateRuntime
from hunter_meme_worker.event_gate_subscriptions import sync_subscriptions
from hunter_meme_worker.lab import LabContext, LabState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

FIXTURES = Path(__file__).parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

MINT_A = "So11111111111111111111111111111111111111112"
MINT_OLD = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MINT_NEW = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


LOGS_LINES = _lines("t452b_ws_logs_notifications_raw.jsonl")
ACCOUNT_LINES = _lines("t452b_ws_account_notifications_raw.jsonl")


def _near_block_time(notif: LogsNotification) -> LogsNotification:
    """The fixture's own ``received_at`` is today's wall clock (parsed live,
    T4.52b-1's own capture date is fixed): rebase it to just after the
    decoded event's ``block_time`` so :class:`MintEventState`'s 120 s window
    (relative to *its own* clock) does not immediately prune the point — the
    same choice ``test_event_state.py`` documents (``received_at = block_time
    + 0.5s``)."""
    events = trade_events_from_logs(notif.logs)
    if not events:
        return notif
    block_time = datetime.fromtimestamp(events[0].timestamp, tz=UTC)
    return replace(notif, received_at=block_time + timedelta(seconds=0.5))


def _parser_client() -> SolanaWsClient:
    """Only ``_parse_frame`` is under test transitively — pre-bind every
    fixture's server id to logical id ``1`` (``test_pumpfun_rpc_ws.py``'s own
    convention), the id our own tests then remap to a mint of their choosing."""
    client = SolanaWsClient()
    for line in LOGS_LINES + ACCOUNT_LINES:
        server_id = json.loads(line)["params"]["subscription"]
        client._logical_of_server[server_id] = 1
    return client


class FakeWs:
    """A ``SolanaWs`` double: records every subscribe/unsubscribe call, hands
    out predictable logical ids."""

    def __init__(self) -> None:
        self.state = ConnectionState()
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[int] = []
        self._next_id = 1

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        self.subscribed.append(("logs", mentions[0]))
        self._next_id += 1
        return self._next_id

    async def subscribe_account(self, pubkey: str, *, commitment: str) -> int:
        self.subscribed.append(("account", pubkey))
        self._next_id += 1
        return self._next_id

    async def unsubscribe(self, logical_id: int) -> bool:
        self.unsubscribed.append(logical_id)
        return True

    async def aclose(self) -> None:
        return None

    def listen(self) -> Any:  # pragma: no cover - unused by these tests
        raise NotImplementedError


def _runtime(ws: FakeWs, *, max_mints: int = 150) -> EventGateRuntime:
    radar = RadarContext(
        config=MemeConfig(enabled=True, fast_lane_max_age_s=300, fast_lane_pinned_max_age_s=1800),
        session_factory=None,  # type: ignore[arg-type]
        tracker=MintTracker(window_minutes=60, cap=200),
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
    )
    lab = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=None,  # type: ignore[arg-type]
        state=LabState(),
        quotes=None,
        heartbeat=None,
    )
    config = EventGateConfig(
        mode="on", ws_url="ws://x", commitment="confirmed", max_mints=max_mints
    )
    return EventGateRuntime(radar=radar, lab=lab, ws=ws, config=config)  # type: ignore[arg-type]


# ---- subscription sync --------------------------------------------------------------


async def test_sync_subscribes_every_young_mint_once() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.radar.tracker.observe(
        TrackedMint(mint=MINT_A, first_seen_at=NOW, created_at=NOW - timedelta(seconds=30))
    )
    await sync_subscriptions(rt, now=NOW)
    assert MINT_A in rt.subs
    assert len(ws.subscribed) == 2  # logs + account
    await sync_subscriptions(rt, now=NOW + timedelta(seconds=1))
    assert len(ws.subscribed) == 2  # already subscribed: no repeat


async def test_sync_unsubscribes_a_mint_that_aged_out() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.radar.tracker.observe(
        TrackedMint(mint=MINT_A, first_seen_at=NOW, created_at=NOW - timedelta(seconds=30))
    )
    await sync_subscriptions(rt, now=NOW)
    assert MINT_A in rt.subs
    await sync_subscriptions(rt, now=NOW + timedelta(seconds=400))  # past fast_lane_max_age_s
    assert MINT_A not in rt.subs
    assert len(ws.unsubscribed) == 2


async def test_sync_stops_at_the_max_mints_cap() -> None:
    ws = FakeWs()
    rt = _runtime(ws, max_mints=1)
    rt.radar.tracker.observe(
        TrackedMint(mint=MINT_OLD, first_seen_at=NOW, created_at=NOW - timedelta(seconds=200))
    )
    rt.radar.tracker.observe(
        TrackedMint(mint=MINT_NEW, first_seen_at=NOW, created_at=NOW - timedelta(seconds=1))
    )
    await sync_subscriptions(rt, now=NOW)
    assert len(rt.subs) == 1
    assert MINT_NEW in rt.subs  # young_mints orders newest first


# ---- notification dispatch -----------------------------------------------------------


async def test_apply_notification_folds_a_trade_and_updates_reserves() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.book.touch(MINT_A, at=NOW, first_seen_at=NOW - timedelta(seconds=90))
    parser = _parser_client()
    processed = 0
    for line in LOGS_LINES:
        notif = parser._parse_frame(line)
        if not isinstance(notif, LogsNotification) or notif.err is not None:
            continue
        notif = _near_block_time(notif)
        rt.subs_by_logical[notif.subscription_id] = MINT_A
        mint = apply_notification(rt, notif)
        assert mint == MINT_A
        processed += 1
    assert processed > 0
    state = rt.book.get(MINT_A)
    assert state is not None and len(state.points) > 0  # at least one line decoded a TradeEvent
    assert MINT_A in rt.reserves


async def test_apply_notification_ignores_an_unknown_subscription() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    parser = _parser_client()
    notif = next(
        n
        for line in LOGS_LINES
        if isinstance(n := parser._parse_frame(line), LogsNotification) and n.err is None
    )
    # No mapping registered for notif.subscription_id -> ignored, never a KeyError.
    assert apply_notification(rt, notif) is None


async def test_apply_notification_folds_an_account_notification() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.book.touch(MINT_A, at=NOW, first_seen_at=NOW - timedelta(seconds=90))
    parser = _parser_client()
    notif = next(
        n
        for line in ACCOUNT_LINES
        if isinstance(n := parser._parse_frame(line), AccountNotification)
    )
    rt.subs_by_logical[notif.subscription_id] = MINT_A
    mint = apply_notification(rt, notif)
    assert mint == MINT_A
    assert MINT_A in rt.reserves
    state = rt.book.get(MINT_A)
    assert state is not None and state.total_supply is not None


async def test_apply_notification_updates_the_slot_anchor_and_returns_none() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    notif = SlotNotification(
        subscription_id=1, kind="slot", slot=500, parent=499, root=0, received_at=NOW
    )
    assert apply_notification(rt, notif) is None
    assert rt.slot == 500
    older = SlotNotification(
        subscription_id=1, kind="slot", slot=100, parent=99, root=0, received_at=NOW
    )
    apply_notification(rt, older)
    assert rt.slot == 500  # never regresses
