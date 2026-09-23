"""T4.90b — a sell the chain confirmed is a closed position, whoever saw it
confirm, and a sell is always read back with the decoder of the venue it was
SENT to.

Three holes the T4.90 audit found (``.claude/state/astra-review-t490.md``):

1. The 30 s reconcile (``main.reconcile_once``) confirmed a sell and never
   closed its position; a later exit then found zero tokens and parked it as
   ``blocked:no_tokens_on_chain``. And a confirmed row read back from Postgres
   carries its fill as JSON, which ``isinstance(FillRecord)`` refused — so even
   the direct path could not close from it. Now the JSON is parsed into a
   typed ``StoredSellFill`` (venue-checked, never a loose dict) and the
   position closes from it.
2. (spot, ``test_spot_reconcile_repair.py``.)
3. A curve sell reconciled after the coin migrated went through
   ``decode_pumpswap_fills``, whose payer-delta fallback "decodes" any landed
   transaction — a curve sale booked as a PumpSwap one.

Pure (no Docker, no network): the chain is a scripted fake RPC (test fixture)
serving the real recorded mainnet curve sell ``t48b_rpc_tx_sell_raw.json``; the
database writes are recorded fakes. The SQL and the full ticks are proven on
Postgres in ``test_exit_retry_integration.py``.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

import hunter_meme_executor.exit_settle as exit_settle
import hunter_meme_executor.pumpswap_settle as pumpswap_settle
from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_meme_executor.fills import decode_fills
from hunter_meme_executor.journal_db import fill_jsonable
from hunter_meme_executor.pumpswap_build import decode_pumpswap_fills
from hunter_meme_executor.repo import OrderRow
from hunter_meme_executor.repo_positions import ConfirmedSell
from hunter_meme_executor.stored_fill import StoredSellFill, parse_stored_sell_fill

from .test_exit_no_tokens_reconcile import (
    CONFIRMED,
    KEY,
    LAST_VALID,
    NOW,
    ORDER_ID,
    SELL_TX,
    SIGNATURE,
    ScriptedRpc,
    _Sessions,
)

pytestmark = pytest.mark.unit

CURVE_NET = 1_207_696_649
"""The recorded sell's real payer delta — what the wallet received."""
BLOCK_TIME = datetime(2026, 9, 12, 17, 52, 42, tzinfo=UTC)
PUMPSWAP_SIG = "PumpSwapSig111"
PUMPSWAP_TX: dict[str, Any] = {
    "slot": 447586200,
    "blockTime": int(BLOCK_TIME.timestamp()),
    "meta": {
        "err": None,
        "fee": 5000,
        "preBalances": [100_000_000, 0],
        "postBalances": [100_018_953, 0],
        "innerInstructions": [],
    },
    "transaction": {"signatures": [PUMPSWAP_SIG], "message": {"accountKeys": []}},
}


def _stored(fill: object) -> Any:
    """What ``PostgresOrderJournal.record_state`` writes and a read gives back."""
    return json.loads(json.dumps(fill_jsonable(fill), default=str))


CURVE_STORED: dict[str, Any] = _stored(decode_fills(SELL_TX)[0])
PUMPSWAP_STORED: dict[str, Any] = _stored(decode_pumpswap_fills(PUMPSWAP_TX)[0])


# ------------------------------------------------------------- the typed parse
def test_a_stored_curve_sell_fill_parses_back_to_the_chain_numbers() -> None:
    fill = parse_stored_sell_fill(CURVE_STORED, venue="curve")
    assert isinstance(fill, StoredSellFill)
    assert fill.venue == "curve" and fill.signature == SIGNATURE
    assert fill.sell_net_lamports == CURVE_NET and fill.block_time == BLOCK_TIME
    assert fill.ata_rent_refund_lamports == CURVE_STORED["ata_rent_refund_lamports"]
    assert fill.as_json()["is_buy"] is False and fill.as_json()["settled_from"] == "stored_fill"


def test_a_stored_pumpswap_sell_fill_parses_back_to_the_chain_numbers() -> None:
    fill = parse_stored_sell_fill(PUMPSWAP_STORED, venue="pumpswap")
    assert isinstance(fill, StoredSellFill)
    assert fill.venue == "pumpswap" and fill.signature == PUMPSWAP_SIG
    assert fill.sell_net_lamports == 18_953 and fill.ata_rent_refund_lamports is None
    assert fill.block_time == BLOCK_TIME


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    out = dict(base)
    for key, value in changes.items():
        if value is ...:
            out.pop(key, None)
        else:
            out[key] = value
    return out


