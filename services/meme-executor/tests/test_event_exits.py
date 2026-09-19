"""T4.63, pure (no Docker): the event-driven exits against a ``FakeWs`` and
the T4.52b-1 fixtures (``t452b_ws_*``) — the running peak follows every account
update, ``decide_exit`` fires ``trailing`` on a 20 % drawdown frame, a creator
sell in the ``TradeEvent`` stamps the row and fires ``creator_dump``, the
per-position lock keeps the tick and the event from both sending, the flag off
opens no WebSocket, a bad frame is counted and never a crash, a crash restarts.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import base64
import json
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import hunter_meme_executor.event_exits as event_exits
import hunter_meme_executor.event_exits_eval as ev
import hunter_meme_executor.event_exits_watch as watch
import hunter_meme_executor.exits as exits
from hunter_core.domain.enums import KillSwitchState
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_exchanges.pumpfun.rpc_ws_models import (
    AccountNotification,
    ConnectionState,
    LogsNotification,
    Notification,
    SlotNotification,
)
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.event_exits_config import EventExitsConfig
from hunter_meme_executor.event_exits_runtime import EventExitsRuntime, Watched
from hunter_meme_executor.event_exits_stats import EventExitsStats, heartbeat_fields, percentile
from hunter_meme_executor.repo import OpenPosition, TokenContext
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import MEME_PAPER_V0

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
LOGS_LINES = (FIXTURES / "t452b_ws_logs_notifications_raw.jsonl").read_text().splitlines()
ACCOUNT_LINES = (FIXTURES / "t452b_ws_account_notifications_raw.jsonl").read_text().splitlines()

# The fixture's own creator dump (T4.52b-1 capture): line 3 is a holder's sell,
# line 4 the creator's own sell of the same mint, seconds apart; account lines
# 1 and 2 are the curve after each (``real_sol_reserves`` 14 739 262 → 1).
MINT = "HMfRWjo6HaBSSJSeiFTwCqukKjKoN3qd5BDyWtGepump"
CREATOR = "3moUmVs7CHAtxggNQwQxEDN2A85JFrJ2SN3k2oggDRBD"
PDA = bonding_curve_address(MINT)
LOGS_ID, ACCOUNT_ID = 1, 2
NOW = datetime(2026, 9, 18, 22, 6, 43, tzinfo=UTC)
POSITION_ID = "01994d00-6c1a-7000-8000-000000000201"
PROPOSAL_ID = "01994d00-6c1a-7000-8000-000000000202"
TOKENS = 1_122_717_598_018
CREATOR_INITIAL_TOKENS = Decimal("34857095.24202")
"""Ten times the creator's sell of fixture line 4 (3 485 709,524202 tokens), so
the stamped fraction reads exactly 0,1."""


def _parser() -> SolanaWsClient:
    client = SolanaWsClient()
    for line in LOGS_LINES:
        client._logical_of_server[json.loads(line)["params"]["subscription"]] = LOGS_ID
    for line in ACCOUNT_LINES:
        client._logical_of_server[json.loads(line)["params"]["subscription"]] = ACCOUNT_ID
    return client


def _logs_frame(index: int) -> LogsNotification:
    frame = _parser()._parse_frame(LOGS_LINES[index])
    assert isinstance(frame, LogsNotification)
    return replace(frame, received_at=NOW)


def _account_frame(index: int) -> AccountNotification:
    frame = _parser()._parse_frame(ACCOUNT_LINES[index])
    assert isinstance(frame, AccountNotification)
    return replace(frame, received_at=NOW)


def _encode_curve(
    *, virtual_sol: int, virtual_token: int, real_sol: int, real_token: int, complete: bool = False
) -> str:
    """The legacy 115-byte ``BondingCurve`` layout (``decode.py``), SOL quote."""
    raw = bytes.fromhex("17b7f83760d8ac60")
    raw += struct.pack("<QQQQQ", virtual_token, virtual_sol, real_token, real_sol, 10**15)
    raw += bytes([int(complete)]) + bytes(32) + bytes([0, 0]) + bytes(32)
    return base64.b64encode(raw).decode("ascii")


def _synthetic(virtual_sol: int, *, slot: int, at: datetime = NOW) -> AccountNotification:
    """A curve whose price is set by ``virtual_sol`` (tokens fixed): the mark of a
    fixed position moves with it — the knob these tests turn."""
    return AccountNotification(
        subscription_id=ACCOUNT_ID,
        kind="account",
        slot=slot,
        data_base64=_encode_curve(
            virtual_sol=virtual_sol,
            virtual_token=1_000_000_000_000_000,
            real_sol=max(0, virtual_sol - 30_000_000_000),
            real_token=720_000_000_000_000,
        ),
        encoding="base64",
        owner=PUMP_PROGRAM_ID,
        lamports=0,
        received_at=at,
    )


# ---- doubles ---------------------------------------------------------------------


class FakeWs:
    def __init__(self) -> None:
        self.state = ConnectionState()
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[int] = []
        self.frames: list[Any] = []

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        self.subscribed.append(("logs", mentions[0]))
        return LOGS_ID

    async def subscribe_account(self, pubkey: str, *, commitment: str) -> int:
        self.subscribed.append(("account", pubkey))
        return ACCOUNT_ID

    async def unsubscribe(self, logical_id: int) -> bool:
        self.unsubscribed.append(logical_id)
        return True

    async def aclose(self) -> None:
        return None

    async def listen(self) -> AsyncIterator[Notification]:
        for frame in self.frames:
            yield frame
        await asyncio.sleep(3600)


@dataclass
class FakeChain:
    curve_virtual_sol: int = 33_000_000_000
    curve_reads: int = 0

    def __post_init__(self) -> None:
        g = json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())["result"]["value"]
        self._global = decode_global_account(g["data"][0], owner=g["owner"])

    def global_account(self) -> Any:
        return self._global

    def curve(self, mint: str) -> CurveRead:
        self.curve_reads += 1
        notif = _synthetic(self.curve_virtual_sol, slot=1)
        from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account

        account = decode_bonding_curve_account(notif.data_base64, owner=notif.owner)
        return CurveRead(mint, account, TOKEN_PROGRAM_ID, 1, NOW)


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE


@dataclass
class FakeConfig:
    limits: Any = MEME_PAPER_V0
    event_exits: EventExitsConfig = EventExitsConfig(enabled=True, ws_url="ws://x")
    auto_close_on_emergency: bool = False
    send: SendTuning = SendTuning()
    compute_unit_limit: int = 400_000
    cluster: str = "mainnet"


@dataclass
class FakeSigner:
    pubkey: str = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"


@dataclass
class FakeContext:
    config: FakeConfig = field(default_factory=FakeConfig)
    chain: FakeChain = field(default_factory=FakeChain)
    signer: FakeSigner | None = field(default_factory=FakeSigner)
    kill: FakeKill = field(default_factory=FakeKill)
    session_factory: Any = None
    journal: Any = None
    state: ExecutorState = field(default_factory=ExecutorState)
    event_exits: EventExitsStats = field(default_factory=EventExitsStats)
    event_exits_wake: asyncio.Event = field(default_factory=asyncio.Event)


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _fake_session(_factory: Any, *, db_role: str) -> _Session:
    return _Session()


def _position(**overrides: Any) -> OpenPosition:
    fields: dict[str, Any] = {
        "id": POSITION_ID,
        "proposal_id": PROPOSAL_ID,
        "mint": MINT,
        "entry_at": NOW - timedelta(seconds=60),
        "tokens": TOKENS,
        "sol_spent_lamports": 50_000_000,
        "initial_risk_sol": Decimal("0.05"),
        "params": {"target_x": "1.3", "trailing_pct": "20", "max_hold_s": 300},
        "mark_sol": None,
        "high_water_sol": None,
        "exit_intent": None,
        "sell_requested_at": None,
        "sell_requested_by": None,
        "migrated": False,
    }
    fields.update(overrides)
    return OpenPosition(**fields)


@dataclass
class Db:
    """What the runtime writes without Postgres: marks, stamps, and the rows it reads."""

    positions: list[OpenPosition]
    marks: list[tuple[str, Decimal | None, str]] = field(
        default_factory=list[tuple[str, Decimal | None, str]]
    )
    stamped: list[tuple[str, Decimal]] = field(default_factory=list[tuple[str, Decimal]])
    submitted_at: datetime | None = None
    creator_initial_tokens: Decimal | None = CREATOR_INITIAL_TOKENS
    """``meme_tokens.creator_initial_tokens`` (``0048``) — the denominator of the
    fraction a creator sell stamps; ``None`` on a coin whose create frame we never saw."""


def _wire(monkeypatch: pytest.MonkeyPatch, db: Db) -> None:
    async def open_positions(_session: Any) -> list[OpenPosition]:
        return list(db.positions)

    async def open_position(_session: Any, position_id: str) -> OpenPosition | None:
        return next((p for p in db.positions if p.id == position_id), None)

    async def token_context(_session: Any, mint: str, *, now: Any = None) -> TokenContext:
        return TokenContext(
            created_at=NOW - timedelta(seconds=120),
            creator=CREATOR,
            initial_real_token_reserves=793_100_000,
            completed_at=None,
            migrated_at=None,
            curve_volume_1m_sol=None,
            features_end_time=None,
            creator_sold=None,
            top10_share=None,
            bundled_share=None,
            creator_initial_tokens=db.creator_initial_tokens,
        )

    async def update_mark(
        _session: Any, position_id: str, *, mark_sol: Any, source: str, **_: Any
    ) -> None:
        db.marks.append((position_id, mark_sol, source))

    async def stamp_creator_sold(
        _session: Any, position_id: str, *, at: Any, fraction: Decimal, now: Any
    ) -> bool:
        assert 0 < fraction <= 1, fraction  # the row's CHECK, enforced by the fake too
        db.stamped.append((position_id, fraction))
        return True

    async def latest_sell_submitted_at(_session: Any, proposal_id: str) -> datetime | None:
        return db.submitted_at

    for module in (ev, watch, exits):
        monkeypatch.setattr(module, "role_session", _fake_session)
    monkeypatch.setattr(watch, "open_positions", open_positions)
    monkeypatch.setattr(watch, "token_context", token_context)
    monkeypatch.setattr(exits, "open_position", open_position)
    monkeypatch.setattr(exits, "token_context", token_context)
    monkeypatch.setattr(exits, "update_mark", update_mark)
    monkeypatch.setattr(ev, "update_mark", update_mark)
    monkeypatch.setattr(ev, "stamp_creator_sold", stamp_creator_sold)
    monkeypatch.setattr(ev, "latest_sell_submitted_at", latest_sell_submitted_at)


def _runtime(ws: FakeWs | None = None, ctx: FakeContext | None = None) -> EventExitsRuntime:
    ctx = ctx or FakeContext()
    return EventExitsRuntime(ctx=ctx, ws=ws or FakeWs(), config=ctx.config.event_exits)  # type: ignore[arg-type]


async def _watched(rt: EventExitsRuntime) -> Watched:
    await event_exits.sync_watch(rt, now=NOW)
    return rt.watched[POSITION_ID]


async def _settled(w: Watched) -> None:
    if w.selling is not None:
        await w.selling


# ---- the flag ----------------------------------------------------------------------


def test_the_flag_is_off_by_default_and_only_on_turns_it_on() -> None:
    assert EventExitsConfig.from_env({}).enabled is False
    assert EventExitsConfig.from_env({"MEME_EVENT_EXITS": "on"}).enabled is True
    assert EventExitsConfig.from_env({"MEME_EVENT_EXITS": "shadow"}).enabled is False
    assert EventExitsConfig.from_env({"MEME_EVENT_EXITS": "1"}).enabled is False


def test_flag_off_opens_no_websocket_and_publishes_off() -> None:
    off = EventExitsConfig.from_env({})
    assert event_exits.event_exits_client(off) is None
    fields = heartbeat_fields(EventExitsStats(ws_state="connected"), now=NOW, enabled=False)
    assert fields["event_exits_ws_state"] == "off"
    assert fields["event_exits_enabled"] == "false"
    on = EventExitsConfig.from_env(
        {"MEME_EVENT_EXITS": "on", "SOLANA_RPC_URL": "https://example.invalid/?api-key=FAKE"}
    )
    client = event_exits.event_exits_client(on)
    assert client is not None and client._url == "wss://example.invalid/?api-key=FAKE"


# ---- subscriptions -------------------------------------------------------------------


async def test_sync_subscribes_the_open_position_and_unsubscribes_when_it_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position(high_water_sol=Decimal("0.07"))])
    _wire(monkeypatch, db)
    ws = FakeWs()
    rt = _runtime(ws)
    w = await _watched(rt)
    assert ws.subscribed == [("logs", PDA), ("account", PDA)]
    assert w.creator == CREATOR and w.high_water == Decimal("0.07")
    assert rt.stats.subscriptions == 2 and rt.by_logical == {
        LOGS_ID: POSITION_ID,
        ACCOUNT_ID: POSITION_ID,
    }
    await event_exits.sync_watch(rt, now=NOW)
    assert len(ws.subscribed) == 2, "already watched: not subscribed twice"
    db.positions.clear()
    rt.ctx.state.exit_locks[POSITION_ID] = asyncio.Lock()
    await event_exits.sync_watch(rt, now=NOW)
    assert rt.watched == {} and sorted(ws.unsubscribed) == [LOGS_ID, ACCOUNT_ID]
    assert rt.stats.subscriptions == 0
    assert POSITION_ID not in rt.ctx.state.exit_locks, "the lock of a closed position is pruned"


async def test_subscriptions_are_bounded_by_max_open_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = _position(
        id="01994d00-6c1a-7000-8000-000000000301",
        proposal_id="01994d00-6c1a-7000-8000-000000000302",
    )
    db = Db(positions=[_position(), second])
    _wire(monkeypatch, db)
    ctx = FakeContext(
        config=FakeConfig(limits=MEME_PAPER_V0.model_copy(update={"max_open_positions": 1}))
    )
    rt = _runtime(ctx=ctx)
    await event_exits.sync_watch(rt, now=NOW)
    assert list(rt.watched) == [POSITION_ID]
    assert rt.stats.subscriptions == 2 <= 2 * ctx.config.limits.max_open_positions


# ---- peak and the 20 % drawdown --------------------------------------------------------


async def test_the_peak_follows_every_account_update_and_trailing_fires_on_a_20pct_drawdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position()])
    _wire(monkeypatch, db)
    sells: list[tuple[str, str]] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append((position_id, reason))

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    # 33 → 36 SOL of virtual reserves: the mark rises, the peak with it, nothing fires.
    await event_exits.handle_notification(rt, _synthetic(33_000_000_000, slot=1), now=NOW)
    first_peak = w.high_water
    assert first_peak > 0 and sells == []
    await event_exits.handle_notification(
        rt, _synthetic(36_000_000_000, slot=2), now=NOW + timedelta(seconds=1)
    )
    assert w.high_water > first_peak and sells == []
    peak = w.high_water
    # 36 → 34 SOL: −6 %, inside the 20 % trailing — still nothing.
    await event_exits.handle_notification(
        rt, _synthetic(34_000_000_000, slot=3), now=NOW + timedelta(seconds=2)
    )
    assert w.high_water == peak and sells == [] and rt.stats.triggered_total == 0
    # 36 → 28 SOL in one frame: the mark is ≤ 80 % of the peak — CITIZEN's frame.
    await event_exits.handle_notification(
        rt, _synthetic(28_000_000_000, slot=4), now=NOW + timedelta(seconds=3)
    )
    await _settled(w)
    assert sells == [(POSITION_ID, "trailing")]
    assert rt.stats.triggered_total == 1 and rt.stats.updates_60s(NOW + timedelta(seconds=3)) == 4
    assert w.high_water == peak, "a drawdown never lowers the peak"
    assert db.marks[-1][2] == "solana_rpc" and db.marks[-1][1] is not None


async def test_target_fires_on_the_frame_that_crosses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Db(positions=[_position(sol_spent_lamports=10_000_000, initial_risk_sol=Decimal("0.01"))])
    _wire(monkeypatch, db)
    sells: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append(reason)

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _synthetic(60_000_000_000, slot=1), now=NOW)
    await _settled(w)
    assert sells == ["target"], f"mark {w.high_water} vs 1.3 × 0.01 SOL"


async def test_a_second_trigger_within_a_second_or_with_a_sell_in_flight_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position(high_water_sol=Decimal("0.10"))])
    _wire(monkeypatch, db)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _synthetic(30_000_000_000, slot=1), now=NOW)
    await started.wait()
    for i in range(5):  # a burst while the sell is in flight
        await event_exits.handle_notification(
            rt, _synthetic(29_000_000_000, slot=2 + i), now=NOW + timedelta(milliseconds=100 * i)
        )
    assert calls == 1 and rt.stats.triggered_total == 1
    release.set()
    await _settled(w)
    # Done, but inside the 1 s debounce: still one.
    await event_exits.handle_notification(
        rt, _synthetic(29_000_000_000, slot=9), now=NOW + timedelta(milliseconds=900)
    )
    assert rt.stats.triggered_total == 1
    await event_exits.handle_notification(
        rt, _synthetic(29_000_000_000, slot=10), now=NOW + timedelta(seconds=1, milliseconds=100)
    )
    await _settled(w)
    assert rt.stats.triggered_total == 2 and calls == 2


# ---- the creator's sell in the trade event --------------------------------------------


async def test_a_creator_sell_in_the_trade_event_stamps_the_row_and_fires_creator_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position()])
    _wire(monkeypatch, db)
    sells: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append(reason)

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    # Line 3: a holder's sell — not the creator's. Nothing stamped, nothing fired.
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await _settled(w)
    assert db.stamped == [] and sells == [] and w.creator_sold is False
    # Line 4: the creator himself sells. Stamped once, ``creator_dump`` fires on this frame.
    await event_exits.handle_notification(rt, _logs_frame(4), now=NOW + timedelta(seconds=2))
    await _settled(w)
    assert db.stamped == [(POSITION_ID, Decimal("0.1"))] and w.creator_sold is True
    assert sells == ["creator_dump"]
    assert rt.stats.creator_sells_seen_total == 1
    assert (
        rt.ctx.state.creator_sold_on_chain.seen_at(MINT, now=NOW + timedelta(seconds=2)) is not None
    )
    # The account frame of the same drain (line 2) does not stamp again.
    await event_exits.handle_notification(rt, _account_frame(2), now=NOW + timedelta(seconds=3))
    assert db.stamped == [(POSITION_ID, Decimal("0.1"))]


async def test_a_creator_sell_without_a_recorded_allocation_fires_but_stamps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``creator_sold_fraction`` is ``sold ÷ allocation`` and the row's CHECK
    refuses a stamp without it: with ``creator_initial_tokens`` unknown (pre-``0048``
    coin) the sell is remembered in memory, ``creator_dump`` still fires on the
    event, and nothing is written that the schema would reject."""
    db = Db(positions=[_position()], creator_initial_tokens=None)
    _wire(monkeypatch, db)
    sells: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append(reason)

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _logs_frame(4), now=NOW)
    await _settled(w)
    assert db.stamped == [] and w.creator_sold is True and sells == ["creator_dump"]
    assert rt.stats.creator_sells_seen_total == 1
    assert rt.ctx.state.creator_sold_on_chain.seen_at(MINT, now=NOW) is not None


