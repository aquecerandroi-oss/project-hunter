"""T4.54 — the treasury top-up orchestration: USDC -> SOL through Jupiter,
once per kill-switch tick.

Everton's directive of 17/09/2026 ("eu quero deixar atualizado para usar
outra moeda"): the bot wallet holds USDC beside its SOL and pump.fun buys are
SOL-only. Once per kill-switch tick (``main.kill_switch_once``, 10 s), when
``MEME_TREASURY_ENABLED`` is on, the live flag is on, a signer exists, the
kill switch is not latched, and the wallet's SOL is below
``MEME_TREASURY_SOL_FLOOR``, this module sizes a swap (capped per attempt and
per day, never above the wallet's own USDC), quotes it, **verifies** the
built transaction against a program allowlist before it is ever signed
(``treasury_rules.verify_swap_transaction``), simulates it, signs it with the
executor's own signer, sends it and confirms it — one row in
``meme_treasury_swaps`` per attempt, whether it lands, fails or is refused
before anything is built (``docs/RISK_ENGINE_MEME.md`` new §).

The sizing math, the refusal classification and the verifier are pure and
live in ``treasury_rules`` (testable with no network, no database, no
signer); this module is the async wiring around them plus the one RPC/DB/HTTP
surface each step touches.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT, JupiterQuote, decode_versioned_transaction
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, serialize_transaction
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.treasury_rules import (
    TreasurySwapRefused,
    classify_quote_refusal,
    should_attempt,
    size_first_pass,
    size_to_target,
    verify_swap_transaction,
)

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["LAMPORTS", "USDC_MINT", "USDC_UNIT", "treasury_once"]

logger = get_logger(__name__)

LAMPORTS = Decimal(1_000_000_000)
USDC_UNIT = Decimal(1_000_000)
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


async def treasury_once(ctx: ExecutorContext) -> None:
    cfg, state = ctx.config, ctx.state
    now = utcnow()
    wallet_lamports = state.wallet_lamports
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        last_attempt = await treasury_db.last_attempt_at(session)
        usdc_today = await treasury_db.usdc_confirmed_last_24h(session, now=now)
    if wallet_lamports is None:
        state.treasury_last_attempt_reason = "wallet_balance_unread"
        return
    wallet_sol = Decimal(wallet_lamports) / LAMPORTS
    reason = should_attempt(
        enabled=cfg.treasury_enabled,
        live=cfg.live,
        has_signer=ctx.signer is not None,
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
        if reason not in ("disabled", "sol_above_floor"):
            logger.info("meme_treasury_skipped", reason=reason)
        return
    assert ctx.signer is not None
    sized = await _size_and_quote(ctx, wallet_lamports=wallet_lamports, usdc_today=usdc_today)
    if sized is not None:
        await _attempt_swap(ctx, usdc_atoms=sized[0], quote=sized[1], wallet_sol=wallet_sol)


async def _size_and_quote(
    ctx: ExecutorContext, *, wallet_lamports: int, usdc_today: Decimal
) -> tuple[int, JupiterQuote] | None:
    cfg, state = ctx.config, ctx.state
    assert ctx.signer is not None
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
        target_lamports=int(cfg.treasury_sol_target * LAMPORTS),
    )
    if resized_atoms <= 0:
        state.treasury_last_attempt_reason = "target_already_met"
        return None
    if resized_atoms < first_pass_atoms:
        quote = await _quote(ctx, resized_atoms)
        if quote is None:
            return None
    return resized_atoms, quote


async def _quote(ctx: ExecutorContext, amount_atoms: int) -> JupiterQuote | None:
    try:
        return await asyncio.to_thread(
            ctx.treasury_client.quote,
            input_mint=USDC_MINT,
            output_mint=WRAPPED_SOL_MINT,
            amount=amount_atoms,
            slippage_bps=ctx.config.treasury_max_slippage_bps,
        )
    except ExchangeError as exc:
        ctx.state.treasury_last_attempt_reason = f"quote_failed:{type(exc).__name__}"
        logger.warning("meme_treasury_quote_failed", error_type=type(exc).__name__)
        return None


async def _attempt_swap(
    ctx: ExecutorContext, *, usdc_atoms: int, quote: JupiterQuote, wallet_sol: Decimal
) -> None:
    assert ctx.signer is not None
    cfg, state = ctx.config, ctx.state
    usdc_in = Decimal(usdc_atoms) / USDC_UNIT
    sol_out_quoted = Decimal(quote.out_amount) / LAMPORTS
    refusal = classify_quote_refusal(quote)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        if refusal is not None:
            await treasury_db.insert_refused(
                session,
                reason="sol_below_floor",
                refusal=refusal,
                usdc_in=usdc_in,
                sol_out_quoted=sol_out_quoted,
                price_impact_pct=quote.price_impact_pct,
                slippage_bps=cfg.treasury_max_slippage_bps,
                wallet_sol_before=wallet_sol,
            )
            state.treasury_last_attempt_reason = refusal
            return
        swap_id = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=usdc_in,
            sol_out_quoted=sol_out_quoted,
            price_impact_pct=quote.price_impact_pct,
            slippage_bps=cfg.treasury_max_slippage_bps,
            wallet_sol_before=wallet_sol,
        )
    try:
        swap_tx = await asyncio.to_thread(
            ctx.treasury_client.swap, quote=quote, user_public_key=ctx.signer.pubkey
        )
        raw_tx = base64.b64decode(swap_tx.swap_transaction_b64)
        decoded = decode_versioned_transaction(raw_tx)
        verify_swap_transaction(decoded.message, wallet=ctx.signer.pubkey)
    except TreasurySwapRefused as exc:
        await _refuse(ctx, swap_id, exc.reason)
        return
    except Exception as exc:
        await _refuse(ctx, swap_id, f"swap_build_failed:{type(exc).__name__}")
        logger.warning("meme_treasury_swap_build_failed", error_type=type(exc).__name__)
        return
    await _simulate_sign_and_send(
        ctx,
        swap_id,
        message_bytes=decoded.message_bytes,
        raw_tx=raw_tx,
        wallet_sol_before=wallet_sol,
        usdc_in=usdc_in,
    )


async def _refuse(ctx: ExecutorContext, swap_id: uuid.UUID, refusal: str) -> None:
    ctx.state.treasury_last_attempt_reason = refusal
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_refused(session, swap_id, refusal=refusal)


async def _simulate_sign_and_send(
    ctx: ExecutorContext,
    swap_id: uuid.UUID,
    *,
    message_bytes: bytes,
    raw_tx: bytes,
    wallet_sol_before: Decimal,
    usdc_in: Decimal,
) -> None:
    assert ctx.signer is not None
    try:
        simulation = await asyncio.to_thread(
            ctx.chain.rpc.simulate_transaction, raw_tx, sig_verify=False
        )
    except Exception as exc:
        await _refuse(ctx, swap_id, f"simulation_unreadable:{type(exc).__name__}")
        return
    if not simulation.ok:
        await _refuse(ctx, swap_id, f"simulation_failed:{str(simulation.err)[:120]}")
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_simulated(session, swap_id)

    signature_bytes = ctx.signer.sign(message_bytes)
    signed_tx = serialize_transaction((signature_bytes,), message_bytes)
    try:
        signature = await asyncio.to_thread(ctx.chain.rpc.send_transaction, signed_tx)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        ctx.state.treasury_last_attempt_reason = f"send_failed:{type(exc).__name__}"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await treasury_db.mark_failed(session, swap_id)
        logger.error("meme_treasury_send_failed", error_type=type(exc).__name__)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_submitted(session, swap_id, signature=signature)
    ctx.state.last_signature = signature

    if not await _confirm(ctx, signature):
        ctx.state.treasury_last_attempt_reason = "confirm_timeout"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await treasury_db.mark_failed(session, swap_id)
        return
    try:
        wallet_after = await asyncio.to_thread(ctx.chain.wallet, ctx.signer.pubkey)
        wallet_sol_after = Decimal(wallet_after.lamports) / LAMPORTS
    except Exception:
        wallet_sol_after = wallet_sol_before
    sol_out_filled = max(Decimal(0), wallet_sol_after - wallet_sol_before)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_confirmed(
            session, swap_id, sol_out_filled=sol_out_filled, wallet_sol_after=wallet_sol_after
        )
    ctx.state.treasury_last_swap_at = utcnow()
    ctx.state.treasury_last_attempt_reason = f"ok:{signature}"
    logger.info(
        "meme_treasury_swap_confirmed",
        signature=signature,
        usdc_in=str(usdc_in),
        sol_out_filled=str(sol_out_filled),
    )


async def _confirm(ctx: ExecutorContext, signature: str) -> bool:
    attempts = max(1, int(ctx.config.confirm_timeout_s))
    for _ in range(attempts):
        try:
            statuses = await asyncio.to_thread(ctx.chain.rpc.get_signature_statuses, [signature])
        except Exception:
            await asyncio.sleep(1.0)
            continue
        status = statuses[0] if statuses else None
        if status is not None:
            if status.get("err") is not None:
                return False
            if status.get("confirmationStatus") in ("confirmed", "finalized"):
                return True
        await asyncio.sleep(1.0)
    return False
