"""Assembles ``GET /meme/live`` (T4.14): the executor's heartbeat read field by
field, the ledger's rows, and the API's own flag — never a number this module
made up. Pure: rows and a mapping in, a payload out."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from fastapi import status

from hunter_api.errors import HunterError
from hunter_api.repositories.meme_live import LiveOrderRow, LivePositionRow
from hunter_api.schemas.meme_live import LiveExecutorOut, LiveOrderOut, LivePositionOut, MemeLiveOut
from hunter_api.services.meme_lab_goal import parse_heartbeat_datetime

__all__ = [
    "EXECUTOR_STALLED_AFTER_S",
    "LivePositionNotFoundError",
    "build_meme_live",
    "read_executor",
]

EXECUTOR_STALLED_AFTER_S = 30
LAMPORTS = Decimal(1_000_000_000)


class LivePositionNotFoundError(HunterError):
    """404 — the same shape as the desk's ``ProposalNotFoundError`` (problem+json)."""

    def __init__(self, position_id: uuid.UUID) -> None:
        super().__init__(
            type_slug="meme-live-position-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meme live position {position_id} not found.",
        )


def _decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _bool(raw: str | None) -> bool | None:
    return None if raw is None or raw == "" else raw == "true"


def _json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed: Any = json.loads(raw)
    except ValueError:
        return None
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None


def read_executor(
    heartbeat: Mapping[str, str] | None, *, as_of: datetime, key: str, error: str | None
) -> LiveExecutorOut:
    fields = heartbeat or {}
    ts = parse_heartbeat_datetime(fields.get("ts"))
    executor_ts = parse_heartbeat_datetime(fields.get("executor_ts"))
    tick = parse_heartbeat_datetime(fields.get("last_entries_tick_at"))
    if error is not None:
        status = "redis_unavailable"
    elif not fields or executor_ts is None:
        status = "heartbeat_missing" if not fields else "never"
    elif tick is None:
        status = "never"
    elif (as_of - tick).total_seconds() > EXECUTOR_STALLED_AFTER_S:
        status = "stalled"
    else:
        status = "alive"
    orders_raw = _json(fields.get("orders_by_state")) or {}
    blocked_raw = _json(fields.get("blocked_exits")) or {}
    sources = {
        k.removeprefix("kill_switch_"): v
        for k, v in fields.items()
        if k.startswith("kill_switch_")
        and k not in ("kill_switch_latched", "kill_switch_latch_reason")
    }
    return LiveExecutorOut(
        status=status,  # type: ignore[arg-type]
        heartbeat_key=key,
        heartbeat_ts=ts,
        executor_ts=executor_ts,
        error=error,
        live_enabled=_bool(fields.get("live_enabled")),
        cluster=fields.get("cluster") or None,
        wallet_pubkey=fields.get("wallet_pubkey") or None,
        wallet_sol_balance=_decimal(fields.get("wallet_sol_balance")),
        wallet_read_at=parse_heartbeat_datetime(fields.get("wallet_read_at")),
        kill_switch=fields.get("kill_switch") or None,
        kill_switch_latched=_bool(fields.get("kill_switch_latched")),
        kill_switch_latch_reason=fields.get("kill_switch_latch_reason") or None,
        kill_switch_sources=sources,
        gates=_json(fields.get("gates")),
        policy=_json(fields.get("policy")),
        orders_by_state={str(k): int(v) for k, v in orders_raw.items()},
        positions_open=int(fields["positions_open"]) if fields.get("positions_open") else None,
        blocked_exits={str(k): str(v) for k, v in blocked_raw.items()},
        last_signature=fields.get("last_signature") or None,
        last_refusal=fields.get("last_refusal") or None,
        day_start_sol_equity=_decimal(fields.get("day_start_sol_equity")),
        equity_sol=_decimal(fields.get("equity_sol")),
        daily_loss_sol=_decimal(fields.get("daily_loss_sol")),
        auto_close_on_emergency=_bool(fields.get("auto_close_on_emergency")),
        last_entries_tick_at=tick,
        last_exits_tick_at=parse_heartbeat_datetime(fields.get("last_exits_tick_at")),
    )


def _refusals(admission: dict[str, Any]) -> list[str]:
    """The §4 refusal names in evaluation order, as ``MemeDecision.to_jsonable`` wrote them."""
    names: list[str] = []
    for raw in cast(list[Any], admission.get("checks") or []):
        if not isinstance(raw, dict):
            continue
        refusal = cast(dict[str, Any], raw).get("refusal")
        if isinstance(refusal, str) and refusal:
            names.append(refusal)
    return names


def order_out(row: LiveOrderRow) -> LiveOrderOut:
    sizing = cast(dict[str, Any], row.admission.get("sizing") or {})
    refusals = _refusals(row.admission)
    return LiveOrderOut(
        id=row.id,
        proposal_id=row.proposal_id,
        mint=row.mint,
        side=row.side,
        client_order_id=row.client_order_id,
        attempt=row.attempt,
        status=row.status,
        reason=row.reason,
        tx_signature=row.tx_signature,
        admission_approved=row.admission.get("approved") if "approved" in row.admission else None,
        first_refusal=refusals[0] if refusals else None,
        binding_constraint=sizing.get("binding_constraint"),
        sol_final=_decimal(str(row.intent.get("sol_final")))
        if row.intent.get("sol_final")
        else None,
        fill=row.fill,
        received_at=row.received_at,
        submitted_at=row.submitted_at,
        settled_at=row.settled_at,
    )


def position_out(row: LivePositionRow) -> LivePositionOut:
    return LivePositionOut(
        id=row.id,
        proposal_id=row.proposal_id,
        mint=row.mint,
        status=row.status,
        entry_at=row.entry_at,
        tokens=row.tokens,
        sol_spent=Decimal(row.sol_spent_lamports) / LAMPORTS,
        initial_risk_sol=row.initial_risk_sol,
        params=row.params,
        mark_sol=row.mark_sol,
        mark_at=row.mark_at,
        mark_source=row.mark_source,
        mark_reason=row.mark_reason,
        high_water_sol=row.high_water_sol,
        exit_intent=row.exit_intent,
        sell_requested_at=row.sell_requested_at,
        sell_requested_by=row.sell_requested_by,
        exit_at=row.exit_at,
        exit=row.exit,
        sol_received=None
        if row.sol_received_lamports is None
        else Decimal(row.sol_received_lamports) / LAMPORTS,
        pnl_sol=row.pnl_sol,
        r_multiple=row.r_multiple,
        migrated=row.migrated,
        can_sell_now=row.status == "open" and row.sell_requested_at is None,
    )


def build_meme_live(
    orders: list[LiveOrderRow],
    positions: list[LivePositionRow],
    heartbeat: Mapping[str, str] | None,
    *,
    as_of: datetime,
    heartbeat_key: str,
    redis_error: str | None,
    api_live_enabled: bool,
) -> MemeLiveOut:
    return MemeLiveOut(
        server_now=as_of,
        api_live_enabled=api_live_enabled,
        executor=read_executor(heartbeat, as_of=as_of, key=heartbeat_key, error=redis_error),
        positions=[position_out(p) for p in positions],
        orders=[order_out(o) for o in orders],
    )
