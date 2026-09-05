"""hunter_exchanges.binance.subscriptions: incremental universe diffs.

``docs/plans/M1.md`` T1.2b ("quem fica não é reassinado"): symbols that stay
subscribed are never resubscribed; only the diff travels as ``SUBSCRIBE``/
``UNSUBSCRIBE``; overflow beyond every group's free capacity opens a new one.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hunter_exchanges.base import ConnectionState, StreamChannel
from hunter_exchanges.binance.subscriptions import (
    SubscriptionController,
    SymbolGroup,
    control_frame,
    is_control_ack,
    names_for,
    plan_updates,
)

pytestmark = pytest.mark.unit


def test_control_frame_is_a_binance_json_rpc_request() -> None:
    frame = json.loads(control_frame("SUBSCRIBE", 7, ["btcusdt@aggTrade"]))

    assert frame == {"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade"], "id": 7}


def test_is_control_ack_distinguishes_from_a_data_frame() -> None:
    assert is_control_ack({"result": None, "id": 1}) is True
    assert is_control_ack({"stream": "btcusdt@aggTrade", "data": {}}) is False


def test_names_for_builds_every_symbol_channel_combination() -> None:
    names = names_for(["BTCUSDT", "ETHUSDT"], [StreamChannel.TRADES, StreamChannel.KLINE_1M])

    assert names == [
        "btcusdt@aggTrade",
        "btcusdt@kline_1m",
        "ethusdt@aggTrade",
        "ethusdt@kline_1m",
    ]


def _group(key: str, symbols: list[str]) -> SymbolGroup:
    return SymbolGroup(key=key, route="market", channels=(StreamChannel.TRADES,), symbols=symbols)


def test_plan_updates_removed_symbol_leaves_the_rest_of_the_group_untouched() -> None:
    groups = {"market:0": _group("market:0", ["BTCUSDT", "ETHUSDT"])}

    plan = plan_updates(groups, "market", [StreamChannel.TRADES], [], ["ETHUSDT"], next_index=1)

    assert plan.unsubscribe == {"market:0": ["ethusdt@aggTrade"]}
    assert plan.subscribe == {}
    assert plan.new_groups == []
    assert groups["market:0"].symbols == ["BTCUSDT"]  # BTCUSDT was never touched


def test_plan_updates_added_symbol_fills_existing_group_free_capacity() -> None:
    groups = {"market:0": _group("market:0", ["BTCUSDT"])}

    plan = plan_updates(groups, "market", [StreamChannel.TRADES], ["ETHUSDT"], [], next_index=1)

    assert plan.subscribe == {"market:0": ["ethusdt@aggTrade"]}
    assert plan.new_groups == []
    assert groups["market:0"].symbols == ["BTCUSDT", "ETHUSDT"]


def test_plan_updates_raises_rather_than_overshoot_the_1024_stream_limit() -> None:
    """F12: growing an *existing* group past ``MAX_STREAMS_PER_CONNECTION``
    (symbols x channels) must raise, never silently build an oversized
    group. ``MAX_SYMBOLS_PER_CONNECTION`` (200) is only safe today because
    Binance's ``market`` route carries 4 channels (800); simulating a
    hypothetical 6-channel route (1200) must fail loud instead of silently
    building a connection Binance would reject."""
    channels = list(StreamChannel)  # all 6 — simulates a future extra channel
    assert len(channels) == 6
    groups = {
        "market:0": SymbolGroup(
            key="market:0",
            route="market",
            channels=tuple(channels),
            symbols=[f"SYM{i}USDT" for i in range(150)],
        )
    }
    added = [f"NEW{i}USDT" for i in range(50)]  # free capacity: 200 - 150 = 50, fills exactly

    with pytest.raises(ValueError, match="1024"):
        plan_updates(groups, "market", channels, added, [], next_index=1)


def test_plan_updates_overflow_opens_a_new_group() -> None:
    full = _group("market:0", [f"SYM{i}USDT" for i in range(200)])
    groups = {"market:0": full}

    plan = plan_updates(groups, "market", [StreamChannel.TRADES], ["NEWUSDT"], [], next_index=1)

    assert plan.subscribe == {}
    assert len(plan.new_groups) == 1
    assert plan.new_groups[0].key == "market:1"
    assert plan.new_groups[0].symbols == ["NEWUSDT"]


def test_plan_updates_added_and_removed_same_symbol_is_a_no_op() -> None:
    groups = {"market:0": _group("market:0", ["BTCUSDT"])}

    plan = plan_updates(
        groups, "market", [StreamChannel.TRADES], ["ETHUSDT"], ["ETHUSDT"], next_index=1
    )

    assert plan.subscribe == {}
    assert plan.unsubscribe == {}
    assert plan.new_groups == []


def test_plan_updates_ignores_a_different_routes_groups() -> None:
    groups = {"public:0": _group("public:0", ["BTCUSDT"])}
    groups["public:0"].route = "public"

    plan = plan_updates(groups, "market", [StreamChannel.TRADES], ["ETHUSDT"], [], next_index=0)

    assert plan.new_groups[0].key == "market:0"  # index counted independently per route


class _RecordingConnection:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


async def test_controller_update_sends_only_the_diff_and_keeps_states_in_sync() -> None:
    started: list[SymbolGroup] = []
    controller = SubscriptionController(start=started.append)
    controller.groups["market:0"] = _group("market:0", ["BTCUSDT", "ETHUSDT"])
    connection = _RecordingConnection()
    controller.live_ws["market:0"] = connection
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = ("btcusdt@aggTrade", "ethusdt@aggTrade")

    await controller.update(["XRPUSDT"], ["ETHUSDT"], [StreamChannel.TRADES], states)

    assert len(connection.sent) == 2  # one UNSUBSCRIBE, one SUBSCRIBE
    methods = [json.loads(frame)["method"] for frame in connection.sent]
    assert methods == ["UNSUBSCRIBE", "SUBSCRIBE"]
    assert "ethusdt@aggTrade" not in states["market:0"].subscriptions
    assert "xrpusdt@aggTrade" in states["market:0"].subscriptions
    assert "btcusdt@aggTrade" in states["market:0"].subscriptions  # untouched symbol stays
    assert started == []  # no overflow: no new connection/task started


async def test_controller_send_control_with_no_live_connection_logs_and_skips() -> None:
    controller = SubscriptionController(start=lambda group: None)

    sent = await controller.send_control("market:0", "SUBSCRIBE", ["btcusdt@aggTrade"])

    assert sent is False


async def test_controller_update_never_reports_success_without_a_live_connection() -> None:
    """Astra review, T1.2b resume finding 3: adding ETH while BTC's
    connection is mid-handshake (no live socket yet) must not claim ETH is
    subscribed — the group's own symbol list still gets the addition, so the
    next successful (re)connect self-heals ``subscriptions`` for free."""
    controller = SubscriptionController(start=lambda group: None)
    controller.groups["market:0"] = _group("market:0", ["BTCUSDT"])
    # No entry in controller.live_ws["market:0"]: handshake still in flight.
    states = {"market:0": ConnectionState(route="market", ws_state="connecting")}
    states["market:0"].subscriptions = ("btcusdt@aggTrade",)

    await controller.update(["ETHUSDT"], [], [StreamChannel.TRADES], states)

    assert states["market:0"].subscriptions == ("btcusdt@aggTrade",)  # unchanged, honestly
    assert controller.groups["market:0"].symbols == ["BTCUSDT", "ETHUSDT"]  # self-heals on connect


async def test_controller_resolve_ack_logs_an_error_ack_without_raising() -> None:
    controller = SubscriptionController(start=lambda group: None)
    controller.pending_acks[1] = ("market:0", "SUBSCRIBE", ("btcusdt@aggTrade",))
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}

    await controller.resolve_ack(
        {"id": 1, "error": {"code": -1121, "msg": "Invalid symbol"}}, states
    )

    assert 1 not in controller.pending_acks  # still consumed, just logged as an error


async def test_controller_resolve_ack_error_ack_drops_names_and_restarts_the_connection() -> None:
    """F6: a rejected SUBSCRIBE must not leave the name reported as an
    active subscription, and the affected connection must restart so it
    resubscribes from the group's desired set."""
    restarted: list[str] = []

    async def restart(key: str) -> None:
        restarted.append(key)

    controller = SubscriptionController(start=lambda group: None, restart=restart)
    controller.pending_acks[1] = (
        "market:0",
        "SUBSCRIBE",
        ("ethusdt@aggTrade", "ethusdt@kline_1m"),
    )
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = (
        "btcusdt@aggTrade",
        "ethusdt@aggTrade",
        "ethusdt@kline_1m",
    )

    await controller.resolve_ack(
        {"id": 1, "error": {"code": -1121, "msg": "Invalid symbol"}}, states
    )

    assert states["market:0"].subscriptions == ("btcusdt@aggTrade",)
    assert restarted == ["market:0"]