def test_the_stamped_fraction_is_sold_over_the_allocation_capped_at_one() -> None:
    sold = 3_485_709_524_202  # sub-units, fixture line 4
    assert ev.creator_sold_fraction(sold, CREATOR_INITIAL_TOKENS) == Decimal("0.1")
    assert ev.creator_sold_fraction(sold, Decimal("1000000")) == Decimal(1), "sold > allocation"
    assert ev.creator_sold_fraction(sold, None) is None
    assert ev.creator_sold_fraction(sold, Decimal(0)) is None, "no allocation, no fraction"
    assert ev.creator_sold_fraction(0, CREATOR_INITIAL_TOKENS) is None
    tiny = ev.creator_sold_fraction(1, Decimal("1000000000"))
    assert tiny is not None and tiny == Decimal("0.000001"), "never rounded down to zero"


async def test_a_failed_instruction_is_not_a_trade(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Db(positions=[_position()])
    _wire(monkeypatch, db)
    rt = _runtime()
    await _watched(rt)
    assert _logs_frame(0).err is not None
    assert await event_exits.handle_notification(rt, _logs_frame(0), now=NOW) is None
    assert rt.stats.updates_60s(NOW) == 0


# ---- the lock: the tick and the event never both send -----------------------------------


async def test_the_lock_keeps_the_tick_and_the_event_from_both_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both paths decide ``trailing`` for the same position at the same instant:
    exactly one ``_sell``; the second one in re-reads the row, finds it closed."""
    db = Db(positions=[_position(high_water_sol=Decimal("0.10"))])
    _wire(monkeypatch, db)
    ctx = FakeContext(chain=FakeChain(curve_virtual_sol=28_000_000_000))
    sends: list[str] = []

    async def latest_sell_order(_session: Any, proposal_id: str) -> None:
        return None

    async def _sell(
        _ctx: Any, position: OpenPosition, read: Any, reason: str, attempt: int, now: Any
    ) -> None:
        sends.append(reason)
        await asyncio.sleep(0.05)  # the send in flight
        db.positions.clear()  # confirmed: the row is closed

    monkeypatch.setattr(exits, "latest_sell_order", latest_sell_order)
    monkeypatch.setattr(exits, "_sell", _sell)
    position = db.positions[0]
    await asyncio.gather(
        exits.sell_on_event(ctx, POSITION_ID, "trailing", now=NOW),  # type: ignore[arg-type]
        exits.manage_position(ctx, position, now=NOW),  # type: ignore[arg-type]
        exits.sell_on_event(ctx, POSITION_ID, "trailing", now=NOW),  # type: ignore[arg-type]
    )
    assert sends == ["trailing"], sends
    assert ctx.chain.curve_reads == 1, "only the path that sold read the curve for the build"


async def test_the_event_path_reads_a_fresh_curve_for_the_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position()])
    _wire(monkeypatch, db)
    ctx = FakeContext(chain=FakeChain(curve_virtual_sol=31_000_000_000))
    routed: list[tuple[str, bool, bool]] = []

    async def route_exit(
        _ctx: Any,
        position: OpenPosition,
        read: Any,
        reason: str,
        *,
        migrated: bool,
        complete: bool,
        now: Any,
    ) -> None:
        routed.append(
            (
                reason,
                read is not None and read.account.virtual_sol_reserves == 31_000_000_000,
                complete,
            )
        )

    monkeypatch.setattr(exits, "route_exit", route_exit)
    await exits.sell_on_event(ctx, POSITION_ID, "creator_dump", now=NOW)  # type: ignore[arg-type]
    assert routed == [("creator_dump", True, False)]
    assert ctx.chain.curve_reads == 1


async def test_without_a_signer_the_event_path_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position()])
    _wire(monkeypatch, db)
    ctx = FakeContext(signer=None)
    await exits.sell_on_event(ctx, POSITION_ID, "trailing", now=NOW)  # type: ignore[arg-type]
    assert ctx.chain.curve_reads == 0


# ---- marks ------------------------------------------------------------------------------


async def test_marks_are_written_at_most_once_a_second_except_a_new_peak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Peak 1,2 % above the frames' mark (0,03654): no new peak, no trailing (20 %).
    db = Db(positions=[_position(high_water_sol=Decimal("0.037"))])
    _wire(monkeypatch, db)
    rt = _runtime()
    await _watched(rt)
    for i in range(5):  # five frames in 400 ms, none a new peak, none fires
        await event_exits.handle_notification(
            rt, _synthetic(33_000_000_000 - i, slot=i), now=NOW + timedelta(milliseconds=100 * i)
        )
    assert len(db.marks) == 1
    await event_exits.handle_notification(
        rt, _synthetic(33_000_000_000, slot=9), now=NOW + timedelta(seconds=1, milliseconds=100)
    )
    assert len(db.marks) == 2
    assert rt.stats.marks_written_total == 2


async def test_the_mark_of_a_frame_that_fires_is_always_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two frames 100 ms apart: the first writes the mark, the second is inside
    the throttle **but fires** ``trailing`` — the row must carry the mark the
    decision was made on, so the close and the desk read the same number."""
    db = Db(positions=[_position(high_water_sol=Decimal("0.037"))])
    _wire(monkeypatch, db)
    sells: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append(reason)

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _synthetic(33_000_000_000, slot=1), now=NOW)
    assert len(db.marks) == 1 and sells == [] and rt.stats.triggered_total == 0
    await event_exits.handle_notification(
        rt, _synthetic(20_000_000_000, slot=2), now=NOW + timedelta(milliseconds=100)
    )
    await _settled(w)
    assert sells == ["trailing"]
    assert len(db.marks) == 2, "the firing frame's mark is written despite the throttle"
    assert db.marks[-1][1] is not None and db.marks[-1][1] < Decimal("0.037") * Decimal("0.8")


