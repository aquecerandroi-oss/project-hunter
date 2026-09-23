"""T4.74-3 — the ``spot/1`` lane's reads and writes of ``spot_orders`` and
``spot_desk_markets`` (``0057``) plus the one query that finds a Lab signal to
buy (design §2). The positions live in ``spot_repo_positions.py`` and are
re-exported here, so callers import one place.

``hunter_worker``, SQL ``text()`` bound by name, every read limited; one
statement per call so the caller (``spot_leg``, T4.74-4) commits **one step
per transaction** — the T4.73b rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_meme_executor.spot_repo_positions import (
    ClosedStats,
    SpotPosition,
    close_position,
    closed_stats,
    insert_position,
    open_spot_positions,
    set_mark,
    spot_position_from_row,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ClosedStats",
    "PendingSpotIntent",
    "SpotCandidate",
    "SpotPosition",
    "candidate_from_row",
    "candidate_signals",
    "close_position",
    "closed_stats",
    "insert_order",
    "insert_position",
    "mark_confirmed",
    "mark_failed",
    "mark_refused",
    "mark_simulated",
    "mark_submitted",
    "market_decimals",
    "open_spot_positions",
    "pending_spot_markets",
    "set_mark",
    "set_market_decimals",
    "spot_position_from_row",
]

SPOT_STRATEGY_KEY = "mean_reversion"
"""``strategies.key`` of the only strategy the desk operates — the literal in ``_CANDIDATES``."""
DECIMALS_WRITER = "executor:spot1"
"""``spot_desk_markets.updated_by`` of the decimals write-back — the literal in ``_SET_DECIMALS``."""


@dataclass(frozen=True, slots=True)
class SpotCandidate:
    signal_id: str
    market_id: str
    market_symbol: str
    exchange_id: str
    market_type: str
    emitted_at: datetime
    expires_at: datetime
    reference_price: Decimal | None
    stop: Decimal | None
    target1: Decimal | None
    expected_holding_s: int | None
    mint: str
    units_per_binance_unit: Decimal
    decimals: int | None
    kind: str
    tier: str


@dataclass(frozen=True, slots=True)
class PendingSpotIntent:
    signal_id: str
    market_symbol: str
    mint: str
    reserved_sol: Decimal


# The features envelope is a *list* of ``{name, value}`` (``SupportingFeatures``),
# not an object — hence the lateral pick instead of ``->'features'->>'close_15m'``.
# The map is keyed by the **Binance** symbol, so the exchange is named (Astra: a
# homonym on another exchange would otherwise become a candidate); ``emitted_at
# <= :now`` keeps a replay over an already-updated table from seeing the future.
_CANDIDATES = text(
    "SELECT s.id, s.market_id, m.symbol AS market_symbol, m.exchange_id, m.market_type, "
    "  s.emitted_at, s.expires_at, s.stop, s.targets->>0 AS target1, s.expected_holding_s, "
    "  coalesce(o.meta->>'reference_price', "
    "    (SELECT f->>'value' FROM jsonb_array_elements(s.supporting_features->'features') f "
    "     WHERE f->>'name' = 'close_15m' LIMIT 1)) AS reference_price, "
    "  d.mint, d.units_per_binance_unit, d.decimals, d.kind, d.tier "
    "FROM agent_signals s "
    "JOIN strategy_versions v ON v.id = s.strategy_version_id "
    "JOIN strategies st ON st.id = v.strategy_id "
    "JOIN markets m ON m.id = s.market_id "
    "JOIN exchanges e ON e.id = m.exchange_id AND e.code = 'binance' "
    "JOIN spot_desk_markets d ON d.binance_symbol = m.symbol AND d.enabled "
    "LEFT JOIN signal_outcomes o ON o.signal_id = s.id "
    "WHERE st.key = 'mean_reversion' AND v.version = :version "
    "  AND s.direction = 'long' AND s.status = 'active' "
    "  AND s.emitted_at >= :since AND s.emitted_at <= :now AND s.expires_at > :now "
    "  AND NOT EXISTS (SELECT 1 FROM spot_orders so WHERE so.signal_id = s.id AND so.side = 'buy') "
    "ORDER BY s.emitted_at DESC LIMIT :limit"
)
_INSERT_ORDER = text(
    "INSERT INTO spot_orders (id, signal_id, position_id, market_symbol, mint, side, "
    "  client_order_id, attempt, quote, intent, admission, status, reason, received_at, "
    "  admitted_at, updated_at) "
    "VALUES (:id, :signal_id, :position_id, :market_symbol, :mint, :side, :client_order_id, "
    "  :attempt, CAST(:quote AS jsonb), CAST(:intent AS jsonb), CAST(:admission AS jsonb), "
    "  :status, :reason, :now, CASE WHEN :status = 'admitted' THEN CAST(:now AS timestamptz) END, "
    "  :now) ON CONFLICT (client_order_id) DO NOTHING RETURNING id"
)
_SIMULATED = text(
    "UPDATE spot_orders SET status = 'simulated', simulated_at = :now, updated_at = :now "
    "WHERE id = :id AND status = 'admitted' RETURNING id"
)
_SUBMITTED = text(
    "UPDATE spot_orders SET status = 'submitted_unconfirmed', tx_signature = :signature, "
    "  signatures = signatures || CAST(:signature_json AS jsonb), "
    "  last_valid_block_height = :last_valid_block_height, signing_at = :now, "
    "  submitted_at = :now, updated_at = :now "
    "WHERE id = :id AND status IN ('admitted', 'simulated') RETURNING id"
)
_CONFIRMED = text(
    "UPDATE spot_orders SET status = 'confirmed', fill = CAST(:fill AS jsonb), "
    "  settled_at = :now, updated_at = :now "
    "WHERE id = :id AND status = 'submitted_unconfirmed' RETURNING id"
)
_FAILED = text(
    "UPDATE spot_orders SET status = 'failed', reason = :reason, settled_at = :now, "
    "  updated_at = :now WHERE id = :id AND status <> 'confirmed' RETURNING id"
)
_REFUSED = text(
    "UPDATE spot_orders SET status = 'refused', reason = :reason, settled_at = :now, "
    "  updated_at = :now WHERE id = :id AND status IN ('admitted', 'simulated') "
    "  AND signing_at IS NULL RETURNING id"
)
"""T4.86 — the same set ``_FAIL_ABANDONED`` rescues: an order that never left
this process. ``spot_leg`` marks ``simulated`` **before** it signs, so the
signer's own refusal (``signer_failed:<type>``) lands on a ``simulated`` row;
with ``status = 'admitted'`` alone it updated zero rows and the order stayed
``simulated`` — reservation held — while the caller was told it was refused.
``signing_at IS NULL`` is the guard that matters: a row that was signed is
settled by its signature, never refused."""
_PENDING = text(
    "SELECT signal_id, market_symbol, mint, intent FROM spot_orders "
    "WHERE side = 'buy' AND status IN ('admitted', 'simulated', 'submitted_unconfirmed') "
    "ORDER BY received_at LIMIT 100"
)
_DECIMALS = text("SELECT decimals FROM spot_desk_markets WHERE binance_symbol = :symbol")
_SET_DECIMALS = text(
    "UPDATE spot_desk_markets SET decimals = :decimals, updated_at = :now, "
    "  updated_by = 'executor:spot1' "
    "WHERE binance_symbol = :symbol AND decimals IS NULL RETURNING binance_symbol"
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None or value == "" else Decimal(str(value))


def candidate_from_row(r: Any) -> SpotCandidate:
    holding = r["expected_holding_s"]
    return SpotCandidate(
        signal_id=str(r["id"]),
        market_id=str(r["market_id"]),
        market_symbol=str(r["market_symbol"]),
        exchange_id=str(r["exchange_id"]),
        market_type=str(r["market_type"]),
        emitted_at=r["emitted_at"],
        expires_at=r["expires_at"],
        reference_price=_decimal(r["reference_price"]),
        stop=_decimal(r["stop"]),
        target1=_decimal(r["target1"]),
        expected_holding_s=None if holding is None else int(holding),
        mint=str(r["mint"]),
        units_per_binance_unit=Decimal(str(r["units_per_binance_unit"])),
        decimals=None if r["decimals"] is None else int(r["decimals"]),
        kind=str(r["kind"]),
        tier=str(r["tier"]),
    )


async def candidate_signals(
    session: AsyncSession, *, version: str, max_age_s: int, now: datetime, limit: int
) -> list[SpotCandidate]:
    """Design §2, newest first; the caller buys **at most one** per tick."""
    params = {"version": version, "since": now - timedelta(seconds=max_age_s), "now": now}
    rows = (await session.execute(_CANDIDATES, {**params, "limit": limit})).mappings()
    return [candidate_from_row(r) for r in rows]


async def insert_order(
    session: AsyncSession,
    *,
    signal_id: str,
    market_symbol: str,
    mint: str,
    side: str,
    client_order_id: str,
    attempt: int,
    status: str,
    reason: str | None,
    intent: dict[str, Any],
    admission: dict[str, Any],
    quote: dict[str, Any] | None,
    position_id: str | None = None,
    now: datetime,
) -> str | None:
    """``None`` when the key already exists (idempotent); a sell names its position."""
    order_id = str(uuid7())
    inserted = await session.execute(
        _INSERT_ORDER,
        {
            "id": order_id,
            "signal_id": signal_id,
            "position_id": position_id,
            "market_symbol": market_symbol,
            "mint": mint,
            "side": side,
            "client_order_id": client_order_id,
            "attempt": attempt,
            "quote": None if quote is None else json.dumps(quote, default=str),
            "intent": json.dumps(intent, default=str),
            "admission": json.dumps(admission, default=str),
            "status": status,
            "reason": reason,
            "now": now,
        },
    )
    return None if inserted.scalar() is None else order_id


async def _step(session: AsyncSession, statement: Any, params: dict[str, Any]) -> bool:
    return (await session.execute(statement, params)).scalar() is not None


async def mark_simulated(session: AsyncSession, order_id: str, *, now: datetime) -> bool:
    return await _step(session, _SIMULATED, {"id": order_id, "now": now})


async def mark_submitted(
    session: AsyncSession,
    order_id: str,
    *,
    signature: str,
    last_valid_block_height: int | None,
    now: datetime,
) -> bool:
    """The signature is written **before** the broadcast (T4.73b). The row then
    stays ``submitted_unconfirmed`` — a send that raises is ambiguous (the RPC
    may have relayed it) — and ``spot_reconcile`` settles it by signature; only
    ``SendDisabled`` (never relayed by construction) is ``failed``."""
    params = {
        "id": order_id,
        "signature": signature,
        "signature_json": json.dumps([signature]),
        "last_valid_block_height": last_valid_block_height,
        "now": now,
    }
    return await _step(session, _SUBMITTED, params)


async def mark_confirmed(
    session: AsyncSession, order_id: str, *, fill: dict[str, Any], now: datetime
) -> bool:
    """``fill`` = the chain's deltas (lamports and atoms, before/after), never the quote."""
    payload = {"id": order_id, "fill": json.dumps(fill, default=str), "now": now}
    return await _step(session, _CONFIRMED, payload)