@pytest.mark.parametrize(
    ("raw", "venue", "why"),
    [
        ("not a dict", "curve", "a string is not a fill"),
        (None, "curve", "no fill at all"),
        (CURVE_STORED, "pumpswap", "a curve fill asked as a PumpSwap one"),
        (PUMPSWAP_STORED, "curve", "a PumpSwap fill asked as a curve one"),
        (_with(CURVE_STORED, is_buy=True), "curve", "a buy is not a sell"),
        (_with(CURVE_STORED, is_buy=...), "curve", "a curve fill names its side"),
        (_with(CURVE_STORED, signature=""), "curve", "no signature"),
        (_with(CURVE_STORED, sell_net_lamports=None), "curve", "no net"),
        (_with(CURVE_STORED, sell_net_lamports="1207696649"), "curve", "a string net"),
        (_with(CURVE_STORED, sell_net_lamports=True), "curve", "a bool is not lamports"),
        (_with(CURVE_STORED, block_time="2026-09-12T17:52:42"), "curve", "a naive time"),
        (_with(CURVE_STORED, block_time="yesterday"), "curve", "not a time"),
        (_with(CURVE_STORED, ata_rent_refund_lamports="0"), "curve", "a string refund"),
        (_with(CURVE_STORED, venue="pumpswap"), "curve", "venue marker disagrees"),
    ],
)
def test_a_malformed_or_foreign_stored_fill_is_refused(raw: object, venue: str, why: str) -> None:
    assert parse_stored_sell_fill(raw, venue=venue) is None, why


def test_a_stored_fill_without_a_block_time_is_still_a_fill() -> None:
    fill = parse_stored_sell_fill(_with(CURVE_STORED, block_time=None), venue="curve")
    assert fill is not None and fill.block_time is None


# ----------------------------------------------------------------- the rig
def _position(**changes: Any) -> Any:
    base: dict[str, Any] = {
        "id": "pos-1",
        "proposal_id": "prop-1",
        "mint": "Mint111",
        "tokens": 1_000,
        "sol_spent_lamports": 1_000_000_000,
        "initial_risk_sol": None,
        "params": {},
        "exit_intent": {"reason": "time_stop", "attempt": 1},
        "migrated": False,
    }
    base.update(changes)
    return SimpleNamespace(**base)


@dataclass
class Rig:
    rpc: ScriptedRpc
    journal: InMemoryOrderJournal
    ctx: Any
    confirmed: list[ConfirmedSell] = field(default_factory=lambda: list[ConfirmedSell]())
    expired: list[OrderRow] = field(default_factory=lambda: list[OrderRow]())
    open_ids: set[str] = field(default_factory=lambda: {"pos-1"})
    closed: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    blocked: list[str] = field(default_factory=lambda: list[str]())
    intents: dict[str, dict[str, Any]] = field(default_factory=lambda: dict[str, dict[str, Any]]())


