"""Shared builders of the copy-lane tests (H-037): a spec with the frozen EXP-M28 parameter names,
leader events and gaps. Labeled test fixtures — nothing here ships."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_exchanges.pumpfun.leader_events import (
    Kind,
    LeaderConfirmation,
    LeaderEvent,
    LeaderGap,
)
from hunter_meme_worker.copy_spec import CopyLeader, CopySpec

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
LEADER_A = "LeaderAWa11et111111111111111111111111111111"
LEADER_B = "LeaderBWa11et111111111111111111111111111111"
MINT_1 = "MintOne1111111111111111111111111111111111"
MINT_2 = "MintTwo1111111111111111111111111111111111"

PARAMS: dict[str, Any] = {
    "clock": "copy",
    "leaders": [
        {"wallet": LEADER_A, "stratum": "regra"},
        {"wallet": LEADER_B, "stratum": "regra"},
    ],
    "size_sol": "0.05",
    "min_trigger_sol": "0.1",
    "exit_leader_drop_fraction": "0.5",
    "stop_fraction": "0.4",
    "time_cap_s": 600,
    "exec_latency_s": "0",
    "fill_window_s": 2,
    "exit_window_s": 2,
    "max_attempts_per_leader_day": 20,
    "max_open_per_stratum": 100,
    "fee_pct": "1.25",
    "priority_fee_sol": "0.00005",
    "venues": ["curve"],
    "act_on_unconfirmed": True,
    "confirm_timeout_s": 30,
    "mark_every_s": 1,
}


def make_spec(**overrides: Any) -> CopySpec:
    status = overrides.pop("status", "active")
    params = {**PARAMS, **overrides}
    return CopySpec.from_params(
        id="rs-copy", name="copy_v0", version="1", params=params, status=status
    )


def leaders() -> tuple[CopyLeader, ...]:
    return make_spec().leaders


_counter = {"n": 0}


def buy(
    wallet: str = LEADER_A,
    mint: str = MINT_1,
    *,
    at: datetime = T0,
    position_after: int = 1_000_000,
    position_before: int = 0,
    spent_sol: str | None = "0.12",
    confirmed: bool = True,
    signature: str | None = None,
    block_time: datetime | None = None,
    slot: int | None = None,
    multi_mint: bool = False,
    kind: Kind = "unknown",
) -> LeaderEvent:
    _counter["n"] += 1
    return LeaderEvent(
        wallet=wallet,
        mint=mint,
        side="buy",
        token_delta_atoms=position_after - position_before,
        sol_delta_lamports=(
            None if spent_sol is None or multi_mint else -int(Decimal(spent_sol) * 1_000_000_000)
        ),
        position_after_atoms=position_after,
        signature=signature or f"sig-buy-{_counter['n']}",
        slot=slot if slot is not None else 1_000 + _counter["n"],
        block_time=block_time if block_time is not None else at - timedelta(seconds=1),
        first_seen_at=at,
        fields_complete_at=at + timedelta(milliseconds=2),
        source="nats",
        confirmed=confirmed,
        multi_mint=multi_mint,
        kind=kind,
    )


def sell(
    wallet: str = LEADER_A,
    mint: str = MINT_1,
    *,
    at: datetime = T0 + timedelta(seconds=60),
    position_after: int = 0,
    confirmed: bool = True,
    signature: str | None = None,
    block_time: datetime | None = None,
    kind: Kind = "unknown",
) -> LeaderEvent:
    _counter["n"] += 1
    return LeaderEvent(
        wallet=wallet,
        mint=mint,
        side="sell",
        token_delta_atoms=-500_000,
        sol_delta_lamports=60_000_000,
        position_after_atoms=position_after,
        signature=signature or f"sig-sell-{_counter['n']}",
        slot=2_000 + _counter["n"],
        block_time=block_time if block_time is not None else at - timedelta(seconds=1),
        first_seen_at=at,
        fields_complete_at=at + timedelta(milliseconds=2),
        source="nats",
        confirmed=confirmed,
        multi_mint=False,
        kind=kind,
    )


def gap(
    start: datetime,
    end: datetime | None,
    wallet: str | None = LEADER_A,
    reason: str = "socket_down",
) -> LeaderGap:
    return LeaderGap(wallet=wallet, start=start, end=end, reason=reason)


def dec(value: str) -> Decimal:
    return Decimal(value)


def confirmation(
    event: LeaderEvent,
    status: str = "confirmed",
    *,
    at: datetime | None = None,
    chain_position_after: int | None = None,
    chain_token_delta: int | None = None,
) -> LeaderConfirmation:
    return LeaderConfirmation(
        wallet=event.wallet,
        mint=event.mint,
        signature=event.signature,
        slot=event.slot,
        status=status,  # type: ignore[arg-type]
        reason=None if status == "confirmed" else f"{status} by test",
        confirmed_at=at or event.first_seen_at + timedelta(milliseconds=700),
        block_time=None,
        chain_position_after_atoms=chain_position_after,
        chain_token_delta_atoms=chain_token_delta,
    )
