"""T4.67b, pure (no Docker): the three exit rules of a launch position on
replayed frames (``t452b_ws_*`` fixtures and synthetic account frames) —
the first third-party sell (``TradeEvent`` line 3: a holder, not the creator),
the 6 s time stop and the 20 % drawdown from the peak — plus what does **not**
fire: a creation-slot buyer's sell, the rule switched off, a desk position; the
creator's own sell is still ``creator_dump``; two triggers within a second are
one sell; the watcher learns the creator from the position's params when the
token row is missing; the 2 s launch tick runs only launch positions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

import hunter_meme_executor.event_exits as event_exits
import hunter_meme_executor.event_exits_eval as ev
import hunter_meme_executor.event_exits_watch as watch
import hunter_meme_executor.launch_exits as launch_exits
from hunter_meme_executor.event_exits_watch import launch_watch_fields
from hunter_meme_executor.repo import OpenPosition, TokenContext

from .test_event_exits import (
    CREATOR,
    NOW,
    POSITION_ID,
    Db,
    FakeContext,
    _logs_frame,
    _position,
    _runtime,
    _settled,
    _synthetic,
    _watched,
    _wire,
)

pytestmark = pytest.mark.unit

HOLDER = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
"""The seller of fixture line 3 (a holder — happens to be the Mayhem agent's wallet)."""
LAUNCH_PARAMS: dict[str, Any] = {
    "lane": "launch",
    "time_stop_s": 6,
    "max_hold_s": 6,
    "max_drawdown_from_peak_pct": "20",
    "trailing_pct": "20",
    "exit_on_first_third_party_sell": True,
    "creator": CREATOR,
    "creation_slot": None,
    "known_buyers": [],
}


def _launch(**overrides: Any) -> OpenPosition:
    params = {**LAUNCH_PARAMS, **overrides.pop("params", {})}
    return _position(params=params, entry_at=NOW - timedelta(seconds=1), **overrides)


def _sells(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sells: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        sells.append(reason)

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    return sells


# ---- rule 1: the first third-party sell ------------------------------------------------


async def test_the_first_third_party_sell_in_a_trade_event_sells_the_launch_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch()])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    assert w.launch is True and w.third_party_rule is True and w.creator == CREATOR
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await _settled(w)
    assert sells == ["third_party_sell"]
    assert w.third_party_sell_seen is True and rt.stats.third_party_sells_seen_total == 1
    assert db.stamped == [], "a holder's sell is not the creator's"


async def test_a_creation_slot_buyers_sell_is_not_a_third_party_sell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch(params={"known_buyers": [HOLDER]})])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    assert HOLDER in w.known_buyers
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await _settled(w)
    assert sells == [] and w.third_party_sell_seen is False
    assert rt.stats.third_party_sells_seen_total == 0


async def test_the_rule_switched_off_or_a_desk_position_ignores_the_sell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch(params={"exit_on_first_third_party_sell": False})])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await _settled(w)
    assert sells == [] and w.third_party_sell_seen is False
    db.positions[:] = [_position(entry_at=NOW - timedelta(seconds=1))]  # the desk's
    rt2 = _runtime()
    w2 = await _watched(rt2)
    assert w2.launch is False and w2.third_party_rule is False
    await event_exits.handle_notification(rt2, _logs_frame(3), now=NOW)
    await _settled(w2)
    assert sells == []


async def test_the_creators_own_sell_is_still_creator_dump_not_third_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch()])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _logs_frame(4), now=NOW)
    await _settled(w)
    assert sells == ["creator_dump"] and w.third_party_sell_seen is False
    assert db.stamped == [(POSITION_ID, Decimal("0.1"))]