def _rig(monkeypatch: pytest.MonkeyPatch, *, tx: dict[str, Any] = SELL_TX) -> Rig:
    rpc = ScriptedRpc({SIGNATURE: [CONFIRMED], PUMPSWAP_SIG: [CONFIRMED]})
    rpc_any: Any = rpc

    def get_transaction(signature: str, *, commitment: str = "confirmed") -> dict[str, Any]:
        rpc.calls.append(f"transaction:{signature}")
        return tx

    rpc_any.get_transaction = get_transaction
    state = SimpleNamespace(
        exits_confirmed=0,
        blocked_exits={},
        ata_closed=0,
        exit_locks={},
        rpc_errors=0,
        settle_errors=0,
    )
    ctx = SimpleNamespace(
        chain=SimpleNamespace(rpc=rpc),
        journal=InMemoryOrderJournal(),
        config=SimpleNamespace(cluster="mainnet"),
        state=state,
        session_factory=None,
    )
    rig = Rig(rpc, ctx.journal, ctx)

    async def confirmed_sells(_s: Any, proposal_id: str) -> list[ConfirmedSell]:
        return [c for c in rig.confirmed if c.proposal_id == proposal_id]

    async def positions_with_confirmed_sell(_s: Any) -> list[str]:
        return sorted({c.position_id for c in rig.confirmed})

    async def expired_sell_orders(_s: Any, _proposal_id: str) -> list[OrderRow]:
        return rig.expired

    async def open_position(_s: Any, position_id: str) -> Any:
        if position_id not in rig.open_ids:
            return None
        proposal_id = position_id.replace("pos-", "prop-")
        return _position(
            id=position_id, proposal_id=proposal_id, exit_intent=rig.intents.get(position_id)
        )

    async def close_position(_s: Any, position_id: str, **kwargs: Any) -> bool:
        if position_id not in rig.open_ids:
            return False
        rig.open_ids.discard(position_id)
        rig.closed.append({"position_id": position_id, **kwargs})
        return True

    async def mark_blocked(_c: Any, position: Any, reason: str, block: str, _now: Any) -> None:
        rig.blocked.append(block)
        rig.intents[position.id] = {"reason": reason, "blocked": block}

    for module in (exit_settle, pumpswap_settle):
        monkeypatch.setattr(module, "role_session", _Sessions())
        monkeypatch.setattr(module, "close_position", close_position)
    monkeypatch.setattr(exit_settle, "confirmed_sells", confirmed_sells)
    monkeypatch.setattr(exit_settle, "positions_with_confirmed_sell", positions_with_confirmed_sell)
    monkeypatch.setattr(exit_settle, "expired_sell_orders", expired_sell_orders)
    monkeypatch.setattr(exit_settle, "open_position", open_position)
    monkeypatch.setattr(exit_settle, "mark_blocked", mark_blocked)
    return rig


def _signed(journal: InMemoryOrderJournal, key: str, signature: str) -> None:
    journal.begin_signing(key)
    journal.record_signature(key, signature, last_valid_block_height=LAST_VALID)
    journal.record_state(key, SubmitState.SUBMITTED_UNCONFIRMED, "confirmation_timeout", None)
    journal.release_signing(key)


def _confirmed_sell(
    fill: Any = CURVE_STORED, *, intent: dict[str, Any] | None = None, signature: str = SIGNATURE
) -> ConfirmedSell:
    return ConfirmedSell(
        order_id=ORDER_ID,
        proposal_id="prop-1",
        position_id="pos-1",
        tx_signature=signature,
        intent={"exit_reason": "target"} if intent is None else intent,
        fill=fill,
    )


def _order(status: str, *, intent: dict[str, Any] | None = None, key: str = KEY) -> OrderRow:
    return OrderRow(ORDER_ID, "prop-1", "sell", key, 1, status, None, intent or {}, {})


