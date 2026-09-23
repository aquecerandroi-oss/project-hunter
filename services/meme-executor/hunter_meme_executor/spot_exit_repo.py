"""T4.74-5 — the reads and writes the ``spot/1`` exits and the reconcile need
beyond ``spot_repo``: how many sells a position already has (the attempt
counter survives a restart in the rows, not in memory), the pending-exit
marker on an open position (``exit_order_id`` + ``exit_intent`` while a sell
is ``submitted_unconfirmed``), the ``submitted_unconfirmed`` rows the
reconcile settles by signature, one open position by id, and the count of
enabled markets the heartbeat publishes.

``hunter_worker``, SQL ``text()`` bound by name, one statement per call,
every read limited — the ``spot_repo`` rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_meme_executor.spot_repo_positions import SpotPosition, spot_position_from_row

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "TRANSIENT_EXIT_REFUSALS",
    "SellAttempts",
    "SpotOrderRow",
    "abandoned_orders",
    "clear_exit_pending",
    "confirmed_buys_without_position",
    "confirmed_sells_still_pending",
    "enabled_market_count",
    "fail_abandoned",
    "open_position_by_id",
    "pending_exits_on_terminal_orders",
    "sell_attempts",
    "set_exit_pending",
    "unconfirmed_spot_orders",
]

PENDING_EXIT_STATUS = "submitted_unconfirmed"
"""``exit_intent.status`` while a sell is on the chain and not yet settled."""
TRANSIENT_EXIT_REFUSALS: tuple[str, ...] = (
    "quote_failed:",
    "swap_build_failed:",
    "simulation_unreadable:",
    "signer_failed:",
)
"""Refusal prefixes of ``spot_leg`` that mean "Jupiter/RPC did not answer", not
"this sell cannot be built": they back off and are retried, and they do
**not** spend the ``MAX_EXIT_ATTEMPTS`` budget that blocks a position (Astra,
T4.74-5 review: a 2 min Jupiter outage must not park a stop for ever).
``signer_failed:`` joined them in T4.86 (Astra, review of that diff) for the
same reason: a signer out of service says nothing about *this* trade, and six
of its refusals would leave the position in ``blocked_exits`` — never sold by
the loop again, not even on ``emergency`` — after the key came back. It stays
named, backed off and visible as ``stuck_exits`` at the 30th in a row.
The literal list is repeated in ``_SELL_ATTEMPTS`` — keep the two in step."""


@dataclass(frozen=True, slots=True)
class SellAttempts:
    attempts: int
    """Every sell row of the position — the next attempt number."""
    hard_failures: int
    """Rows refused/failed for a non-transient reason — what blocks the position."""


@dataclass(frozen=True, slots=True)
class SpotOrderRow:
    id: str
    side: str
    status: str
    signal_id: str
    position_id: str | None
    market_symbol: str
    mint: str
    signature: str
    last_valid_block_height: int | None
    submitted_at: datetime
    intent: dict[str, Any]
    admission: dict[str, Any]
    quote: dict[str, Any] | None
    fill: dict[str, Any] | None


_SELL_ATTEMPTS = text(
    "SELECT count(*) AS n, "
    "  count(*) FILTER (WHERE status IN ('refused', 'failed') "
    "    AND reason NOT LIKE 'quote_failed:%' AND reason NOT LIKE 'swap_build_failed:%' "
    "    AND reason NOT LIKE 'simulation_unreadable:%' "
    "    AND reason NOT LIKE 'signer_failed:%') AS hard "
    "FROM spot_orders WHERE side = 'sell' AND position_id = :position_id"
)
_SET_EXIT_PENDING = text(
    "UPDATE spot_positions SET exit_order_id = :order_id, "
    "  exit_intent = CAST(:intent AS jsonb), updated_at = :now "
    "WHERE id = :id AND status = 'open' RETURNING id"
)
_CLEAR_EXIT_PENDING = text(
    "UPDATE spot_positions SET exit_order_id = NULL, "
    "  exit_intent = CAST(:intent AS jsonb), updated_at = :now "
    "WHERE id = :id AND status = 'open' AND exit_order_id = :order_id RETURNING id"
)
_UNCONFIRMED = text(
    "SELECT o.id, o.side, o.status, o.signal_id, o.position_id, o.market_symbol, o.mint, "
    "  o.tx_signature, o.last_valid_block_height, o.submitted_at, o.intent, o.admission, "
    "  o.quote, o.fill FROM spot_orders o "
    "WHERE o.status = 'submitted_unconfirmed' AND o.tx_signature IS NOT NULL "
    "ORDER BY o.submitted_at LIMIT 50"
)
# The two orphans a crash between ``mark_confirmed`` and the position write leaves:
# a confirmed buy with no position (tokens in the wallet, reservation released,
# nobody managing them) and an open position whose pending sell already confirmed.
_BUYS_WITHOUT_POSITION = text(
    "SELECT o.id, o.side, o.status, o.signal_id, o.position_id, o.market_symbol, o.mint, "
    "  o.tx_signature, o.last_valid_block_height, o.submitted_at, o.intent, o.admission, "
    "  o.quote, o.fill FROM spot_orders o "
    "WHERE o.side = 'buy' AND o.status = 'confirmed' "
    "  AND NOT EXISTS (SELECT 1 FROM spot_positions p WHERE p.entry_order_id = o.id) "
    "ORDER BY o.settled_at LIMIT 20"
)
_SELLS_STILL_PENDING = text(
    "SELECT o.id, o.side, o.status, o.signal_id, o.position_id, o.market_symbol, o.mint, "
    "  o.tx_signature, o.last_valid_block_height, o.submitted_at, o.intent, o.admission, "
    "  o.quote, o.fill FROM spot_orders o "
    "JOIN spot_positions p ON p.exit_order_id = o.id AND p.status = 'open' "
    "WHERE o.side = 'sell' AND o.status = 'confirmed' ORDER BY o.settled_at LIMIT 20"
)
# A leg the process died inside: ``admitted``/``simulated`` and never signed
# (``signing_at IS NULL`` — the signature is written before the broadcast, so
# such a row was never sent). A buy there holds its reservation and its market
# for ever; a sell there pins its position's pending marker for ever.
_ABANDONED = text(
    "SELECT o.id, o.side, o.status, o.signal_id, o.position_id, o.market_symbol, o.mint, "
    "  o.tx_signature, o.last_valid_block_height, o.submitted_at, o.intent, o.admission, "
    "  o.quote, o.fill FROM spot_orders o "
    "WHERE o.status IN ('admitted', 'simulated') AND o.signing_at IS NULL "
    "  AND o.received_at < :before ORDER BY o.received_at LIMIT 20"
)
_FAIL_ABANDONED = text(
    "UPDATE spot_orders SET status = 'failed', reason = :reason, settled_at = :now, "
    "  updated_at = :now WHERE id = :id AND status IN ('admitted', 'simulated') "
    "  AND signing_at IS NULL RETURNING id"
)
# A crash between ``spot_leg`` writing ``refused``/``failed`` and the exits
# loop clearing the marker: the position still says a sell is in flight and
# would never be sold again.
_PENDING_ON_TERMINAL = text(
    "SELECT o.id, o.side, o.status, o.signal_id, o.position_id, o.market_symbol, o.mint, "
    "  o.tx_signature, o.last_valid_block_height, o.submitted_at, o.intent, o.admission, "
    "  o.quote, o.fill FROM spot_orders o "
    "JOIN spot_positions p ON p.exit_order_id = o.id AND p.status = 'open' "
    "WHERE o.side = 'sell' AND o.status IN ('refused', 'failed') "
    "ORDER BY o.settled_at LIMIT 20"
)
_OPEN_BY_ID = text(
    "SELECT id, signal_id, market_symbol, mint, entry_at, tokens, sol_spent_lamports, "
    "  initial_risk_sol, params, ata_rent_lamports, mark_sol, high_water_sol, exit_intent, "
    "  sell_requested_at, sell_requested_by "
    "FROM spot_positions WHERE id = :id AND status = 'open'"
)
_ENABLED_MARKETS = text("SELECT count(*) AS n FROM spot_desk_markets WHERE enabled")


async def sell_attempts(session: AsyncSession, position_id: str) -> SellAttempts:
    """Every sell row of the position (attempt ``n + 1`` is next) and how many of
    them failed for a reason that is not transient — both survive a restart."""
    r = (await session.execute(_SELL_ATTEMPTS, {"position_id": position_id})).mappings().one()
    return SellAttempts(int(r["n"] or 0), int(r.get("hard") or 0))


async def set_exit_pending(
    session: AsyncSession,
    position_id: str,
    *,
    order_id: str,
    reason: str,
    attempt: int,
    now: datetime,
) -> bool:
    """The position names its sell in flight: it stays ``open`` with
    ``exit_order_id`` set, and the exits loop sells nothing else until the leg
    or the reconcile settles that order."""
    intent = {
        "status": PENDING_EXIT_STATUS,
        "order_id": order_id,
        "reason": reason,
        "attempt": attempt,
        "decided_at": now.isoformat(),
    }
    params = {"id": position_id, "order_id": order_id, "intent": json.dumps(intent), "now": now}
    return (await session.execute(_SET_EXIT_PENDING, params)).scalar() is not None


async def clear_exit_pending(
    session: AsyncSession, position_id: str, *, order_id: str, outcome: str, now: datetime
) -> bool:
    """The pending sell did not land (errored or expired): the marker goes, the
    outcome stays written, and the exits loop may try again."""
    intent = {"status": outcome, "order_id": order_id, "settled_at": now.isoformat()}
    params = {"id": position_id, "order_id": order_id, "intent": json.dumps(intent), "now": now}
    return (await session.execute(_CLEAR_EXIT_PENDING, params)).scalar() is not None


def _order_row(r: Any) -> SpotOrderRow:
    height = r["last_valid_block_height"]
    return SpotOrderRow(
        id=str(r["id"]),
        side=str(r["side"]),
        status=str(r["status"]),
        signal_id=str(r["signal_id"]),
        position_id=None if r["position_id"] is None else str(r["position_id"]),
        market_symbol=str(r["market_symbol"]),
        mint=str(r["mint"]),
        signature=str(r["tx_signature"] or ""),
        last_valid_block_height=None if height is None else int(height),
        submitted_at=r["submitted_at"],
        intent=dict(r["intent"] or {}),
        admission=dict(r["admission"] or {}),
        quote=None if r["quote"] is None else dict(r["quote"]),
        fill=None if r["fill"] is None else dict(r["fill"]),
    )


async def unconfirmed_spot_orders(session: AsyncSession) -> list[SpotOrderRow]:
    return [_order_row(r) for r in (await session.execute(_UNCONFIRMED)).mappings()]


async def confirmed_buys_without_position(session: AsyncSession) -> list[SpotOrderRow]:
    """Confirmed buys nobody opened (a crash after ``mark_confirmed``): the
    reconcile opens them from the row's own fill and admission."""
    return [_order_row(r) for r in (await session.execute(_BUYS_WITHOUT_POSITION)).mappings()]