async def test_controller_resolve_ack_error_ack_on_unsubscribe_does_not_restart() -> None:
    """An error ACK on UNSUBSCRIBE is logged, but F6's drop-and-restart is
    scoped to SUBSCRIBE (a rejected subscription silently staying "active"
    is the failure mode; a rejected unsubscribe is not)."""
    restarted: list[str] = []

    async def restart(key: str) -> None:
        restarted.append(key)

    controller = SubscriptionController(start=lambda group: None, restart=restart)
    controller.pending_acks[1] = ("market:0", "UNSUBSCRIBE", ("ethusdt@aggTrade",))
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}

    await controller.resolve_ack(
        {"id": 1, "error": {"code": -1121, "msg": "Invalid symbol"}}, states
    )

    assert restarted == []


async def test_controller_send_control_with_empty_names_is_a_no_op() -> None:
    controller = SubscriptionController(start=lambda group: None)
    connection = _RecordingConnection()
    controller.live_ws["market:0"] = connection

    await controller.send_control("market:0", "SUBSCRIBE", [])

    assert connection.sent == []


async def test_controller_resolve_ack_pops_the_pending_entry() -> None:
    controller = SubscriptionController(start=lambda group: None)
    controller.pending_acks[1] = ("market:0", "SUBSCRIBE", ("btcusdt@aggTrade",))
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}

    await controller.resolve_ack({"result": None, "id": 1}, states)

    assert 1 not in controller.pending_acks