# ------------------------------------------ 1. a confirmed sell closes the position
def test_a_replayed_confirmed_row_closes_the_position_from_its_stored_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 30 s reconcile confirmed the row first; the exits tick's reconcile
    then gets the REPLAY — the fill as JSON, not a ``FillRecord``. Before
    T4.90b that returned ``False`` and the position stayed open."""
    rig = _rig(monkeypatch)
    _signed(rig.journal, KEY, SIGNATURE)
    rig.journal.record_state(KEY, SubmitState.CONFIRMED, "trade_event", CURVE_STORED)
    closed = asyncio.run(exit_settle.reconcile_sell(rig.ctx, _position(), KEY, ORDER_ID))
    assert closed is True
    (row,) = rig.closed
    assert row["exit_order_id"] == ORDER_ID and row["sol_received_lamports"] == CURVE_NET
    assert row["exit_at"] == BLOCK_TIME and row["exit_payload"]["reason"] == "time_stop"
    assert rig.rpc.calls == [], "a replay asks the chain nothing"


def test_a_replayed_row_whose_fill_is_foreign_does_not_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    _signed(rig.journal, KEY, SIGNATURE)
    rig.journal.record_state(KEY, SubmitState.CONFIRMED, "trade_event", PUMPSWAP_STORED)
    closed = asyncio.run(exit_settle.reconcile_sell(rig.ctx, _position(), KEY, ORDER_ID))
    assert closed is False and rig.closed == []


def test_a_confirmed_latest_sell_closes_the_position_and_is_never_sold_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell()]
    handled = asyncio.run(
        exit_settle.settle_latest(rig.ctx, _position(), _order("confirmed"), "sell_now", NOW)
    )
    assert handled is True, "the caller must not build another sell"
    (row,) = rig.closed
    assert row["exit_order_id"] == ORDER_ID and row["sol_received_lamports"] == CURVE_NET
    assert row["exit_payload"]["reason"] == "target", "the reason the ORDER was sent for"
    assert row["exit_payload"]["settled_from"] == "stored_fill"
    assert rig.blocked == [] and rig.rpc.calls == []
    assert rig.ctx.state.exits_confirmed == 1


def test_a_confirmed_latest_sell_with_an_unreadable_fill_is_blocked_by_name_not_resold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell(fill={"garbage": True})]
    handled = asyncio.run(
        exit_settle.settle_latest(rig.ctx, _position(), _order("confirmed"), "sell_now", NOW)
    )
    assert handled is True and rig.closed == []
    assert rig.blocked == ["reconciliation_mismatch:confirmed_sell_unsettled"]


def test_a_stored_fill_of_another_signature_is_never_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell(signature="SomeOtherSig")]
    asyncio.run(
        exit_settle.settle_latest(rig.ctx, _position(), _order("confirmed"), "sell_now", NOW)
    )
    assert rig.closed == [], "a fill must be of this order's own transaction"


def test_a_failed_latest_sell_is_left_to_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _rig(monkeypatch)
    handled = asyncio.run(
        exit_settle.settle_latest(rig.ctx, _position(), _order("failed"), "sell_now", NOW)
    )
    assert handled is False and rig.closed == [] and rig.rpc.calls == []


def test_an_empty_wallet_closes_from_a_confirmed_sell_before_asking_the_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The brief's scenario: the reconcile confirmed the sell, a rule fired,
    ``_sell`` found zero tokens. Before T4.90b: ``blocked:no_tokens_on_chain``."""
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell()]
    asyncio.run(exit_settle.no_tokens_on_chain(rig.ctx, _position(), "time_stop", NOW))
    assert rig.blocked == [] and len(rig.closed) == 1 and rig.rpc.calls == []


def test_the_sweep_closes_every_open_position_whose_sell_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    gone = ConfirmedSell("o-2", "prop-2", "pos-2", "Sig2", {}, CURVE_STORED)
    rig.confirmed = [_confirmed_sell(), gone]  # pos-2 was closed meanwhile
    asyncio.run(exit_settle.repair_confirmed_sells(rig.ctx))
    assert [c["position_id"] for c in rig.closed] == ["pos-1"]
    assert rig.rpc.calls == [], "the repair reads the row, never the chain"
    asyncio.run(exit_settle.repair_confirmed_sells(rig.ctx))
    assert len(rig.closed) == 1, "idempotent: a closed position is not closed twice"


# ------------------------- one poisoned close never stops the others (review M1)
CLOSE_FAILED = "reconciliation_mismatch:confirmed_sell_close_failed:RuntimeError"


def _poison_close(monkeypatch: pytest.MonkeyPatch, poisoned: str) -> None:
    """Stands in for ``ck_meme_live_positions_an_exit_is_after_the_entry``: a
    wall-clock ``entry_at`` with microseconds, a second-precision ``block_time``
    in the same second — the UPDATE is refused by the database."""
    real_close = exit_settle.close_position

    async def close(session: Any, position_id: str, **kwargs: Any) -> bool:
        if position_id == poisoned:
            raise RuntimeError("IntegrityError: ck_meme_live_positions_an_exit_is_after_the_entry")
        return await real_close(session, position_id, **kwargs)

    monkeypatch.setattr(exit_settle, "close_position", close)


def _two_orphans(rig: Rig) -> None:
    rig.open_ids = {"pos-1", "pos-2"}
    rig.confirmed = [
        _confirmed_sell(),
        ConfirmedSell("o-2", "prop-2", "pos-2", SIGNATURE, {"exit_reason": "stop"}, CURVE_STORED),
    ]


