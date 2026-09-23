"""T4.90 — zero tokens in the wallet for a position the ledger holds open.

Before T4.90 ``MemeSubmitter.reconcile`` could write a sell that landed in its
last valid block as ``failed:blockhash_expired_never_landed``; T4.88's retry
then built a new sell, found no tokens and parked the position as
``blocked:reconciliation_mismatch:no_tokens_on_chain`` — open, outside the
day's loss, waiting for a human. Now that path first asks the chain about each
of our own "expired" sells (never re-sent, never re-signed): if one landed, the
position closes with the fill of that transaction; otherwise the named block
stands. The SQL filter and the full tick are proven on Postgres in
``test_exit_retry_integration.py``.

Pure (no Docker, no network): the chain is a scripted fake RPC (test fixture)
returning the real recorded mainnet sell ``t48b_rpc_tx_sell_raw.json``; the
database writes are recorded fakes.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hunter_meme_executor.exit_settle as exit_settle
import hunter_meme_executor.exits as exits
import hunter_meme_executor.pumpswap_exit as pumpswap_exit
from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_meme_executor.repo import OrderRow

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
SELL_TX: dict[str, Any] = json.loads(
    (FIXTURES / "t48b_rpc_tx_sell_raw.json").read_text(encoding="utf-8")
)["result"]
SIGNATURE = str(SELL_TX["transaction"]["signatures"][0])
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
KEY = "prop-1:exit:2"
ORDER_ID = "01994d00-6c1a-7000-8000-00000000a002"
LAST_VALID = 150
CONFIRMED: dict[str, Any] = {"confirmationStatus": "confirmed", "err": None}
BLOCK = "reconciliation_mismatch:no_tokens_on_chain"


OLD_KEY, OLD_ID, OLD_SIG = "prop-1:exit:1", "01994d00-6c1a-7000-8000-00000000a001", "0ldS1g"
EXPIRED = "blockhash_expired_never_landed"


@dataclass
class ScriptedRpc:
    """Fixture: per signature, successive ``getSignatureStatuses`` answers (the
    last repeats); a signature not scripted is never seen by the chain."""

    statuses: dict[str, list[dict[str, Any] | None]]
    height: int = LAST_VALID + 1
    calls: list[str] = field(default_factory=lambda: list[str]())

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        (signature,) = signatures
        script = self.statuses.get(signature, [None])
        index = min(self.calls.count(f"status:{signature}"), len(script) - 1)
        self.calls.append(f"status:{signature}")
        return [script[index]]

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        self.calls.append("height")
        return self.height

    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None:
        self.calls.append(f"transaction:{signature}")
        return SELL_TX


class _Sessions:
    """Stands in for ``role_session``: no database."""

    def __call__(self, *_: Any, **__: Any) -> _Sessions:
        return self

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: Any) -> None:
        return None


def _journal() -> InMemoryOrderJournal:
    """Two sells the pre-T4.90 reconcile wrote ``failed`` on a stale read."""
    journal = InMemoryOrderJournal()
    for key, signature in ((KEY, SIGNATURE), (OLD_KEY, OLD_SIG)):
        journal.begin_signing(key)
        journal.record_signature(key, signature, last_valid_block_height=LAST_VALID)
        journal.record_state(key, SubmitState.FAILED, EXPIRED, None)
        journal.release_signing(key)
    return journal


NEWEST = OrderRow(ORDER_ID, "prop-1", "sell", KEY, 2, "failed", EXPIRED, {}, {})
OLDEST = OrderRow(OLD_ID, "prop-1", "sell", OLD_KEY, 1, "failed", EXPIRED, {}, {})


def _position() -> Any:
    return SimpleNamespace(
        id="pos-1",
        proposal_id="prop-1",
        mint="Mint111",
        tokens=1_000,
        sol_spent_lamports=1_000_000_000,
        initial_risk_sol=None,
        params={},
        exit_intent={"reason": "time_stop", "attempt": 2},
    )


@dataclass
class Rig:
    rpc: ScriptedRpc
    journal: InMemoryOrderJournal
    ctx: Any
    closed: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    blocked: list[str] = field(default_factory=lambda: list[str]())


async def _no_confirmed_sell(_session: Any, _proposal_id: str) -> list[Any]:
    return []


def _rig(
    monkeypatch: pytest.MonkeyPatch,
    statuses: dict[str, list[dict[str, Any] | None]],
    expired: list[OrderRow],
) -> Rig:
    rpc = ScriptedRpc(statuses)
    journal = _journal()
    state = SimpleNamespace(exits_confirmed=0, blocked_exits={"pos-1": BLOCK}, ata_closed=0)
    ctx = SimpleNamespace(
        chain=SimpleNamespace(rpc=rpc),
        journal=journal,
        config=SimpleNamespace(cluster="mainnet"),
        state=state,
        session_factory=None,
    )
    rig = Rig(rpc, journal, ctx)

    async def expired_sell_orders(_session: Any, proposal_id: str) -> list[OrderRow]:
        assert proposal_id == "prop-1"
        return expired

    async def close_position(_session: Any, position_id: str, **kwargs: Any) -> bool:
        rig.closed.append({"position_id": position_id, **kwargs})
        return True

    async def mark_blocked(_ctx: Any, _position: Any, _reason: str, block: str, _now: Any) -> None:
        rig.blocked.append(block)

    monkeypatch.setattr(exit_settle, "role_session", _Sessions())
    monkeypatch.setattr(exit_settle, "expired_sell_orders", expired_sell_orders)
    monkeypatch.setattr(exit_settle, "confirmed_sells", _no_confirmed_sell)  # T4.90b
    monkeypatch.setattr(exit_settle, "close_position", close_position)
    monkeypatch.setattr(exit_settle, "mark_blocked", mark_blocked)
    return rig


def _run(rig: Rig) -> None:
    asyncio.run(exit_settle.no_tokens_on_chain(rig.ctx, _position(), "time_stop", NOW))


def test_our_expired_sell_that_landed_closes_the_position_with_its_own_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, {SIGNATURE: [None, CONFIRMED]}, [NEWEST])
    _run(rig)
    assert rig.blocked == [], "a sell that landed is a closed position, not a mismatch"
    (closed,) = rig.closed
    assert closed["position_id"] == "pos-1" and closed["exit_order_id"] == ORDER_ID
    assert closed["sol_received_lamports"] == 1_207_696_649, "the recorded sell's real delta"
    assert closed["exit_at"] == datetime(2026, 9, 12, 17, 52, 42, tzinfo=UTC)
    assert closed["exit_payload"]["reason"] == "time_stop"
    row = rig.journal.get(KEY)
    assert row is not None and row.state is SubmitState.CONFIRMED
    assert rig.ctx.state.exits_confirmed == 1 and "pos-1" not in rig.ctx.state.blocked_exits
    s = f"status:{SIGNATURE}"
    assert rig.rpc.calls == [s, "height", s, f"transaction:{SIGNATURE}"]


def test_our_expired_sell_that_truly_never_landed_keeps_the_named_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, {SIGNATURE: [None, None]}, [NEWEST])
    _run(rig)
    assert rig.closed == [] and rig.blocked == [BLOCK]
    s = f"status:{SIGNATURE}"
    assert rig.rpc.calls == [s, "height", s], "absent only after a second look"
    row = rig.journal.get(KEY)
    assert row is not None and row.state is SubmitState.FAILED


def test_an_older_expired_sell_that_landed_is_found_behind_a_newer_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra (T4.90 review): a retry built on a stale balance can fail on top of
    the sell that landed — the newest row is not the only suspect."""
    rig = _rig(monkeypatch, {SIGNATURE: [None, None], OLD_SIG: [CONFIRMED]}, [NEWEST, OLDEST])
    _run(rig)
    assert rig.blocked == []
    (closed,) = rig.closed
    assert closed["exit_order_id"] == OLD_ID
    old, new = rig.journal.get(OLD_KEY), rig.journal.get(KEY)
    assert old is not None and old.state is SubmitState.CONFIRMED
    assert new is not None and new.state is SubmitState.FAILED


