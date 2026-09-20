"""T4.74-4 — the rig of ``test_spot_entries.py``: the buy rig of the money path
(a real ``spot_leg`` over the synthetic transaction) with the entries' own
config, kill switch, mode, inflow and stats on the context, and a recording
store behind every repository function the loop calls."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import spot_entries, spot_entry_reads, spot_entry_writes
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_repo import ClosedStats, candidate_from_row
from hunter_meme_executor.spot_signals import FinalClose
from hunter_meme_executor.spot_stats import SpotStats
from hunter_risk_meme import MemeKillSwitchInputs, limits_from_env

from .spot_fakes import (
    TICKET,
    WIF,
    FakeConfig,
    Rig,
    as_swap,
    buy_message,
    buy_rig,
    quote,
)
from .test_spot_repo import candidate_row

NOW = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.05",
    "MEME_DAILY_LOSS_CAP_SOL": "0.1",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "3600",
}
LIMITS = limits_from_env(POLICY)
ON = SpotConfig(requested=True, live=True, signer_present=True)
# UNIUSDT at 7,5 USD, SOL at 200 USD: 0,05 SOL = 10 USD buys 1,3333 UNI (decimals 8).
UNI_OUT = 133_333_333
EXTRA = 2_039_280 + 5_050
"""What the buy costs beyond the ticket: the UNI ATA's rent, the base fee and 50 of priority."""
WSOL = "So11111111111111111111111111111111111111112"


@dataclass
class EntriesConfig(FakeConfig):
    limits: Any = LIMITS
    spot: SpotConfig = ON


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE
    flip_on_refresh: KillSwitchState | None = None
    flip_after: int = 1
    refreshes: int = 0
    latched: list[str] = field(default_factory=lambda: list[str]())

    @property
    def blocks_entries(self) -> bool:
        return self.effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)

    async def refresh(self) -> None:
        self.refreshes += 1
        if self.flip_on_refresh is not None and self.refreshes >= self.flip_after:
            self.effective = self.flip_on_refresh

    def inputs(self) -> MemeKillSwitchInputs:
        return MemeKillSwitchInputs(system=self.effective)

    def describe(self) -> dict[str, str]:
        return {"kill_switch": self.effective.value}

    async def latch(self, reason: str) -> bool:
        self.latched.append(reason)
        return True


@dataclass
class FakeInflow:
    inflow_sol: Decimal | None = Decimal(0)

    def describe(self) -> dict[str, str]:
        return {"treasury_inflow_today_sol": str(self.inflow_sol)}


@dataclass
class FakeMode:
    live: bool = True


@dataclass
class Store:
    closed: ClosedStats = field(
        default_factory=lambda: ClosedStats(0, Decimal(0), Decimal(0), None, 0, None)
    )
    candidates: list[Any] = field(default_factory=lambda: list[Any]())
    closes: dict[str, FinalClose | None] = field(
        default_factory=lambda: {
            "UNIUSDT": FinalClose(Decimal("7.5"), NOW - timedelta(seconds=20)),
            "SOLUSDT": FinalClose(Decimal("200"), NOW - timedelta(seconds=20)),
        }
    )
    queries: list[str] = field(default_factory=lambda: list[str]())
    orders: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    positions: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    refused_admitted: list[str] = field(default_factory=lambda: list[str]())
    decimals_written: list[int] = field(default_factory=lambda: list[int]())
    anchor: DayAnchor | None = field(
        default_factory=lambda: DayAnchor(DAY_START, Decimal("0.5"), Decimal("0.5"), NOW)
    )


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _wire(monkeypatch: pytest.MonkeyPatch, store: Store) -> None:
    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    async def closed_stats(_s: Any, *, since: datetime) -> ClosedStats:
        store.queries.append("closed_stats")
        return store.closed

    async def candidates(_s: Any, **kw: Any) -> list[Any]:
        store.queries.append("candidates")
        return list(store.candidates)

    async def insert_order(_s: Any, **row: Any) -> str | None:
        store.orders.append(row)
        return f"order-{len(store.orders)}"

    async def insert_position(_s: Any, **row: Any) -> str | None:
        store.positions.append(row)
        return "pos-1"

    async def mark_refused(_s: Any, order_id: str, *, reason: str, now: Any) -> bool:
        store.refused_admitted.append(reason)
        return True

    async def close(_s: Any, *, symbol: str, **kw: Any) -> FinalClose | None:
        return store.closes.get(symbol)

    async def nothing(_s: Any, *_a: Any, **_k: Any) -> list[Any]:
        return []

    async def set_decimals(_s: Any, symbol: str, decimals: int, *, now: Any) -> bool:
        store.decimals_written.append(decimals)
        return True

    async def ensure_anchor(ctx: Any, now: Any, equity: Decimal) -> DayAnchor | None:
        return store.anchor

    for module in (spot_entries, spot_entry_reads, spot_entry_writes):
        monkeypatch.setattr(module, "role_session", session)
    monkeypatch.setattr(spot_entries, "utcnow", lambda: NOW)  # the signal's age is measured here
    monkeypatch.setattr(spot_entries, "closed_stats", closed_stats)
    monkeypatch.setattr(spot_entries, "candidate_signals", candidates)
    monkeypatch.setattr(spot_entries, "insert_order", insert_order)
    monkeypatch.setattr(spot_entries, "mark_refused", mark_refused)
    monkeypatch.setattr(spot_entries, "ensure_anchor", ensure_anchor)
    monkeypatch.setattr(spot_entry_writes, "insert_order", insert_order)
    monkeypatch.setattr(spot_entry_writes, "insert_position", insert_position)
    monkeypatch.setattr(spot_entry_reads, "latest_final_close", close)
    monkeypatch.setattr(spot_entry_reads, "brake_positions", nothing)
    monkeypatch.setattr(spot_entry_reads, "pending_attempts", nothing)
    monkeypatch.setattr(spot_entry_reads, "pending_spot_markets", nothing)
    monkeypatch.setattr(spot_entry_reads, "set_market_decimals", set_decimals)


def entries_rig(monkeypatch: pytest.MonkeyPatch, store: Store, *, spot: SpotConfig = ON) -> Rig:
    """The buy rig of the money path (real ``spot_leg`` over the synthetic tx), with
    the entries' own config, mode, inflow and stats on the context."""
    rig = buy_rig(monkeypatch, token_after=UNI_OUT, wallet_after=500_000_000 - TICKET - EXTRA)
    rig.ctx.chain.rpc.simulation = replace(
        rig.ctx.chain.rpc.simulation,
        accounts=(
            {"lamports": 500_000_000 - TICKET - EXTRA},
            {"data": {"parsed": {"info": {"tokenAmount": {"amount": str(UNI_OUT)}}}}},
        ),
    )
    rig.ctx.treasury_client.quote_reply = replace(
        quote(input_mint=WSOL, output_mint=WIF, amount=TICKET, out=UNI_OUT),
        price_impact_pct=Decimal(0),
    )
    rig.ctx.treasury_client.swap_reply = as_swap(buy_message(out=UNI_OUT))
    ctx = cast(Any, rig.ctx)
    ctx.config = EntriesConfig(spot=spot)
    ctx.kill = FakeKill()
    ctx.mode = FakeMode()
    ctx.treasury_inflow = FakeInflow()
    ctx.spot = SpotStats()
    rig.db.expected_order_id = "order-1"
    _wire(monkeypatch, store)
    return rig


def candidate(**overrides: Any) -> Any:
    row = {**candidate_row(), "mint": WIF, "emitted_at": NOW - timedelta(seconds=30)}
    row.update(overrides)
    return candidate_from_row(row)
