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
    "Spot1ClosedOut",
    "Spot1OpenPositionOut",
    "Spot1Out",
    "Spot1RefutationOut",
]

MEME_LIVE_LABEL = (
    "REAL — transações assinadas na carteira Solana dedicada; a chave vive só no meme-executor, "
    "a API nunca assina"
)

ExecutorStatus = Literal["alive", "stalled", "never", "heartbeat_missing", "redis_unavailable"]


class Spot1OpenPositionOut(BaseModel):
    """One open leg of the ``spot/1`` desk, design §7 -- at most 3 in practice."""

    market: str
    mint8: str
    entry_at: datetime
    sol_spent: DecimalStr
    mark_sol: DecimalStr | None
    r_now: DecimalStr | None
    age_s: int | None
    horizon_s: int | None
    mark_stale_s: int | None
    """Only set after three consecutive failed quotes (design §4); ``None`` means fresh."""


class Spot1ClosedOut(BaseModel):
    n: int
    sum_r_gross: DecimalStr
    sum_r_net: DecimalStr
    sum_pnl_sol: DecimalStr
    expectancy_r_net: DecimalStr | None
    """``None`` with ``n == 0`` -- no sample yet, never a made-up zero."""


class Spot1RefutationOut(BaseModel):
    trades: int
    threshold: int
    state: str
    """``ok`` / ``refuted`` / ``cooldown`` -- design §8's hard stop, as written."""


class Spot1Out(BaseModel):
    """``spot1`` field of ``hb:meme:executor``, design §7 -- the whole contract,
    parsed field by field; absent or malformed is ``None`` at the caller, never
    a partial/invented shape."""

    mode: str
    """``on`` / ``inert:<motivo>`` / ``refuted`` / ``cooldown`` (design §7/§8)."""
    strategy_version: str
    ticket_sol: DecimalStr
    max_open: int
    markets_enabled: int
    open: list[Spot1OpenPositionOut]
    signals_seen: int
    admitted: int
    refused_by_reason: dict[str, int]
    exits_by_reason: dict[str, int]
    blocked_exits: dict[str, str]
    closed: Spot1ClosedOut
    refutation: Spot1RefutationOut
    last_signature: str | None
    last_refusal: str | None
    last_entries_tick_at: datetime | None
    last_exits_tick_at: datetime | None


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
    auto_approve: bool | None = None
    """T4.28 stage 1 ("liga sozinho"): the executor opens the desk's ``operator``
    proposal itself, inside the written small-test scope, without the click."""
    auto_approve_max_per_hour: int | None = None
    auto_approved_1h: int | None = None
    """Proposals the robot opened **and the admission let through** in the last
    hour (T4.28e: a refusal costs no slot of this budget)."""
    auto_refused_1h: dict[str, int] = {}
    """The last hour's admission refusals of robot-opened proposals, by reason —
    the same vocabulary as ``LiveOrderOut.reason``/``first_refusal``."""
    auto_skipped: dict[str, int] = {}
    """Passes where the robot did not even open a proposal, by reason (in-memory
    since the process's last restart) — ``expired``, ``too_old``, ``mint_busy_superseded``,
    ``recently_refused`` (T4.28f), ``exceeds_max_sol_per_bet``, ``hourly_cap``,
    ``tick_cap``, ``mint_repeated``, ``kill_switch``, ``program_upgraded``,
    ``scope_exhausted:<max_trades|max_total_sol>``, ``decided_concurrently``."""
    small_test_used_sol: DecimalStr | None = None
    small_test_trades_done: int | None = None
    small_test_remaining_sol: DecimalStr | None = None
    small_test_exhausted: str | None = None
    """``max_trades`` or ``max_total_sol`` when the written scope is spent, or
    ``None`` while there is room left."""
    gates_mtime: datetime | None = None
    """When ``meme_gates.json`` was last written, per ``stat`` (T4.28d)."""
    gates_reloaded_at: datetime | None = None
    """When this process last swapped its policy from a reload of that file."""
    gates_reload_error: str | None = None
    """The latched reload reason, or ``deferred:<reason>`` during the one-tick
    grace after a parse failure (T4.28f) — empty/``None`` means the last read
    of the file was a good one."""
    spot1: Spot1Out | None = None
    """The ``spot/1`` desk (T4.74, design §7) -- ``None`` on an executor build
    that predates the field, or on any malformed blob; never invented."""


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
