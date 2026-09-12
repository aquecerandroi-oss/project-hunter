"""``GET /api/v1/orgs/{org_id}/meme/live`` — the real executor as the desk sees it
(T4.14), and ``POST .../meme/live/positions/{id}/sell-now``.

Every payload carries the permanent label **REAL**: these rows are signed
transactions on the owner's dedicated wallet. The API never signs — it exposes
whether its own ``ENABLE_MEME_LIVE_TRADING`` is on (``api_live_enabled``), which
is exactly and only what the desk needs to render "Aprovar (REAL)" with the
double confirmation; the executor's own flag and gates arrive through its
heartbeat (``hb:meme:executor``) and are reported separately, never inferred.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr

__all__ = [
    "MEME_LIVE_LABEL",
    "ExecutorStatus",
    "LiveExecutorOut",
    "LiveOrderOut",
    "LivePositionOut",
    "MemeLiveOut",
    "SellNowOut",
]

MEME_LIVE_LABEL = (
    "REAL — transações assinadas na carteira Solana dedicada; a chave vive só no meme-executor, "
    "a API nunca assina"
)

ExecutorStatus = Literal["alive", "stalled", "never", "heartbeat_missing", "redis_unavailable"]


class LiveExecutorOut(BaseModel):
    """What ``hb:meme:executor`` says, field by field — ``None`` when it does not say."""

    status: ExecutorStatus
    heartbeat_key: str
    heartbeat_ts: datetime | None
    executor_ts: datetime | None
    error: str | None = None
    live_enabled: bool | None = None
    cluster: str | None = None
    wallet_pubkey: str | None = None
    wallet_sol_balance: DecimalStr | None = None
    wallet_read_at: datetime | None = None
    kill_switch: str | None = None
    kill_switch_latched: bool | None = None
    kill_switch_latch_reason: str | None = None
    kill_switch_sources: dict[str, str] = {}
    gates: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    orders_by_state: dict[str, int] = {}
    positions_open: int | None = None
    blocked_exits: dict[str, str] = {}
    last_signature: str | None = None
    last_refusal: str | None = None
    day_start_sol_equity: DecimalStr | None = None
    equity_sol: DecimalStr | None = None
    daily_loss_sol: DecimalStr | None = None
    auto_close_on_emergency: bool | None = None
    last_entries_tick_at: datetime | None = None
    last_exits_tick_at: datetime | None = None


class LiveOrderOut(BaseModel):
    id: uuid.UUID
    proposal_id: uuid.UUID
    mint: str | None
    side: str
    client_order_id: str
    attempt: int
    status: str
    reason: str | None
    tx_signature: str | None
    admission_approved: bool | None
    first_refusal: str | None
    binding_constraint: str | None
    sol_final: DecimalStr | None
    fill: dict[str, Any] | None
    received_at: datetime
    submitted_at: datetime | None
    settled_at: datetime | None


class LivePositionOut(BaseModel):
    id: uuid.UUID
    proposal_id: uuid.UUID
    mint: str
    status: str
    entry_at: datetime
    tokens: int
    sol_spent: DecimalStr
    initial_risk_sol: DecimalStr
    params: dict[str, Any]
    mark_sol: DecimalStr | None
    mark_at: datetime | None
    mark_source: str | None
    mark_reason: str | None
    high_water_sol: DecimalStr | None
    exit_intent: dict[str, Any] | None
    sell_requested_at: datetime | None
    sell_requested_by: str | None
    exit_at: datetime | None
    exit: dict[str, Any] | None
    sol_received: DecimalStr | None
    pnl_sol: DecimalStr | None
    r_multiple: DecimalStr | None
    migrated: bool
    can_sell_now: bool


class MemeLiveOut(BaseModel):
    label: str = MEME_LIVE_LABEL
    server_now: datetime
    api_live_enabled: bool
    """The API's own ``ENABLE_MEME_LIVE_TRADING``: when true the desk renders
    "Aprovar (REAL)" (double confirmation) and may file ``mode = 'live'``."""

    executor: LiveExecutorOut
    positions: list[LivePositionOut]
    orders: list[LiveOrderOut]


class SellNowOut(BaseModel):
    label: str = MEME_LIVE_LABEL
    position_id: uuid.UUID
    status: str
    sell_requested_at: datetime | None
    sell_requested_by: str | None
    already_requested: bool
    note: str = "vende na curva na próxima passada do executor (≤ 5 s), nunca a esta marca"