async def test_our_own_sell_never_counts_as_a_third_partys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture's holder re-read as this wallet: the executor's own exit
    landing in the stream must not re-trigger."""
    db = Db(positions=[_launch()])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    ctx = FakeContext()
    ctx.signer.pubkey = HOLDER  # type: ignore[union-attr]
    rt = _runtime(ctx=ctx)
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await _settled(w)
    assert sells == [] and w.third_party_sell_seen is False


# ---- rule 2: the time stop in seconds ------------------------------------------------


async def test_the_six_second_time_stop_fires_on_the_first_frame_past_six_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch()])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    entry = w.position.entry_at
    await event_exits.handle_notification(
        rt, _synthetic(33_000_000_000, slot=1), now=entry + timedelta(seconds=5, milliseconds=900)
    )
    await _settled(w)
    assert sells == [], "5,9 s: not yet"
    await event_exits.handle_notification(
        rt, _synthetic(33_000_000_000, slot=2), now=entry + timedelta(seconds=6)
    )
    await _settled(w)
    assert sells == ["time_stop"]


# ---- rule 3: the drawdown from the peak ---------------------------------------------


async def test_a_twenty_pct_drawdown_from_the_peak_sells_the_launch_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch()])
    _wire(monkeypatch, db)
    sells = _sells(monkeypatch)
    rt = _runtime()
    w = await _watched(rt)
    t = w.position.entry_at
    await event_exits.handle_notification(
        rt, _synthetic(36_000_000_000, slot=1), now=t + timedelta(seconds=1)
    )
    peak = w.high_water
    await event_exits.handle_notification(
        rt, _synthetic(33_000_000_000, slot=2), now=t + timedelta(seconds=2)
    )
    await _settled(w)
    assert sells == [] and w.high_water == peak, "−8 %: inside the 20 %"
    await event_exits.handle_notification(
        rt, _synthetic(28_000_000_000, slot=3), now=t + timedelta(seconds=3)
    )
    await _settled(w)
    assert sells == ["trailing"]


# ---- one sell, whatever fires --------------------------------------------------------


async def test_a_third_party_sell_and_a_drawdown_within_a_second_are_one_sell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = Db(positions=[_launch(high_water_sol=Decimal("0.10"))])
    _wire(monkeypatch, db)
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def sell_on_event(_ctx: Any, position_id: str, reason: str, *, now: Any) -> None:
        calls.append(reason)
        started.set()
        await release.wait()

    monkeypatch.setattr(ev, "sell_on_event", sell_on_event)
    rt = _runtime()
    w = await _watched(rt)
    await event_exits.handle_notification(rt, _logs_frame(3), now=NOW)
    await started.wait()
    await event_exits.handle_notification(
        rt, _synthetic(28_000_000_000, slot=9), now=NOW + timedelta(milliseconds=300)
    )
    assert calls == ["third_party_sell"] and rt.stats.triggered_total == 1
    release.set()
    await _settled(w)
    assert calls == ["third_party_sell"]


# ---- the watcher and the tick ------------------------------------------------------


def test_the_watcher_learns_the_creator_from_the_params_when_the_token_row_is_missing() -> None:
    fields = launch_watch_fields(
        _launch(params={"creation_slot": 448_000_000, "known_buyers": ["A", 7]}), None
    )
    assert fields["creator"] == CREATOR and fields["launch"] is True
    assert fields["creation_slot"] == 448_000_000 and fields["known_buyers"] == {"A"}
    assert launch_watch_fields(_launch(), "someone") == {
        **launch_watch_fields(_launch(), None),
        "creator": "someone",
    }
    assert launch_watch_fields(_position(), None) == {"creator": None}


async def test_a_creation_slot_buy_seen_later_joins_the_known_buyers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs

    db = Db(positions=[_launch(params={"creation_slot": 10**9})])
    _wire(monkeypatch, db)
    rt = _runtime()
    w = await _watched(rt)
    buy_frame = _logs_frame(1)  # a buy of another mint in the fixture — re-addressed by mint filter
    buys = [e for e in trade_events_from_logs(buy_frame.logs) if e.is_buy]
    assert buys, "fixture line 1 is a buy"
    seller = ev.note_third_party_sells(w, buys, slot=10**9 - 1, ours=None)
    assert seller is None and buys[0].user in w.known_buyers
    late = ev.note_third_party_sells(w, buys, slot=10**9 + 1, ours=None)
    assert late is None and len(w.known_buyers) == 1


async def test_the_launch_tick_manages_only_launch_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managed: list[str] = []

    async def manage_position(_ctx: Any, position: OpenPosition, *, now: Any) -> None:
        managed.append(position.id)

    async def open_positions(_session: Any) -> list[OpenPosition]:
        return [_launch(), _position(id="desk-1")]

    class _Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(launch_exits, "manage_position", manage_position)
    monkeypatch.setattr(launch_exits, "open_positions", open_positions)

    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    monkeypatch.setattr(launch_exits, "role_session", session)
    await launch_exits.launch_exits_once(FakeContext())  # type: ignore[arg-type]
    assert managed == [POSITION_ID]


def test_token_context_without_a_creator_still_yields_the_params_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = TokenContext(
        created_at=None,
        creator=None,
        initial_real_token_reserves=None,
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=None,
        features_end_time=None,
        creator_sold=None,
        top10_share=None,
        bundled_share=None,
    )
    assert launch_watch_fields(_launch(), token.creator)["creator"] == CREATOR
    assert watch.launch_watch_fields is launch_watch_fields
