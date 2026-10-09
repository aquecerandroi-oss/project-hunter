"""Price and shape a copy's ``meme_paper_bets`` row with the Lab's own machinery (H-037) — no second
pricing: the buy is ``curve.quote_buy`` (the same call ``paper_fill``/``launch_lane_bets`` make), the
sale is ``paper_engine.close_bet`` (so the Mayhem cap — ``Snapshot.sell_cap_sol``, the observed real
SOL **plus** our own ``curve_cost_sol`` — and its ``sell_cap_model`` stamp come for free), and a
mint that already migrated is sold on the PumpSwap pool with ``pool_mark.mark_on_pool``/
``close_on_pool``. What this module adds is only the *shape*: the market state is the one **at
``decided_at`` + the declared execution latency** (never the leader's fill), and the row carries the
leader, the signature and an ms-precision timestamp trail.

Pure: no IO, no clock — the executor hands the instants in.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_buy, quote_sell
from hunter_meme_worker.copy_events import ms_iso
from hunter_meme_worker.lab_models import (
    BetEntry,
    BetExit,
    BetState,
    EffectiveParams,
    Snapshot,
    money_str,
)
from hunter_meme_worker.lab_values import INDETERMINATE, SELL_CAP_MODEL
from hunter_meme_worker.paper_engine import close_bet
from hunter_meme_worker.pool_mark import close_on_pool, mark_on_pool, stale_seconds

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_indicators.meme.pool import PoolTrade
    from hunter_meme_worker.copy_events import CloseIntent, OpenIntent
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = [
    "bet_state_of",
    "build_entry",
    "censored_exit",
    "close_on_curve",
    "close_on_pool_trade",
    "inert_lab_params",
    "snapshot_of",
]

_INERT_TARGET_X = Decimal(1_000_000)
_INERT_TRAILING_PCT = Decimal("99.99")
_LAB_BACKSTOP_S = 7 * 86_400
ENTRY_REASON = "copy_leader_buy"


def snapshot_of(state: NormalizedCurveState) -> Snapshot:
    """A chain read of the curve as the engine's :class:`Snapshot` (``observed_at`` = when the read
    came back, so it is never earlier than the instant it was asked for)."""
    return Snapshot(
        mint=state.mint,
        observed_at=state.observed_at,
        source=state.source,
        reserves=CurveReserves(
            virtual_sol_reserves=state.virtual_sol_reserves,
            virtual_token_reserves=state.virtual_token_reserves,
            real_token_reserves=state.real_token_reserves,
            complete=state.complete,
        ),
        real_sol_reserves=state.real_sol_reserves,
        total_supply=state.total_supply,
        complete=state.complete,
        mcap_sol=state.market_cap_sol,
        mayhem_enabled=state.mayhem_enabled,
    )


def inert_lab_params(spec: CopySpec) -> EffectiveParams:
    """What the Lab's own tick reads off this bet (it loads every open bet): numbers that never
    fire, so the leader — or our safety stop and time cap, in this lane — is the only exit. The
    time stop is a backstop a week past the cap, never the real one."""
    return EffectiveParams(
        size_sol=spec.size_sol,
        target_x=_INERT_TARGET_X,
        trailing_pct=_INERT_TRAILING_PCT,
        max_hold_s=spec.time_cap_s + _LAB_BACKSTOP_S,
        max_loss_pct=Decimal(100),
        exit_on_migration=False,
        exit_on_creator_dump=False,
    )


def _latency_block(
    intent_decided: datetime, snapshot_at: datetime, observed: datetime
) -> dict[str, Any]:
    return {
        "observed_to_decided_ms": round((intent_decided - observed).total_seconds() * 1000, 3),
        "decided_to_priced_ms": round((snapshot_at - intent_decided).total_seconds() * 1000, 3),
    }


def build_entry(
    spec: CopySpec,
    snapshot: Snapshot,
    intent: OpenIntent,
    *,
    queued_at: datetime,
    slot: int | None,
) -> BetEntry:
    """Buy ``spec.size_sol`` against ``snapshot`` — the market at the pricing instant, with the
    priority fee once on the leg exactly as ``paper_fill._build_entry`` does. Raises ``ValueError``
    when the curve cannot sell that much (``quote_buy``'s own refusal)."""
    quote = quote_buy(snapshot.reserves, spec.size_sol, spec.fee_pct)
    with localcontext(CONTEXT):
        spent = quote.total_sol + spec.priority_fee_sol
        first_mark = quote_sell(quote.reserves_after, quote.tokens, spec.fee_pct).net_sol
        first_mark -= spec.priority_fee_sol
        high_water = first_mark / spent
    ref = intent.leader
    entry: dict[str, Any] = {
        "snapshot": snapshot.as_json(),
        "reason": ENTRY_REASON,
        "decided_at": ms_iso(intent.decided_at),
        "decision_to_fill_ms": round(
            (snapshot.observed_at - intent.decided_at).total_seconds() * 1000
        ),
        "marginal_price_before_sol": money_str(
            snapshot.reserves.virtual_sol_reserves / snapshot.reserves.virtual_token_reserves
        ),
        "marginal_price_after_sol": money_str(quote.marginal_price_after_sol),
        "average_price_sol": money_str(quote.average_price_sol),
        "curve_cost_sol": money_str(quote.curve_cost_sol),
        "fee_sol": money_str(quote.fee_sol),
        "fee_pct": money_str(spec.fee_pct),
        "sell_cap_model": SELL_CAP_MODEL,
        "priority_fee_sol": money_str(spec.priority_fee_sol),
        "sol_spent": money_str(spent),
        "tokens": money_str(quote.tokens),
        "sol_usd": None,
        "sol_usd_source": None,
        "sol_usd_reason": "quote_unavailable",
        "leg": "single",
        "parent_bet_id": None,
        "copy": {
            "rule_set": spec.label,
            "leader": ref.as_json(),
            "leader_wallet": ref.wallet,
            "leader_signature": ref.signature,
            "leader_observed_at": ms_iso(ref.observed_at),
            "declared_execution_latency_ms": spec.execution_latency_ms,
            "leader_slot": ref.slot,
            "priced_slot": slot,
            "ts": {
                "leader_block_time": None if ref.block_time is None else ms_iso(ref.block_time),
                "observed_at": ms_iso(ref.observed_at),
                "first_seen_at": ms_iso(ref.observed_at),
                "fields_complete_at": ms_iso(ref.fields_complete_at),
                "server_ts": None if ref.server_ts is None else ms_iso(ref.server_ts),
                "decided_at": ms_iso(intent.decided_at),
                "target_at": ms_iso(intent.target_at),
                "queued_at": ms_iso(queued_at),
                "priced_at": ms_iso(snapshot.observed_at),
                "persisted_at": None,
            },
            "latency_ms": _latency_block(intent.decided_at, snapshot.observed_at, ref.observed_at),
            "confirmation_delay_ms": None,
            "invalid_reason": None,
        },
    }
    return BetEntry(
        entry_at=snapshot.observed_at,
        entry=entry,
        tokens=quote.tokens,
        sol_spent=spent,
        initial_risk_sol=spent,
        params=inert_lab_params(spec),
        mark_sol=first_mark,
        high_water_x=high_water,
        sol_usd_at_entry=None,
    )


def bet_state_of(
    *, bet_id: str, rule_set_id: str, mint: str, entry: BetEntry, mayhem: bool | None
) -> BetState:
    """The open bet as ``paper_engine`` reads it, rebuilt from the entry this lane wrote."""
    return BetState(
        id=bet_id,
        proposal_id="",
        rule_set_id=rule_set_id,
        mint=mint,
        entry_at=entry.entry_at,
        tokens=entry.tokens,
        sol_spent=entry.sol_spent,
        initial_risk_sol=entry.initial_risk_sol,
        params=entry.params,
        high_water_x=entry.high_water_x,
        mark_sol=entry.mark_sol,
        mark_at=entry.entry_at,
        exit_intent=None,
        fee_pct=Decimal(entry.entry["fee_pct"]),
        priority_fee_sol=Decimal(entry.entry["priority_fee_sol"]),
        curve_cost_sol=Decimal(entry.entry["curve_cost_sol"]),
        leg="single",
        parent_bet_id=None,
        mark_source="curve",
        mark_stale_s=None,
        is_mayhem=mayhem,
    )


def _exit_block(
    intent: CloseIntent, priced_at: datetime | None, persisted_at: datetime | None
) -> dict[str, Any]:
    ref = intent.leader
    return {
        "trigger": "copy_leader" if ref is not None else "copy_own",
        "leader_signature": None if ref is None else ref.signature,
        "leader_observed_at": None if ref is None else ms_iso(ref.observed_at),
        "ts": {
            "leader_block_time": (
                None if ref is None or ref.block_time is None else ms_iso(ref.block_time)
            ),
            "decided_at": ms_iso(intent.decided_at),
            "target_at": ms_iso(intent.target_at),
            "priced_at": None if priced_at is None else ms_iso(priced_at),
            "persisted_at": None if persisted_at is None else ms_iso(persisted_at),
        },
        "latency_ms": (
            {}
            if ref is None or priced_at is None
            else _latency_block(intent.decided_at, priced_at, ref.observed_at)
        ),
        "leader_position_after_atoms": None if ref is None else ref.position_after_atoms,
    }


def close_on_curve(state: BetState, snapshot: Snapshot, intent: CloseIntent) -> BetExit:
    """Sell everything against ``snapshot`` with the Lab's ``close_bet`` (cap and stamps included)."""
    closed = close_bet(state, snapshot, intent.reason, None, intent_snapshot_at=intent.decided_at)
    closed.exit["copy"] = _exit_block(intent, snapshot.observed_at, None)
    return closed


def close_on_pool_trade(
    state: BetState, trade: PoolTrade, known: list[PoolTrade], intent: CloseIntent
) -> BetExit:
    """Sell on the PumpSwap pool at ``trade`` — the first trade at or after the pricing instant."""
    pool_mark = mark_on_pool(state, trade, known, total_supply=None)
    closed = close_on_pool(
        state,
        pool_mark,
        intent.reason,
        None,
        intent_trade_at=None,
        mark_stale_s=stale_seconds(trade.block_time, intent.decided_at),
    )
    closed.exit["copy"] = _exit_block(intent, trade.block_time, None)
    return closed


def censored_exit(state: BetState, intent: CloseIntent, *, censor: str, now: datetime) -> BetExit:
    """No price was guessed: the copy is closed ``indeterminate`` with the named reason. The row
    keeps ``−stake`` like every ``rug_no_snapshot`` close, and every sum leaves it out."""
    with localcontext(CONTEXT):
        pnl = -state.sol_spent
        r_multiple = pnl / state.initial_risk_sol
    exit_payload: dict[str, Any] = {
        "reason": intent.reason,
        "censored": censor,
        "snapshot": None,
        "sol_received": "0",
        "sol_usd": None,
        "sol_usd_source": None,
        "sol_usd_reason": "no_sale_to_price",
        "outcome_quality": INDETERMINATE,
        "copy": _exit_block(intent, None, None),
    }
    return BetExit(
        exit_at=now,
        exit=exit_payload,
        pnl_sol=pnl,
        r_multiple=r_multiple,
        sol_usd_at_exit=None,
        outcome_quality=INDETERMINATE,
        outcome_quality_reason=censor,
    )