# ---- resilience --------------------------------------------------------------------------


async def test_a_bad_frame_is_counted_and_the_loop_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_position(high_water_sol=Decimal("0.5"))])
    _wire(monkeypatch, db)
    rt = _runtime()
    await _watched(rt)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    bad = replace(_synthetic(33_000_000_000, slot=1), data_base64="not base64!")
    await queue.put(bad)
    await queue.put(_synthetic(33_000_000_000, slot=2))
    task = asyncio.create_task(event_exits._handle_loop(rt, queue))
    try:
        for _ in range(200):
            if queue.empty() and rt.stats.updates_60s(NOW) == 1:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert rt.stats.bad_frames_total == 1 and rt.stats.updates_60s(NOW) == 1


async def test_the_read_loop_counts_reconnects_and_drops_when_the_queue_is_full() -> None:
    ws = FakeWs()
    ws.frames = [
        SlotNotification(subscription_id=9, kind="slot", slot=i, parent=0, root=0, received_at=NOW)
        for i in range(3)
    ]
    ws.state.reconnects = 1
    rt = _runtime(ws)
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=2)
    task = asyncio.create_task(event_exits._read_loop(rt, queue))
    try:
        for _ in range(200):
            if rt.stats.dropped_total == 1:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert rt.stats.dropped_total == 1 and rt.stats.reconnects_total == 1