async def mark_failed(session: AsyncSession, order_id: str, *, reason: str, now: datetime) -> bool:
    return await _step(session, _FAILED, {"id": order_id, "reason": reason, "now": now})


async def mark_refused(session: AsyncSession, order_id: str, *, reason: str, now: datetime) -> bool:
    return await _step(session, _REFUSED, {"id": order_id, "reason": reason, "now": now})


async def pending_spot_markets(session: AsyncSession) -> list[PendingSpotIntent]:
    """Buys in flight — each reserves its ``intent.max_sol_cost_sol`` (engine §9.5)."""
    out: list[PendingSpotIntent] = []
    for r in (await session.execute(_PENDING)).mappings():
        reserved = _decimal(dict(r["intent"] or {}).get("max_sol_cost_sol")) or Decimal(0)
        if reserved > 0:
            out.append(
                PendingSpotIntent(
                    str(r["signal_id"]), str(r["market_symbol"]), str(r["mint"]), reserved
                )
            )
    return out


async def market_decimals(session: AsyncSession, symbol: str) -> int | None:
    r = (await session.execute(_DECIMALS, {"symbol": symbol})).mappings().first()
    return None if r is None or r["decimals"] is None else int(r["decimals"])


async def set_market_decimals(
    session: AsyncSession, symbol: str, decimals: int, *, now: datetime
) -> bool:
    """The mint's scale read once by RPC, written back only while the map has none."""
    payload = {"symbol": symbol, "decimals": decimals, "now": now}
    return await _step(session, _SET_DECIMALS, payload)
