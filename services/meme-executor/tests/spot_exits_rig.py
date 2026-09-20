"""T4.74-5 — the rig of ``test_spot_exits.py`` / ``test_spot_reconcile.py`` /
``test_spot_heartbeat.py``: the sell rig of the money path (a real
``spot_leg`` over the synthetic sell transaction), the exits' own config,
kill switch and stats on the context, and a recording store behind every
repository function the exits, the settle and the reconcile call. No
network, no key, no Postgres."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import spot_exits, spot_reconcile, spot_settle
from hunter_meme_executor.chain import TokenAccountRead
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_exit_repo import SellAttempts, SpotOrderRow
from hunter_meme_executor.spot_repo import ClosedStats, spot_position_from_row
from hunter_meme_executor.spot_send_rules import ATA_RENT_LAMPORTS
from hunter_meme_executor.spot_stats import SpotStats
from hunter_risk_meme import MemeKillSwitchInputs

from .spot_entries_rig import LIMITS, FakeInflow, FakeMode
from .spot_fakes import (
    Db,
    FakeChain,
    FakeConfig,
    FakeContext,
    FakeJupiter,
    FakeRpc,
    FakeSigner,
    accounts_after,
    simulation,
    tx_meta,
    wire_db,
)
from .spot_tx_fixtures import SIGNATURE, WIF, WSOL, as_swap, quote, sell_message
from .test_spot_repo import position_row

NOW = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
ON = SpotConfig(requested=True, live=True, signer_present=True)
TOKENS = 660_000_000
"""``position_row().tokens`` — the whole lot the sell hands in."""
SPENT = 50_000_000
"""``position_row().sol_spent_lamports``."""
WALLET_BEFORE = 450_000_000
FEES = 60_000
"""What the sell's signature pays beyond the swap (base fee + priority + WSOL rent round trip)."""
POSITION_ID = "p1"
ORDER_ID = "order-1"


@dataclass
class ExitsConfig(FakeConfig):
    limits: Any = LIMITS
    spot: SpotConfig = ON
    auto_close_on_emergency: bool = False


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE
    refreshes: int = 0

    @property
    def blocks_entries(self) -> bool:
        return self.effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)

    async def refresh(self) -> None:
        self.refreshes += 1

    def inputs(self) -> MemeKillSwitchInputs:
        return MemeKillSwitchInputs(system=self.effective)

    def describe(self) -> dict[str, str]:
        return {"kill_switch": self.effective.value}