def test_a_close_the_database_refuses_blocks_that_position_and_the_sweep_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before the review fix the exception escaped ``repair_confirmed_sells`` →
    ``reconcile_once`` → ``forever`` re-raised → the TaskGroup took every loop
    down, every 30 s, leaving the other open positions without exits."""
    rig = _rig(monkeypatch)
    _two_orphans(rig)
    _poison_close(monkeypatch, "pos-1")
    asyncio.run(exit_settle.repair_confirmed_sells(rig.ctx))  # does not raise
    assert [c["position_id"] for c in rig.closed] == ["pos-2"], "the other orphan is repaired"
    assert rig.blocked == [CLOSE_FAILED], "the refused one is blocked by name, still open"
    assert rig.ctx.state.settle_errors == 1
    asyncio.run(exit_settle.repair_confirmed_sells(rig.ctx))  # 30 s later: tried again
    assert rig.blocked == [CLOSE_FAILED], "the same block is not re-marked every tick"
    assert rig.ctx.state.blocked_exits["pos-1"] == CLOSE_FAILED
    assert rig.ctx.state.settle_errors == 2


def test_any_failure_on_one_position_never_stops_the_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    _two_orphans(rig)
    real_open = exit_settle.open_position

    async def open_position(session: Any, position_id: str) -> Any:
        if position_id == "pos-1":
            raise ConnectionError("db")
        return await real_open(session, position_id)

    monkeypatch.setattr(exit_settle, "open_position", open_position)
    asyncio.run(exit_settle.repair_confirmed_sells(rig.ctx))
    assert [c["position_id"] for c in rig.closed] == ["pos-2"]
    assert rig.ctx.state.settle_errors == 1


def test_a_refused_close_on_the_exit_path_is_a_named_block_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell()]
    _poison_close(monkeypatch, "pos-1")
    handled = asyncio.run(
        exit_settle.settle_latest(rig.ctx, _position(), _order("confirmed"), "sell_now", NOW)
    )
    assert handled is True, "never a new sell over a confirmed one"
    assert rig.closed == [] and rig.blocked == [CLOSE_FAILED]
    assert rig.ctx.state.settle_errors == 1


def test_a_refused_close_on_an_empty_wallet_is_one_named_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.confirmed = [_confirmed_sell()]
    _poison_close(monkeypatch, "pos-1")
    asyncio.run(exit_settle.no_tokens_on_chain(rig.ctx, _position(), "time_stop", NOW))
    assert rig.blocked == [CLOSE_FAILED], "the real cause, not no_tokens_on_chain on top"
    assert rig.rpc.calls == []


# -------------------------------------------- 3. the ORDER's venue picks the decoder
def test_a_curve_order_is_read_with_the_curve_decoder_even_on_a_migrated_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before T4.90b the migrated path reconciled every sell with
    ``decode_pumpswap_fills``, whose payer-delta fallback accepts ANY landed
    transaction: this curve sale would be booked as ``venue: pumpswap``."""
    rig = _rig(monkeypatch)
    _signed(rig.journal, KEY, SIGNATURE)
    asyncio.run(
        exit_settle.reconcile_order(
            rig.ctx, _position(migrated=True), _order("submitted_unconfirmed")
        )
    )
    (row,) = rig.closed
    payload = row["exit_payload"]
    assert "venue" not in payload and payload["is_buy"] is False, "a curve TradeEvent"
    assert payload["token_amount"] > 0 and row["sol_received_lamports"] == CURVE_NET


def test_a_pumpswap_order_is_read_with_the_pumpswap_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, tx=PUMPSWAP_TX)
    _signed(rig.journal, KEY, PUMPSWAP_SIG)
    order = _order("submitted_unconfirmed", intent={"venue": "pumpswap"})
    asyncio.run(exit_settle.reconcile_order(rig.ctx, _position(migrated=True), order))
    (row,) = rig.closed
    assert row["exit_payload"]["venue"] == "pumpswap" and row["sol_received_lamports"] == 18_953


def test_an_expired_curve_sell_is_asked_with_the_curve_decoder_after_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch)
    rig.rpc.statuses[SIGNATURE] = [None, CONFIRMED]
    rig.journal.begin_signing(KEY)
    rig.journal.record_signature(KEY, SIGNATURE, last_valid_block_height=LAST_VALID)
    rig.journal.record_state(KEY, SubmitState.FAILED, "blockhash_expired_never_landed", None)
    rig.journal.release_signing(KEY)
    rig.expired = [_order("failed")]
    asyncio.run(exit_settle.no_tokens_on_chain(rig.ctx, _position(migrated=True), "migrated", NOW))
    (row,) = rig.closed
    assert "venue" not in row["exit_payload"] and row["exit_payload"]["is_buy"] is False
