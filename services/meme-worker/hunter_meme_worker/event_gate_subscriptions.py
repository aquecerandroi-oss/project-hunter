"""Keep the WS subscriptions equal to the tracked set the fast lane already
names (T4.52b-3, plan-T4.52b.md §4): no new query, the exact
:func:`~hunter_meme_worker.fast_lane.young_mints` a mint has to be in for the
15-second series to fold it at all.

**T4.70 (notes-T4.66.md §7, P0): subscribe at the instant of the `create`,
not only every 5 s.** A sniper buys in 1-2 s; the periodic sync's own 5 s
grace routinely missed the mint's birth, so ``covered_from_birth`` came back
``False`` and EXP-M19's early-wallet reading was ``early_retention_unknown``
for most young mints. :func:`subscribe_at_create` is the second producer of
the same subscribed set :func:`sync_subscriptions` already owns — the exact
same PDA derivation, the exact same ``max_mints`` cap, the exact same
``mint in rt.subs`` guard the periodic sync uses to skip a mint already
covered, so the two never double-subscribe.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeUnavailable
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_meme_worker.event_gate_caches import MAX_CACHE_AGE_S, prune_event_gate_caches
from hunter_meme_worker.event_gate_runtime import Subscription
from hunter_meme_worker.fast_lane import young_mints

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.models import NormalizedMemeTokenCreated
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime

__all__ = ["subscribe_at_create", "sync_subscriptions"]

logger = get_logger(__name__)


async def _subscribe_mint(
    rt: EventGateRuntime, mint: str, *, first_seen_at: datetime, now: datetime | None = None
) -> None:
    pda = bonding_curve_address(mint)
    try:
        logs_id = await rt.ws.subscribe_logs(mentions=[pda], commitment=rt.config.commitment)
        account_id = await rt.ws.subscribe_account(pda, commitment=rt.config.commitment)
    except ExchangeUnavailable:
        return
    rt.subs[mint] = Subscription(logs_id, account_id, first_seen_at)
    rt.subs_by_logical[logs_id] = mint
    rt.subs_by_logical[account_id] = mint
    rt.book.touch(mint, at=now or utcnow(), first_seen_at=first_seen_at)


async def subscribe_at_create(
    rt: EventGateRuntime, event: NormalizedMemeTokenCreated, *, now: datetime | None = None
) -> None:
    """Called by ``discovery._handle`` for every ``create`` frame, the same
    hook the launch lane already uses (T4.67a) — independent of
    ``MEME_LAUNCH_LANE``. A no-op when the mint is already subscribed (the
    periodic sync got there first, or a replayed frame) or the book is at
    ``max_mints`` (refused exactly like the periodic sync's own cap, never
    raised). Sets ``state.expects_create_slot`` so the first trade
    notification's slot becomes ``crowd.create_slot`` (T4.66's 3-slot rule),
    and ``creation_block_buyers`` starts at ``{event.creator}`` — the
    create frame's own buyer, per T4.67a's own reading of the program.
    Records ``event.signature`` on the ledger unconditionally (T4.89b,
    H-015) — research's own handle to resolve the create transaction's real
    slot later, independent of whether it also carried an initial buy."""
    now = now or utcnow()
    if event.mint in rt.subs or len(rt.subs) >= rt.config.max_mints:
        return
    try:
        await _subscribe_mint(rt, event.mint, first_seen_at=event.observed_at, now=now)
    except (ConnectionError, TimeoutError, OSError) as exc:
        # T4.70b (incident 2026-09-19 18:05:32 UTC): a transient RPC WS error
        # here must never escape into discovery's own TaskGroup — the mint
        # is picked up by sync_subscriptions's own 5 s pass instead.
        if rt.stats.record_subscribe_at_create_failed(now):
            logger.warning(
                "meme_event_gate_subscribe_at_create_failed",
                mint8=event.mint[:8],
                error_type=type(exc).__name__,
            )
        return
    state = rt.book.get(event.mint)
    if state is None:
        return  # ExchangeUnavailable inside _subscribe_mint, or the book is full
    state.creator = event.creator
    state.crowd.creator = event.creator
    state.expects_create_slot = True
    state.creation_block_buyers = frozenset({event.creator}) if event.creator else frozenset()
    state.wallets.record_create_signature(event.signature)
    if event.creator_initial_sol is not None and event.creator_initial_tokens is not None:
        # T4.89: the create's own buy never reaches the logs subscription opened
        # after it — the ledger takes it from the frame (deduped by signature).
        state.wallets.seed_initial_buy(
            event.creator,
            sol=event.creator_initial_sol,
            tokens=event.creator_initial_tokens,
            signature=event.signature,
        )
    latency_ms = max(0.0, (now - event.received_at).total_seconds() * 1000)
    rt.stats.record_subscribed_at_create(latency_ms)


async def _unsubscribe_mint(rt: EventGateRuntime, mint: str) -> None:
    sub = rt.subs.pop(mint, None)
    if sub is None:
        return
    rt.subs_by_logical.pop(sub.logs_id, None)
    rt.subs_by_logical.pop(sub.account_id, None)
    await rt.ws.unsubscribe(sub.logs_id)
    await rt.ws.unsubscribe(sub.account_id)
    rt.book.evict(mint)
    rt.reserves.pop(mint, None)
    rt.debouncer.forget(mint)  # F1: no per-mint seat left behind on unsubscribe
    rt.pending_trail.pop(mint, None)
    rt.pending_tapes.pop(mint, None)
    rt.trail_last_written.pop(mint, None)
    rt.stats.record_unsubscribed()


async def sync_subscriptions(rt: EventGateRuntime, *, now: datetime | None = None) -> None:
    """One pass: subscribe every young mint not yet watched, drop the rest.
    Capped at ``config.max_mints`` — the newest mints win (``young_mints``
    already orders newest first), the rest waits for a slot to free up."""
    now = now or utcnow()
    wanted = {
        t.mint: t
        for t in young_mints(
            rt.radar.tracker,
            now,
            max_age_s=rt.radar.config.fast_lane_max_age_s,
            pinned_max_age_s=rt.radar.config.fast_lane_pinned_max_age_s,
        )
    }
    for mint in [m for m in rt.subs if m not in wanted]:
        await _unsubscribe_mint(rt, mint)
    for tracked in wanted.values():
        if tracked.mint in rt.subs:
            continue
        if len(rt.subs) >= rt.config.max_mints:
            break
        await _subscribe_mint(rt, tracked.mint, first_seen_at=tracked.first_seen_at)
    rt.stats.subscriptions = len(rt.subs)
    keep = frozenset(wanted)
    if rt.lab.caches is not None:
        prune_event_gate_caches(rt.lab.caches, keep=keep, now=now, max_mints=rt.config.max_mints)
    rt.debouncer.prune(keep=keep, now_s=time.monotonic(), max_age_s=MAX_CACHE_AGE_S)