@dataclass
class Store:
    """What the repository fakes answer and record."""

    positions: list[Any] = field(default_factory=lambda: list[Any]())
    sell_attempts: int = 0
    hard_failures: int = 0
    stuck: list[SpotOrderRow] = field(default_factory=lambda: list[SpotOrderRow]())
    confirmed_ok: bool = True
    failed_ok: bool = True
    closed: ClosedStats = field(
        default_factory=lambda: ClosedStats(0, Decimal(0), Decimal(0), None, 0, None)
    )
    unconfirmed: list[SpotOrderRow] = field(default_factory=lambda: list[SpotOrderRow]())
    orphan_buys: list[SpotOrderRow] = field(default_factory=lambda: list[SpotOrderRow]())
    orphan_sells: list[SpotOrderRow] = field(default_factory=lambda: list[SpotOrderRow]())
    abandoned: list[SpotOrderRow] = field(default_factory=lambda: list[SpotOrderRow]())
    queries: list[str] = field(default_factory=lambda: list[str]())
    marks: list[tuple[str, Decimal | None, str | None]] = field(
        default_factory=lambda: list[tuple[str, Decimal | None, str | None]]()
    )
    orders: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    pending_set: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    pending_cleared: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    closes: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    opened: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    confirmed: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    failed: list[tuple[str, str]] = field(default_factory=lambda: list[tuple[str, str]]())
    abandoned_failed: list[str] = field(default_factory=lambda: list[str]())
    duplicate_order_keys: set[str] = field(default_factory=lambda: set[str]())


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def wire_store(monkeypatch: pytest.MonkeyPatch, store: Store) -> None:
    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    async def open_positions(_s: Any) -> list[Any]:
        store.queries.append("open_spot_positions")
        return list(store.positions)

    async def set_mark(_s: Any, position_id: str, *, mark_sol: Any, reason: Any, now: Any) -> None:
        store.marks.append((position_id, mark_sol, reason))

    async def sell_attempts(_s: Any, position_id: str) -> SellAttempts:
        store.queries.append("sell_attempts")
        return SellAttempts(store.sell_attempts, store.hard_failures)

    async def stuck(_s: Any) -> list[SpotOrderRow]:
        return list(store.stuck)

    async def insert_order(_s: Any, **row: Any) -> str | None:
        if row["client_order_id"] in store.duplicate_order_keys:
            return None
        store.orders.append(row)
        return f"order-{len(store.orders)}"

    async def set_exit_pending(_s: Any, position_id: str, **kw: Any) -> bool:
        store.pending_set.append({"position_id": position_id, **kw})
        return True

    async def clear_exit_pending(_s: Any, position_id: str, **kw: Any) -> bool:
        store.pending_cleared.append({"position_id": position_id, **kw})
        return True

    async def close_position(_s: Any, position_id: str, **kw: Any) -> bool:
        store.closes.append({"position_id": position_id, **kw})
        return True

    async def closed_stats(_s: Any, *, since: datetime, min_trades: int = 20) -> ClosedStats:
        store.queries.append("closed_stats")
        return store.closed

    async def insert_position(_s: Any, **row: Any) -> str | None:
        store.opened.append(row)
        return f"pos-{len(store.opened)}"

    async def unconfirmed(_s: Any) -> list[SpotOrderRow]:
        store.queries.append("unconfirmed_spot_orders")
        return list(store.unconfirmed)

    async def orphan_buys(_s: Any) -> list[SpotOrderRow]:
        return list(store.orphan_buys)

    async def orphan_sells(_s: Any) -> list[SpotOrderRow]:
        return list(store.orphan_sells)

    async def abandoned(_s: Any, *, before: datetime) -> list[SpotOrderRow]:
        return [r for r in store.abandoned if r.submitted_at < before]

    async def fail_abandoned(_s: Any, order_id: str, *, reason: str, now: Any) -> bool:
        store.abandoned_failed.append(order_id)
        return True

    async def mark_confirmed(_s: Any, order_id: str, *, fill: dict[str, Any], now: Any) -> bool:
        store.confirmed.append({"order_id": order_id, **fill})
        return store.confirmed_ok

    async def mark_failed(_s: Any, order_id: str, *, reason: str, now: Any) -> bool:
        store.failed.append((order_id, reason))
        return store.failed_ok

    async def open_by_id(_s: Any, position_id: str) -> Any:
        for p in store.positions:
            if p.id == position_id:
                return p
        return None

    for module in (spot_exits, spot_settle, spot_reconcile):
        monkeypatch.setattr(module, "role_session", session)
    monkeypatch.setattr(spot_exits, "open_spot_positions", open_positions)
    monkeypatch.setattr(spot_exits, "set_mark", set_mark)
    monkeypatch.setattr(spot_exits, "sell_attempts", sell_attempts)
    monkeypatch.setattr(spot_exits, "insert_order", insert_order)
    monkeypatch.setattr(spot_exits, "set_exit_pending", set_exit_pending)
    monkeypatch.setattr(spot_exits, "clear_exit_pending", clear_exit_pending)
    monkeypatch.setattr(spot_settle, "close_position", close_position)
    monkeypatch.setattr(spot_settle, "closed_stats", closed_stats)
    monkeypatch.setattr(spot_settle, "insert_position", insert_position)
    monkeypatch.setattr(spot_reconcile, "unconfirmed_spot_orders", unconfirmed)
    monkeypatch.setattr(spot_reconcile, "confirmed_buys_without_position", orphan_buys)
    monkeypatch.setattr(spot_reconcile, "confirmed_sells_still_pending", orphan_sells)
    monkeypatch.setattr(spot_reconcile, "abandoned_orders", abandoned)
    monkeypatch.setattr(spot_reconcile, "pending_exits_on_terminal_orders", stuck)
    monkeypatch.setattr(spot_reconcile, "fail_abandoned", fail_abandoned)
    monkeypatch.setattr(spot_reconcile, "mark_confirmed", mark_confirmed)
    monkeypatch.setattr(spot_reconcile, "mark_failed", mark_failed)
    monkeypatch.setattr(spot_reconcile, "clear_exit_pending", clear_exit_pending)
    monkeypatch.setattr(spot_reconcile, "open_position_by_id", open_by_id)
    monkeypatch.setattr(spot_exits, "utcnow", lambda: NOW)
    monkeypatch.setattr(spot_reconcile, "utcnow", lambda: NOW)