async def test_controller_resolve_ack_of_an_unknown_id_does_not_raise() -> None:
    controller = SubscriptionController(start=lambda group: None)

    # logs a warning, never raises
    await controller.resolve_ack({"result": None, "id": 999}, {})


async def test_controller_update_send_failure_does_not_raise_and_restarts_the_connection() -> None:
    """F6: a send() failure inside update() (called directly by the
    market-worker, outside any connection's own reconnect loop) must never
    propagate a raw exception to the caller — it is routed through the same
    restart path a rejected/timed-out ACK uses. catch_up()'s own send
    failures deliberately keep propagating instead (see
    test_catch_up_failure_goes_through_the_normal_reconnect_backoff in
    test_ws_client_updates.py) so they still go through the connection's
    normal reconnect-attempt/backoff machinery."""

    class _BrokenConnection:
        async def send(self, message: str) -> None:
            raise ConnectionError("socket closed")

    restarted: list[str] = []

    async def restart(key: str) -> None:
        restarted.append(key)

    controller = SubscriptionController(start=lambda group: None, restart=restart)
    controller.groups["market:0"] = _group("market:0", ["BTCUSDT"])
    controller.live_ws["market:0"] = _BrokenConnection()
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = ("btcusdt@aggTrade",)

    await controller.update(["ETHUSDT"], [], [StreamChannel.TRADES], states)  # must not raise

    assert restarted == ["market:0"]
    assert controller.pending_acks == {}  # never left dangling


async def test_controller_subscribe_ack_that_never_arrives_drops_names_and_restarts() -> None:
    """F6: an ACK that never arrives within a short deadline is treated the
    same as an explicit error ACK."""
    clock: dict[str, list[float]] = {"advanced": []}

    async def instant_sleep(seconds: float) -> None:
        clock["advanced"].append(seconds)

    restarted: list[str] = []

    async def restart(key: str) -> None:
        restarted.append(key)

    controller = SubscriptionController(
        start=lambda group: None, restart=restart, sleep=instant_sleep, ack_timeout_s=5.0
    )
    connection = _RecordingConnection()  # never enqueues a matching ack
    controller.live_ws["market:0"] = connection
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = ()

    await controller.send_control("market:0", "SUBSCRIBE", ["ethusdt@aggTrade"], states=states)
    await controller.wait_for_pending_acks()

    assert clock["advanced"] == [5.0]
    assert restarted == ["market:0"]
    assert controller.pending_acks == {}


async def test_controller_reset_clears_all_state() -> None:
    controller = SubscriptionController(start=lambda group: None)
    controller.groups["market:0"] = _group("market:0", ["BTCUSDT"])
    controller.live_ws["market:0"] = _RecordingConnection()
    controller.pending_acks[1] = ("market:0", "SUBSCRIBE", ("btcusdt@aggTrade",))

    controller.reset()

    assert controller.groups == {}
    assert controller.live_ws == {}
    assert controller.pending_acks == {}