def test_without_an_expired_sell_it_is_the_named_block_and_the_chain_is_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused, errored on chain or never written: nothing moved the tokens."""
    rig = _rig(monkeypatch, {SIGNATURE: [CONFIRMED]}, [])
    _run(rig)
    assert rig.closed == [] and rig.blocked == [BLOCK] and rig.rpc.calls == []


def _record_helper(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[Any]:
    seen: list[Any] = []

    async def helper(*args: Any, **kwargs: Any) -> None:
        seen.append((args, kwargs))

    async def fee(*_: Any) -> Any:
        return SimpleNamespace(micro_lamports=1)

    monkeypatch.setattr(module, "no_tokens_on_chain", helper)
    monkeypatch.setattr(module, "priority_fee_for", fee)
    return seen


def _empty_wallet(*_: object) -> Any:
    return SimpleNamespace(amount=0)


def _account(_mint: str) -> Any:
    return SimpleNamespace(owner="TokenProgram")


def _fee_accounts(_mint: str) -> tuple[str, str]:
    return ("a", "b")


def _empty_wallet_ctx() -> Any:
    chain = SimpleNamespace(
        token_account=_empty_wallet,
        global_account=lambda: object(),
        pumpswap_global_config=lambda: object(),
        blockhash=lambda: ("hash", LAST_VALID),
        rpc=SimpleNamespace(get_account=_account),
    )
    return SimpleNamespace(
        signer=SimpleNamespace(pubkey="Wallet111"), config=SimpleNamespace(), chain=chain
    )


def test_the_curve_sell_routes_an_empty_wallet_to_the_chain_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_helper(monkeypatch, exits)
    monkeypatch.setattr(exits, "curve_fee_accounts", _fee_accounts)
    read: Any = SimpleNamespace(token_program="TokenProgram")
    asyncio.run(exits._sell(_empty_wallet_ctx(), _position(), read, "time_stop", 3, NOW))
    ((args, kwargs),) = seen
    assert args[2:] == ("time_stop", NOW) and kwargs == {}


def test_the_pumpswap_sell_routes_an_empty_wallet_to_the_chain_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.90b: no decoder is passed any more — each expired sell is read with
    the decoder of the venue it was SENT to (``exit_settle.reconcile_order``),
    so a curve sell from before the migration is not booked as a PumpSwap one."""
    seen = _record_helper(monkeypatch, pumpswap_exit)
    pool: Any = SimpleNamespace(address="Pool111")
    asyncio.run(pumpswap_exit._sell(_empty_wallet_ctx(), _position(), pool, "time_stop", 3, NOW))
    ((args, kwargs),) = seen
    assert args[2:] == ("time_stop", NOW) and kwargs == {}