class FailingJupiter(FakeJupiter):
    """A Jupiter whose quote raises — the mark and the leg both see the failure."""

    def quote(self, **kwargs: Any) -> Any:
        self.quote_calls += 1
        raise RuntimeError("jupiter_down")


@dataclass
class ExitsRig:
    ctx: Any
    store: Store
    db: Db
    log: list[str]

    @property
    def stats(self) -> SpotStats:
        return cast(SpotStats, self.ctx.spot)


def position(**overrides: Any) -> Any:
    return spot_position_from_row({**position_row(), **overrides})


def exits_rig(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sol_out: int = 49_000_000,
    wallet_after: int | None = None,
    kill: KillSwitchState = KillSwitchState.ACTIVE,
    auto_close: bool = False,
    jupiter: FakeJupiter | None = None,
) -> ExitsRig:
    """A WIF -> SOL sell of the whole lot: the mark quote **and** the leg's
    re-quote are the same ``sol_out``; the chain lands ``sol_out - FEES``."""
    log: list[str] = []
    after = WALLET_BEFORE + sol_out - FEES if wallet_after is None else wallet_after
    rpc = FakeRpc(log, simulation(accounts_after(after, 0)))
    rpc.transaction = tx_meta(
        wallet_pre=WALLET_BEFORE, wallet_post=after, token_pre=TOKENS, token_post=0
    )
    chain = FakeChain(rpc, WALLET_BEFORE, TokenAccountRead(True, TOKENS))
    if jupiter is None:
        jupiter = FakeJupiter(
            quote(input_mint=WIF, output_mint=WSOL, amount=TOKENS, out=sol_out),
            as_swap(sell_message(in_amount=TOKENS, out=sol_out)),
        )
    base = FakeContext(FakeConfig(), chain, FakeSigner(log), cast(Any, FakeKill(kill)), jupiter)
    ctx = cast(Any, base)
    ctx.config = ExitsConfig(auto_close_on_emergency=auto_close)
    ctx.mode = FakeMode()
    ctx.treasury_inflow = FakeInflow()
    ctx.spot = SpotStats()
    db = Db(log, expected_order_id=None)
    wire_db(monkeypatch, db)
    store = Store()
    wire_store(monkeypatch, store)
    return ExitsRig(ctx, store, db, log)


def order_row(**overrides: Any) -> SpotOrderRow:
    base: dict[str, Any] = {
        "id": ORDER_ID,
        "side": "buy",
        "status": "submitted_unconfirmed",
        "signal_id": "01996e2a-0000-7000-8000-000000000001",
        "position_id": None,
        "market_symbol": "UNIUSDT",
        "mint": WIF,
        "signature": SIGNATURE,
        "last_valid_block_height": 250_000_123,
        "submitted_at": NOW - timedelta(seconds=90),
        "intent": {
            "ticket_sol": "0.05",
            "strategy_version": "v14",
            "max_sol_cost_sol": "0.05",
        },
        "admission": {
            "spot1": {
                "geometry": {"stop_frac": "0.015", "target_frac": "0.0225", "horizon_s": 14400},
                "parity": {"sol_usd": "200", "bin_usd": "7.5", "jup_usd": "7.52"},
                "decimals": 8,
            }
        },
        "quote": {"outAmount": "133333333"},
        "fill": None,
    }
    base.update(overrides)
    return SpotOrderRow(**base)


# ----------------------------------------------------- reconcile test helpers
UNI_OUT = 133_333_333
TICKET = 50_000_000


def confirmed_status() -> dict[str, Any]:
    return {"confirmationStatus": "confirmed", "err": None}


def buy_landed(rig: ExitsRig, *, token_pre: int | None = None, token_post: int = UNI_OUT) -> None:
    """The chain says the buy landed: status confirmed, meta = the ticket + rent + fees out, tokens in."""
    before, after = 500_000_000, 500_000_000 - TICKET - ATA_RENT_LAMPORTS - 5_050
    rig.ctx.chain.rpc.statuses = [confirmed_status()]
    rig.ctx.chain.rpc.transaction = tx_meta(
        wallet_pre=before, wallet_post=after, token_pre=token_pre, token_post=token_post
    )


def sell_row(**overrides: Any) -> SpotOrderRow:
    base: dict[str, Any] = {
        "side": "sell",
        "position_id": POSITION_ID,
        "intent": {"reason": "target", "attempt": 2, "slippage_bps": 50},
    }
    return order_row(**{**base, **overrides})
