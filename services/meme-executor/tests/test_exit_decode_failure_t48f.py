"""T4.8f (Astra, 05/10): an exit whose transaction LANDS but whose fill cannot be read must be
closed **once** — and only once — when the decoder comes back, never sold twice and never
closed twice.

Path under test, both venues: the journal holds what the real ``MemeSubmitter`` leaves after a
landed send whose fill does not decode (``submitted_unconfirmed`` + the reason the real decoder
raises/returns — ``packages/core`` proves the submit half) -> a "restarted" executor (a brand new
context over the same journal) reconciles by signature, never re-signs, never re-sends -> with
the decoder healthy the position closes exactly once -> ``repair_confirmed_sells``,
``on_stream_event`` and a second reconcile close nothing more.

**Nothing is signed or sent here**: no key exists in this module, the RPC double raises on
``send_transaction``, and the journal is seeded by hand (a deliberate choice: the first version
signed a dummy message with a seeded test key, which the task's "never sign" rule forbids even
against a fake). PumpSwap's decode failure is the closest analogue the venue still has — since
T4.8e an unreadable *event* falls back to the payer's delta, so what stays unreadable is a landed
transaction the RPC returned without balances (``trade_event_missing``).

Pure (no Docker): the database is recorded fakes whose ``close_position`` answers ``True`` once
per position, like the real guarded UPDATE. The Postgres half (real rows, ``exits_once``) is
``test_exit_decode_failure_integration_t48f.py`` — **not run: Docker was not reachable**; it covers
the curve venue only (a PumpSwap Postgres variant is still to write).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hunter_meme_executor.exit_settle as exit_settle
import hunter_meme_executor.pumpswap_settle as pumpswap_settle
from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.pumpswap_build import decode_pumpswap_fills
from hunter_meme_executor.repo import OrderRow
from hunter_meme_executor.repo_positions import ConfirmedSell

from .test_fills_t48e import _append_to_event_cpi

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
NOW = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
KEY = "prop-1:exit:1"
SIGNATURE = "5igNaTuRe1111111111111111111111111111111111111111111111111111111"
LAST_VALID = 150
ORDER_ID = "01994d00-6c1a-7000-8000-00000000a001"
POSITION_ID = "pos-1"
CURVE_GOOD: dict[str, Any] = json.loads(
    (FIXTURES / "t48b_rpc_tx_sell_raw.json").read_text(encoding="utf-8")
)["result"]
PUMPSWAP_GOOD: dict[str, Any] = {
    "slot": 453_700_000,
    "blockTime": int(NOW.timestamp()),
    "meta": {
        "err": None,
        "fee": 5000,
        "preBalances": [100_000_000, 0],
        "postBalances": [100_018_953, 0],
        "innerInstructions": [],
    },
    "transaction": {"signatures": ["placeholder"], "message": {"accountKeys": []}},
}


def _curve_bad() -> dict[str, Any]:
    """The real sell, its event grown by 7 bytes: a layout nobody has seen."""
    tx = copy.deepcopy(CURVE_GOOD)
    _append_to_event_cpi(tx, b"\x00" * 7, program=None)
    return tx


def _pumpswap_bad() -> dict[str, Any]:
    """A landed PumpSwap sell the RPC returned without balances and with no readable event."""
    tx = copy.deepcopy(PUMPSWAP_GOOD)
    tx["meta"]["preBalances"], tx["meta"]["postBalances"] = [], []
    return tx


@dataclass
class ChainRpc:
    """Fixture RPC: always confirmed; the transaction it returns is whatever ``tx`` says right
    now (swapped when the 'decoder comes back'). It can read; it cannot send."""

    tx: dict[str, Any]

    def simulate_transaction(self, transaction: bytes, **_: Any) -> Any:
        raise AssertionError("nothing is simulated in this test")

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        raise AssertionError("nothing is sent in this test")

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        return [{"confirmationStatus": "confirmed", "err": None} for _ in signatures]

    def get_transaction(self, signature: str, **_: Any) -> dict[str, Any] | None:
        tx = copy.deepcopy(self.tx)
        tx["transaction"]["signatures"] = [signature]
        return tx

    def get_block_height(self, **_: Any) -> int:
        return 100


class _Sessions:
    def __call__(self, *_: Any, **__: Any) -> _Sessions:
        return self

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: Any) -> None:
        return None


@dataclass
class Db:
    """The recorded database: one position, one sell order, closed at most once."""

    journal: InMemoryOrderJournal
    venue: str
    closed: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    blocked: list[str] = field(default_factory=lambda: list[str]())

    @property
    def is_closed(self) -> bool:
        return bool(self.closed)

    def confirmed_sell(self) -> ConfirmedSell | None:
        row = self.journal.get(KEY)
        if row is None or row.state is not SubmitState.CONFIRMED or self.is_closed:
            return None
        fill = row.fill.as_json() if hasattr(row.fill, "as_json") else row.fill
        intent: dict[str, Any] = {"venue": "pumpswap"} if self.venue == "pumpswap" else {}
        return ConfirmedSell(ORDER_ID, "prop-1", POSITION_ID, row.latest_signature, intent, fill)


def _position() -> Any:
    return SimpleNamespace(
        id=POSITION_ID,
        proposal_id="prop-1",
        mint="Mint111",
        tokens=1_000,
        sol_spent_lamports=1_000_000_000,
        initial_risk_sol=None,
        params={},
        exit_intent={"reason": "creator_dump", "attempt": 1},
    )


def _install(monkeypatch: pytest.MonkeyPatch, db: Db) -> None:
    async def close_position(_session: Any, position_id: str, **kwargs: Any) -> bool:
        if db.is_closed:
            return False  # the guarded UPDATE of the real ``close_position``
        db.closed.append({"position_id": position_id, **kwargs})
        return True

    async def confirmed_sells(_session: Any, _proposal_id: str) -> list[ConfirmedSell]:
        sell = db.confirmed_sell()
        return [] if sell is None else [sell]

    async def positions_with_confirmed_sell(_session: Any) -> list[str]:
        return [] if db.confirmed_sell() is None else [POSITION_ID]

    async def open_position(_session: Any, position_id: str) -> Any:
        return None if db.is_closed else _position()

    async def mark_blocked(_ctx: Any, _position: Any, _reason: str, block: str, _now: Any) -> None:
        db.blocked.append(block)

    for module in (exit_settle, pumpswap_settle):
        monkeypatch.setattr(module, "role_session", _Sessions())
        monkeypatch.setattr(module, "close_position", close_position)
    monkeypatch.setattr(exit_settle, "confirmed_sells", confirmed_sells)
    monkeypatch.setattr(exit_settle, "positions_with_confirmed_sell", positions_with_confirmed_sell)
    monkeypatch.setattr(exit_settle, "open_position", open_position)
    monkeypatch.setattr(exit_settle, "mark_blocked", mark_blocked)


def _executor(rpc: ChainRpc, journal: InMemoryOrderJournal) -> Any:
    """A brand new executor context over the SAME journal (the database)."""
    state = SimpleNamespace(
        exits_confirmed=0, blocked_exits={}, ata_closed=0, exit_locks={}, settle_errors=0
    )
    return SimpleNamespace(
        chain=SimpleNamespace(rpc=rpc),
        journal=journal,
        config=SimpleNamespace(cluster="devnet"),
        state=state,
        session_factory=None,
        launch=SimpleNamespace(sells_total=0),
    )


def _seed_landed_send_with_unreadable_fill(
    journal: InMemoryOrderJournal, decoder: Callable[..., Any], tx: dict[str, Any]
) -> str:
    """What ``MemeSubmitter.submit`` leaves in the journal after a send that landed and whose fill
    the decoder cannot read: the signature recorded **before** the send, then
    ``submitted_unconfirmed`` with the reason the REAL decoder produces on ``tx``. Returns it."""
    try:
        reason = "trade_event_missing" if not list(decoder(tx)) else "decoded"
    except Exception as exc:
        reason = f"fill_decode_failed:{type(exc).__name__}"
    assert reason != "decoded", "the scenario needs a transaction the decoder cannot read"
    journal.begin_signing(KEY)
    journal.record_signature(KEY, SIGNATURE, last_valid_block_height=LAST_VALID)
    journal.record_state(KEY, SubmitState.SUBMITTED_UNCONFIRMED, reason, None)
    journal.release_signing(KEY)
    return reason


def _order_row(venue: str, reason: str) -> Any:
    intent: dict[str, Any] = {"venue": "pumpswap"} if venue == "pumpswap" else {}
    return OrderRow(ORDER_ID, "prop-1", "sell", KEY, 1, "submitted_unconfirmed", reason, intent, {})


def _reconciler(rpc: ChainRpc, journal: InMemoryOrderJournal, decoder: Any) -> MemeSubmitter:
    return MemeSubmitter(
        rpc=rpc,
        signer=None,
        journal=journal,
        verify=lambda _m: None,
        decode_fill=decoder,
        policy=SubmitPolicy(allow_send=False, cluster="devnet"),
        now=lambda: NOW,
    )


SCENARIOS = {
    "curve": (decode_fills, _curve_bad, lambda: CURVE_GOOD, "fill_decode_failed:ValueError"),
    "pumpswap": (
        decode_pumpswap_fills,
        _pumpswap_bad,
        lambda: PUMPSWAP_GOOD,
        "trade_event_missing",
    ),
}


@pytest.mark.parametrize("venue", ["curve", "pumpswap"])
def test_a_landed_exit_with_an_unreadable_fill_closes_once_and_only_once(
    monkeypatch: pytest.MonkeyPatch, venue: str
) -> None:
    decoder, bad, good, reason = SCENARIOS[venue]
    journal = InMemoryOrderJournal()
    db = Db(journal, venue)
    _install(monkeypatch, db)
    rpc = ChainRpc(bad())

    # 1. the send landed; its fill cannot be read (the decoder says why)
    assert _seed_landed_send_with_unreadable_fill(journal, decoder, rpc.tx) == reason
    row = journal.get(KEY)
    assert row is not None and row.state is SubmitState.SUBMITTED_UNCONFIRMED

    # 2. restart #1, the decoder still incompatible: pending, never re-signed, never re-sent
    restarted = _executor(rpc, journal)
    for _ in range(2):  # the 30 s reconcile ticks
        done = asyncio.run(
            exit_settle.settle_latest(
                restarted, _position(), _order_row(venue, reason), "creator_dump", NOW
            )
        )
        assert done is True, "a pending sell stops any new sell from being built"
    row = journal.get(KEY)
    assert row is not None and row.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert db.closed == [] and restarted.state.exits_confirmed == 0

    # 3. restart #2, the decoder back: the position closes exactly once
    rpc.tx = good()
    healthy = _executor(rpc, journal)
    assert asyncio.run(
        exit_settle.settle_latest(
            healthy, _position(), _order_row(venue, reason), "creator_dump", NOW
        )
    )
    assert len(db.closed) == 1 and healthy.state.exits_confirmed == 1
    assert db.closed[0]["exit_order_id"] == ORDER_ID
    row = journal.get(KEY)
    assert row is not None and row.state is SubmitState.CONFIRMED
    assert row.latest_signature == SIGNATURE

    # 4. nothing else closes it again: the orphan repair, the stream replay, a second reconcile
    asyncio.run(exit_settle.repair_confirmed_sells(healthy))
    replay = _reconciler(rpc, journal, decoder).on_stream_event(
        SIGNATURE, rpc.get_transaction(SIGNATURE) or {}
    )
    assert replay is not None and replay.replayed
    again = asyncio.run(
        exit_settle.reconcile_order(healthy, _position(), _order_row(venue, reason))
    )
    assert again is False, "the guarded close answers False the second time"
    assert len(db.closed) == 1 and healthy.state.exits_confirmed == 1 and db.blocked == []


@pytest.mark.parametrize("venue", ["curve", "pumpswap"])
def test_a_crash_between_the_confirmation_and_the_close_is_repaired_once(
    monkeypatch: pytest.MonkeyPatch, venue: str
) -> None:
    """The row says ``confirmed`` (the decoder came back and the fill was stored) but the
    process died before ``close_position``: the orphan repair closes it — once."""
    decoder, bad, good, _reason = SCENARIOS[venue]
    journal = InMemoryOrderJournal()
    db = Db(journal, venue)
    _install(monkeypatch, db)
    rpc = ChainRpc(bad())
    _seed_landed_send_with_unreadable_fill(journal, decoder, rpc.tx)
    rpc.tx = good()
    settled = _reconciler(rpc, journal, decoder).reconcile(KEY)  # confirmed, then the process dies
    assert settled is not None and settled.state is SubmitState.CONFIRMED and db.closed == []
    fresh = _executor(rpc, journal)
    asyncio.run(exit_settle.repair_confirmed_sells(fresh))
    asyncio.run(exit_settle.repair_confirmed_sells(fresh))
    assert len(db.closed) == 1 and fresh.state.exits_confirmed == 1