async def test_catch_up_sends_unsubscribe_before_subscribe() -> None:
    """F5: catch_up must send UNSUBSCRIBE before SUBSCRIBE (the order
    update() already uses) — the reverse order can overshoot Binance's
    1024-streams-per-connection limit when a diff arrives mid-handshake
    (200 symbols x 4 channels = 800, swap 100/100 -> 800 -> 1200 -> 800)."""
    channels = (
        StreamChannel.TRADES,
        StreamChannel.KLINE_1M,
        StreamChannel.MARK_PRICE,
        StreamChannel.LIQUIDATIONS,
    )
    opened_symbols = [f"OLD{i}USDT" for i in range(200)]
    current_symbols = [f"OLD{i}USDT" for i in range(100)] + [f"NEW{i}USDT" for i in range(100)]
    connection = _RecordingConnection()
    controller = SubscriptionController(start=lambda group: None)
    controller.groups["market:0"] = SymbolGroup(
        key="market:0", route="market", channels=channels, symbols=current_symbols
    )
    controller.live_ws["market:0"] = connection
    opened_with = names_for(opened_symbols, channels)
    peak_streams = len(opened_with)
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = tuple(opened_with)

    await controller.catch_up("market:0", opened_with, states)

    methods = [json.loads(frame)["method"] for frame in connection.sent]
    assert methods == ["UNSUBSCRIBE", "SUBSCRIBE"]
    # Simulate Binance applying frames in the order sent and check the
    # declared stream count never exceeds the pre-diff peak (never
    # overshoots, since UNSUBSCRIBE always lands before SUBSCRIBE).
    live = len(opened_with)
    for frame in connection.sent:
        parsed = json.loads(frame)
        if parsed["method"] == "UNSUBSCRIBE":
            live -= len(parsed["params"])
        else:
            live += len(parsed["params"])
        assert live <= peak_streams


async def test_catch_up_and_update_are_mutually_exclusive() -> None:
    """Astra review, T1.2b resume round 3, finding 1: interleaving a
    concurrent ``update()`` into an in-flight ``catch_up()`` could compute a
    diff against already-stale membership and unsubscribe a symbol the
    other call just re-added. The shared lock must serialize them fully."""
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    class _SlowConnection:
        async def send(self, message: str) -> None:
            send_started.set()
            await release_send.wait()

    controller = SubscriptionController(start=lambda group: None)
    controller.groups["market:0"] = _group("market:0", ["BTCUSDT"])
    controller.live_ws["market:0"] = _SlowConnection()
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = ()

    # opened_with=[]: forces a non-empty SUBSCRIBE diff so catch_up() must
    # actually reach connection.send() (an empty diff short-circuits first).
    catch_up_task = asyncio.ensure_future(controller.catch_up("market:0", [], states))
    await send_started.wait()  # catch_up now holds the lock, blocked inside send()

    update_task = asyncio.ensure_future(
        controller.update(["ETHUSDT"], [], [StreamChannel.TRADES], states)
    )
    await asyncio.sleep(0.01)
    assert not update_task.done()  # blocked behind catch_up's lock, not interleaved

    release_send.set()
    await catch_up_task
    await update_task


def test_controller_add_group_raises_rather_than_start_an_oversized_group() -> None:
    """F12: ``add_group`` is the single choke point every new connection
    (initial ``stream()`` call and universe-diff overflow alike) goes
    through — a group built with more streams than Binance's
    1024-per-connection limit must never reach ``start`` (never be opened)."""
    started: list[SymbolGroup] = []
    controller = SubscriptionController(start=started.append)
    oversized = SymbolGroup(
        key="market:0",
        route="market",
        channels=tuple(StreamChannel),  # all 6 — simulates a future extra channel
        symbols=[f"SYM{i}USDT" for i in range(200)],  # 200 x 6 = 1200 > 1024
    )

    with pytest.raises(ValueError, match="1024"):
        controller.add_group(oversized)

    assert started == []  # never handed to the connect callback


async def test_controller_new_group_from_overflow_is_started_via_the_callback() -> None:
    started: list[SymbolGroup] = []
    controller = SubscriptionController(start=started.append)
    controller.groups["market:0"] = _group("market:0", [f"SYM{i}USDT" for i in range(200)])
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    states["market:0"].subscriptions = tuple(f"sym{i}usdt@aggTrade" for i in range(200))

    await controller.update(["NEWUSDT"], [], [StreamChannel.TRADES], states)

    assert len(started) == 1
    assert started[0].key == "market:1"
    assert "market:1" in controller.groups
