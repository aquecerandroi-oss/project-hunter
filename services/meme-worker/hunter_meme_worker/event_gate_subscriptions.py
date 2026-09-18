"""Keep the WS subscriptions equal to the tracked set the fast lane already
names (T4.52b-3, plan-T4.52b.md §4): no new query, the exact
:func:`~hunter_meme_worker.fast_lane.young_mints` a mint has to be in for the
15-second series to fold it at all.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import ExchangeUnavailable
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_meme_worker.event_gate_runtime import Subscription
from hunter_meme_worker.fast_lane import young_mints

if TYPE_CHECKING:
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime

__all__ = ["sync_subscriptions"]


async def _subscribe_mint(rt: EventGateRuntime, mint: str, *, first_seen_at: datetime) -> None:
    pda = bonding_curve_address(mint)
    try:
        logs_id = await rt.ws.subscribe_logs(mentions=[pda], commitment=rt.config.commitment)
        account_id = await rt.ws.subscribe_account(pda, commitment=rt.config.commitment)
    except ExchangeUnavailable:
        return
    rt.subs[mint] = Subscription(logs_id, account_id, first_seen_at)
    rt.subs_by_logical[logs_id] = mint
    rt.subs_by_logical[account_id] = mint
    rt.book.touch(mint, at=utcnow(), first_seen_at=first_seen_at)


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
