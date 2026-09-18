"""T4.54 — the treasury top-up orchestration: USDC -> SOL through Jupiter,
once per kill-switch tick.

Everton's directive of 17/09/2026 ("eu quero deixar atualizado para usar
outra moeda"): the bot wallet holds USDC beside its SOL and pump.fun buys are
SOL-only. Once per kill-switch tick (``main.kill_switch_once``, 10 s), when
``MEME_TREASURY_ENABLED`` is on, the live flag is on, a signer exists, the
kill switch is not latched, and the wallet's SOL is below
``MEME_TREASURY_SOL_FLOOR``, this module sizes a swap (capped per attempt and
per day, never above the wallet's own USDC, never past the effective target
``min(MEME_TREASURY_SOL_TARGET, wallet_max_sol - max_sol_per_trade)``),
quotes it, validates the quote against the request, and hands it to
``treasury_send`` — verify instruction by instruction, simulate with the
balance invariant, sign, send, confirm — one row in ``meme_treasury_swaps``
per attempt (``docs/RISK_ENGINE_MEME.md`` §16).

T4.54b (risk review, fix D): with the flag off this tick is a **pure no-op**
— no session, no RPC, no HTTP — and nothing raised inside it ever reaches
the kill-switch loop: an exception is logged, counted in ``rpc_errors`` and
the next tick starts clean. Fix C: ``submitted`` rows are reconciled
(``treasury_reconcile``) before any new attempt is sized.

The sizing math, quote validation and refusal classification are pure and
live in ``treasury_rules``; this module is the async wiring around them.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT, JupiterQuote
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.treasury_reconcile import reconcile_once
from hunter_meme_executor.treasury_rules import (
    USDC_MINT,
    effective_sol_target,
    should_attempt,
    size_first_pass,
    size_to_target,
    validate_quote,
)
from hunter_meme_executor.treasury_send import attempt_swap

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["LAMPORTS", "USDC_MINT", "USDC_UNIT", "treasury_once"]

logger = get_logger(__name__)

LAMPORTS = Decimal(1_000_000_000)
USDC_UNIT = Decimal(1_000_000)


async def treasury_once(ctx: ExecutorContext) -> None:
    """The kill-switch tick's entry point. Never raises (fix D)."""
    if not ctx.config.treasury_enabled:
        ctx.state.treasury_last_attempt_reason = "disabled"
        return
    try:
        await _tick(ctx)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        ctx.state.treasury_last_attempt_reason = f"tick_failed:{type(exc).__name__}"
        logger.exception("meme_treasury_tick_failed", error_type=type(exc).__name__)


async def _tick(ctx: ExecutorContext) -> None:
    cfg, state = ctx.config, ctx.state
    now = utcnow()
    if not cfg.live or ctx.signer is None:
        # Nothing to reconcile or read: a paper/signerless process never sent anything.
        state.treasury_last_attempt_reason = "live_disabled" if not cfg.live else "no_signer"
        return
    await reconcile_once(ctx)
    wallet_lamports = state.wallet_lamports
    if wallet_lamports is None:
        state.treasury_last_attempt_reason = "wallet_balance_unread"
        return
    wallet_sol = Decimal(wallet_lamports) / LAMPORTS
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        last_attempt = await treasury_db.last_attempt_at(session)
        usdc_today = await treasury_db.usdc_committed_last_24h(session, now=now)
    reason = should_attempt(
        enabled=cfg.treasury_enabled,
        live=cfg.live,
        has_signer=True,  # narrowed above: a signerless process returned already
        kill_blocked=ctx.kill.blocks_entries,
        wallet_sol=wallet_sol,
        floor=cfg.treasury_sol_floor,
        last_attempt_at=last_attempt,
        min_interval_s=cfg.treasury_min_interval_s,
        now=now,
        usdc_spent_today=usdc_today,
        daily_cap=cfg.treasury_max_usdc_per_day,
    )
    state.treasury_last_attempt_reason = reason or ""
    if reason is not None:
        if reason != "sol_above_floor":
            logger.info("meme_treasury_skipped", reason=reason)
        return
    sized = await _size_and_quote(ctx, wallet_lamports=wallet_lamports, usdc_today=usdc_today)
    if sized is not None:
        usdc_atoms, quote = sized
        await attempt_swap(ctx, usdc_atoms=usdc_atoms, quote=quote, wallet_sol=wallet_sol)