async def confirmed_sells_still_pending(session: AsyncSession) -> list[SpotOrderRow]:
    """Confirmed sells whose position is still ``open`` and names them as its
    pending exit: the reconcile closes it from the row's own fill."""
    return [_order_row(r) for r in (await session.execute(_SELLS_STILL_PENDING)).mappings()]


async def abandoned_orders(session: AsyncSession, *, before: datetime) -> list[SpotOrderRow]:
    """Rows admitted before ``before`` that were never signed — a process that died mid-leg."""
    return [
        _order_row(r) for r in (await session.execute(_ABANDONED, {"before": before})).mappings()
    ]


async def fail_abandoned(
    session: AsyncSession, order_id: str, *, reason: str, now: datetime
) -> bool:
    """Still unsigned at write time, or nothing happens (a leg that signed meanwhile keeps its row)."""
    params = {"id": order_id, "reason": reason, "now": now}
    return (await session.execute(_FAIL_ABANDONED, params)).scalar() is not None


async def pending_exits_on_terminal_orders(session: AsyncSession) -> list[SpotOrderRow]:
    """Sells refused/failed whose position still names them as in flight."""
    return [_order_row(r) for r in (await session.execute(_PENDING_ON_TERMINAL)).mappings()]


async def open_position_by_id(session: AsyncSession, position_id: str) -> SpotPosition | None:
    r = (await session.execute(_OPEN_BY_ID, {"id": position_id})).mappings().first()
    return None if r is None else spot_position_from_row(r)


async def enabled_market_count(session: AsyncSession) -> int:
    r = (await session.execute(_ENABLED_MARKETS)).mappings().one()
    return int(r["n"] or 0)