async def test_run_forever_restarts_after_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    rt = _runtime(
        ctx=FakeContext(
            config=FakeConfig(event_exits=EventExitsConfig(enabled=True, restart_delay_s=0.01))
        )
    )
    calls: list[int] = []

    async def run_event_exits(_rt: Any) -> None:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise RuntimeError("ws exploded")
        await asyncio.sleep(3600)

    monkeypatch.setattr(event_exits, "run_event_exits", run_event_exits)
    task = asyncio.create_task(event_exits.run_event_exits_forever(rt))
    try:
        for _ in range(200):
            if len(calls) == 2:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(calls) == 2 and rt.stats.restarts_total == 1


# ---- heartbeat --------------------------------------------------------------------------


def test_heartbeat_publishes_the_latency_percentiles_and_counters() -> None:
    stats = EventExitsStats(ws_state="connected", subscriptions=2, triggered_total=3)
    for s in (0.4, 0.9, 1.2, 5.0):
        stats.record_submit_latency(s)
    stats.record_update(NOW - timedelta(seconds=61))
    stats.record_update(NOW - timedelta(seconds=5))
    fields = heartbeat_fields(stats, now=NOW, enabled=True)
    assert fields["event_exits_ws_state"] == "connected"
    assert fields["event_exits_subscriptions"] == "2"
    assert fields["event_exits_updates_60s"] == "1"
    assert fields["event_exits_triggered_total"] == "3"
    assert fields["event_to_sell_submit_s_p50"] == "1.050"
    assert fields["event_to_sell_submit_s_p95"] == "5.000"
    assert percentile([2.0], 0.95) == 2.0
    empty = heartbeat_fields(EventExitsStats(), now=NOW, enabled=True)
    assert empty["event_to_sell_submit_s_p50"] == "" and empty["event_to_sell_submit_s_p95"] == ""