async def _size_and_quote(
    ctx: ExecutorContext, *, wallet_lamports: int, usdc_today: Decimal
) -> tuple[int, JupiterQuote] | None:
    cfg, state = ctx.config, ctx.state
    assert ctx.signer is not None
    target_sol, target_note = effective_sol_target(
        configured_target_sol=cfg.treasury_sol_target,
        wallet_max_sol=cfg.limits.wallet_max_sol,
        max_sol_per_trade=cfg.limits.max_sol_per_trade,
    )
    if target_note is not None:
        # Fix E: a target the entry gate could never live with is a config
        # error, refused by name — never silently bought and parked.
        state.treasury_last_attempt_reason = target_note
        logger.warning(
            "meme_treasury_target_refused",
            reason=target_note,
            configured=str(cfg.treasury_sol_target),
            cap=str(target_sol),
        )
        return None
    try:
        usdc_read = await asyncio.to_thread(
            ctx.chain.token_account, ctx.signer.pubkey, USDC_MINT, TOKEN_PROGRAM_ID
        )
    except Exception as exc:
        state.rpc_errors += 1
        state.treasury_last_attempt_reason = "usdc_balance_unreadable"
        logger.warning("meme_treasury_usdc_unreadable", error_type=type(exc).__name__)
        return None
    wallet_usdc_atoms = usdc_read.amount if usdc_read.exists else 0
    state.treasury_wallet_usdc = Decimal(wallet_usdc_atoms) / USDC_UNIT
    remaining_daily_atoms = int(
        max(Decimal(0), cfg.treasury_max_usdc_per_day - usdc_today) * USDC_UNIT
    )
    first_pass_atoms = size_first_pass(
        wallet_usdc_atoms=wallet_usdc_atoms,
        remaining_daily_cap_atoms=remaining_daily_atoms,
        max_per_swap_atoms=int(cfg.treasury_max_usdc_per_swap * USDC_UNIT),
    )
    if first_pass_atoms <= 0:
        state.treasury_last_attempt_reason = "nothing_to_swap"
        return None
    quote = await _quote(ctx, first_pass_atoms)
    if quote is None:
        return None
    resized_atoms = size_to_target(
        first_pass_usdc_atoms=first_pass_atoms,
        quote_in_amount_atoms=int(quote.in_amount),
        quote_out_amount_atoms=int(quote.out_amount),
        wallet_lamports=wallet_lamports,
        target_lamports=int(target_sol * LAMPORTS),
    )
    if resized_atoms <= 0:
        state.treasury_last_attempt_reason = "target_already_met"
        return None
    if resized_atoms < first_pass_atoms:
        quote = await _quote(ctx, resized_atoms)
        if quote is None:
            return None
    if wallet_lamports + int(quote.out_amount) > int(cfg.limits.wallet_max_sol * LAMPORTS):
        state.treasury_last_attempt_reason = "target_above_wallet_max"
        return None
    return resized_atoms, quote


async def _quote(ctx: ExecutorContext, amount_atoms: int) -> JupiterQuote | None:
    """One ``GET /quote``, validated against what was asked (fix B) — a quote
    for other mints, another amount or another tolerance is refused, never
    handed to the builder."""
    slippage_bps = ctx.config.treasury_max_slippage_bps
    try:
        quote = await asyncio.to_thread(
            ctx.treasury_client.quote,
            input_mint=USDC_MINT,
            output_mint=WRAPPED_SOL_MINT,
            amount=amount_atoms,
            slippage_bps=slippage_bps,
        )
    except ExchangeError as exc:
        ctx.state.treasury_last_attempt_reason = f"quote_failed:{type(exc).__name__}"
        logger.warning("meme_treasury_quote_failed", error_type=type(exc).__name__)
        return None
    mismatch = validate_quote(
        quote,
        input_mint=USDC_MINT,
        output_mint=WRAPPED_SOL_MINT,
        amount_atoms=amount_atoms,
        slippage_bps=slippage_bps,
    )
    if mismatch is not None:
        ctx.state.treasury_last_attempt_reason = mismatch
        logger.warning("meme_treasury_quote_mismatch", reason=mismatch, amount=amount_atoms)
        return None
    return quote
