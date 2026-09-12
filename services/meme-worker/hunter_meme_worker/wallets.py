"""The wallet loop (T4.12): every 30 s, the real fills of each public address in
``MEME_WATCH_WALLETS`` from the chain, into ``meme_wallet_trades`` and the
derived ``meme_wallet_positions``.

**One page of signatures per wallet, one transaction per new signature.**
``getSignaturesForAddress`` newest-first, ``until`` the last signature this
process saw (loaded from the ledger on the first cycle after a restart); the
page is walked oldest-first so the cursor only ever advances past a signature
that was written or deliberately skipped. A signature the node reports as
failed is not a fill and is skipped; one the ledger already has is skipped; the
rest are read, decoded (``hunter_exchanges.pumpfun.wallet_fills``) and appended
— ``side = 'unknown'`` with ``raw`` when nothing decoded. A **buy** gets its
``lab_context`` in the same session (``wallets_lab.py``).

**The RPC is the scarcest budget and it is a public one**: this loop has its
own bucket (``MemeConfig.wallets_rpc_per_s``, two a second) beside the chain
loop's, and an RPC failure ends the wallet's cycle without advancing its
cursor — it is counted on ``solana_rpc`` and in the heartbeat, never raised,
because ``collect.forever`` would take the radar down with it.

**Positions are recomputed, never adjusted**: every ``(wallet, mint)`` a new
fill touched is folded again from its whole ledger (``wallet_positions.py``),
and every open position of the watched wallets is re-marked each cycle from
the latest curve snapshot or tape.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.wallet_fills import WalletFill, wallet_fills_from_transaction
from hunter_meme_worker.features import RATE_LIMITED
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.metrics import meme_rows_total, meme_source_errors_total
from hunter_meme_worker.sources import SOLANA_RPC
from hunter_meme_worker.wallet_positions import (
    DEFAULT_FEE_PCT,
    fold_position,
    mark_of,
    unrealized_and_r,
)
from hunter_meme_worker.wallets_lab import lab_context_for
from hunter_meme_worker.wallets_repo import (
    existing_signatures,
    insert_fills,
    latest_snapshot,
    latest_tape,
    load_fills,
    newest_signature,
    open_positions,
    set_lab_context,
    upsert_position,
)
from hunter_meme_worker.wallets_state import WalletsWatcher, build_wallets

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.lab_models import RuleSetSpec

logger = get_logger(__name__)

__all__ = ["WalletsReport", "WalletsWatcher", "build_wallets", "wallets_once"]

WORKER_ROLE = "hunter_worker"
TRANSACTION_NOT_FOUND = "transaction_not_found"


@dataclass(frozen=True, slots=True)
class WalletsReport:
    wallets: int
    signatures: int = 0
    fills: int = 0
    unknown: int = 0
    failed: int = 0
    known: int = 0
    calls: int = 0
    positions: int = 0
    errors: int = 0
    duration_s: float = 0.0


@dataclass
class _Cycle:
    signatures: int = 0
    fills: int = 0
    unknown: int = 0
    failed: int = 0
    known: int = 0
    calls: int = 0
    errors: int = 0


def _record_error(watcher: WalletsWatcher, exc: Exception, now: datetime) -> None:
    watcher.errors_1h.add(now)
    meme_source_errors_total.labels(source=SOLANA_RPC).inc()
    if watcher.sources is not None:
        watcher.sources[SOLANA_RPC].record_spent(now)
        watcher.sources[SOLANA_RPC].record_error(
            now, RATE_LIMITED if isinstance(exc, RateLimited) else type(exc).__name__
        )
    logger.warning("meme_wallets_rpc_failed", error=str(exc)[:200])


def _fills_of(
    tx: dict[str, Any] | None, wallet: str, info: SignatureInfo
) -> tuple[WalletFill, ...]:
    if tx is None:
        return (
            WalletFill(
                wallet,
                info.signature,
                0,
                info.slot,
                info.block_time,
                None,
                "unknown",
                None,
                None,
                None,
                None,
                "none",
                {"reason": TRANSACTION_NOT_FOUND},
            ),  # fmt: skip
        )
    return wallet_fills_from_transaction(
        tx,
        wallet=wallet,
        signature=info.signature,
        slot_hint=info.slot,
        block_time_hint=info.block_time,
    )


async def _collect_wallet(
    session: AsyncSession,
    watcher: WalletsWatcher,
    wallet: str,
    specs: Sequence[RuleSetSpec],
    *,
    now: datetime,
) -> _Cycle:
    cycle = _Cycle()
    if wallet not in watcher.cursors:
        watcher.cursors[wallet] = await newest_signature(session, wallet)
    try:
        infos = await watcher.chain.get_signatures_for_address(
            wallet, until=watcher.cursors[wallet], limit=watcher.page
        )
    except Exception as exc:  # counted on the source; the cursor does not move
        _record_error(watcher, exc, now)
        cycle.errors += 1
        return cycle
    cycle.calls += 1
    if not infos:
        return cycle
    known = await existing_signatures(session, wallet, [i.signature for i in infos])
    for info in reversed(infos):  # oldest first: the cursor advances past what was written
        cycle.signatures += 1
        if info.failed or info.signature in known:
            cycle.failed += info.failed
            cycle.known += info.signature in known
            watcher.cursors[wallet] = info.signature
            continue
        try:
            tx = await watcher.chain.get_transaction(info.signature)
        except Exception as exc:
            _record_error(watcher, exc, now)
            cycle.errors += 1
            return cycle
        cycle.calls += 1
        fills = _fills_of(tx, wallet, info)
        cycle.failed += not fills
        for fill in await insert_fills(session, fills, received_at=utcnow()):
            meme_rows_total.labels(table="meme_wallet_trades").inc()
            if not fill.is_fill:
                cycle.unknown += 1
                continue
            cycle.fills += 1
            if fill.mint is not None:
                watcher.affected.add((wallet, fill.mint))
            if fill.block_time is not None and (
                watcher.last_trade_at is None or fill.block_time > watcher.last_trade_at
            ):
                watcher.last_trade_at = fill.block_time
            if fill.side == "buy" and fill.mint is not None:
                lab = await lab_context_for(
                    session,
                    mint=fill.mint,
                    at=fill.block_time or now,
                    specs=specs,
                    features_version=watcher.features_version,
                    now=now,
                )
                await set_lab_context(
                    session,
                    signature=fill.signature,
                    event_index=fill.event_index,
                    context=lab.context,
                    hype_score=lab.hype_score,
                    line_reason=lab.line_reason,
                )
        watcher.cursors[wallet] = info.signature
    return cycle


async def _refresh_positions(session: AsyncSession, watcher: WalletsWatcher, now: datetime) -> int:
    """Fold every touched ``(wallet, mint)`` from its ledger and re-mark every open one."""
    targets = set(watcher.affected) | set(await open_positions(session, watcher.wallets))
    watcher.affected = set()
    written = 0
    for wallet, mint in sorted(targets):
        loaded = await load_fills(session, wallet, mint)
        if not loaded.fills:
            continue
        position = fold_position(loaded.fills)
        mark = mark_of(
            position,
            snapshot=await latest_snapshot(session, mint),
            tape=await latest_tape(session, mint),
            fee_pct=loaded.fee_pct or DEFAULT_FEE_PCT,
        )
        unrealized, r_multiple = unrealized_and_r(position, mark)
        await upsert_position(
            session,
            wallet=wallet,
            mint=mint,
            position=position,
            mark=mark,
            unrealized=unrealized,
            r_multiple=r_multiple,
            now=now,
        )
        written += 1
    watcher.positions_open = len(await open_positions(session, watcher.wallets))
    return written


async def wallets_once(ctx: RadarContext) -> WalletsReport:
    """One cycle over every watched wallet. Never raises on the RPC."""
    watcher = ctx.wallets
    assert watcher is not None
    started = time.monotonic()
    now = utcnow()
    total = _Cycle()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        specs = await load_active_rule_sets(session)
    for wallet in watcher.wallets:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            cycle = await _collect_wallet(session, watcher, wallet, specs, now=now)
        for name in ("signatures", "fills", "unknown", "failed", "known", "calls", "errors"):
            setattr(total, name, getattr(total, name) + getattr(cycle, name))
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await _refresh_positions(session, watcher, now)
    duration = round(time.monotonic() - started, 3)
    watcher.trades_60s.add(now, total.fills)
    watcher.unknown_1h.add(now, total.unknown)
    watcher.calls_60s.add(now, total.calls)
    watcher.last_cycle_at, watcher.last_cycle_s = now, duration
    if watcher.sources is not None and total.calls:
        watcher.sources[SOLANA_RPC].record_ok(
            observed_at=watcher.last_trade_at or now, received_at=now, count=total.calls
        )
    if total.fills or total.unknown or total.errors:
        logger.info(
            "meme_wallets_cycle",
            fills=total.fills,
            unknown=total.unknown,
            failed=total.failed,
            errors=total.errors,
            positions=positions,
        )
    return WalletsReport(
        wallets=len(watcher.wallets),
        signatures=total.signatures,
        fills=total.fills,
        unknown=total.unknown,
        failed=total.failed,
        known=total.known,
        calls=total.calls,
        positions=positions,
        errors=total.errors,
        duration_s=duration,
    )
