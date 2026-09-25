"""``--enable``/``--disable``/``--set-mint`` writes — split out of
``spot_desk_markets.py`` for the 350-line budget: T4.93's "Obsidian primeiro"
note gate (:mod:`obsidian_note_gate`) pushed it over. ``audit`` is also used
by ``spot_desk_markets.py``'s own ``--sell-now``, which needs no note (T4.93
scopes the gate to ``--enable``/``--disable``/``--set-mint`` only).

The gate runs right before the one write each act performs — after the
``market_missing``/"nothing to do" checks, never before them, so a refusal
for an unrelated reason or a plain no-op needs no note at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import obsidian_note_gate
from meme_ops_db import record_event
from spot_desk_markets_plan import COMPONENT, MarketRow, Refused, require_note
from sqlalchemy import text

__all__ = ["Connection", "audit", "set_enabled", "set_mint"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


_MARKET_BY_SYMBOL = text(
    "SELECT binance_symbol, mint, kind, tier, round_trip_cost_pct_at_seed, enabled "
    "FROM spot_desk_markets WHERE binance_symbol = :symbol"
)
_SET_ENABLED = text(
    "UPDATE spot_desk_markets SET enabled = :enabled, updated_at = now(), updated_by = :actor "
    "WHERE binance_symbol = :symbol RETURNING binance_symbol"
)
_SET_MINT = text(
    "UPDATE spot_desk_markets SET mint = :mint, updated_at = now(), updated_by = :actor "
    "WHERE binance_symbol = :symbol RETURNING binance_symbol"
)


async def _market(conn: Connection, symbol: str) -> MarketRow:
    rows = (await conn.execute(_MARKET_BY_SYMBOL, {"symbol": symbol})).mappings()
    for row in rows:
        return MarketRow.from_mapping(dict(row))
    raise Refused("market_missing", symbol)


async def audit(conn: Connection, event: str, message: str, data: dict[str, Any]) -> None:
    await record_event(
        conn, component=COMPONENT, level="info", event=event, message=message, data=data
    )


async def set_enabled(
    conn: Connection,
    symbol: str,
    enabled: bool,
    *,
    apply: bool,
    actor: str,
    reason: str,
    note: str | None = None,
    repo_root: Path | None = None,
) -> tuple[int, str]:
    row = await _market(conn, symbol)
    verb, label = ("enable", "enabled") if enabled else ("disable", "disabled")
    if row.enabled == enabled:
        return 0, f"{symbol} is already {label}; nothing to do"
    plan = f"{verb} {symbol} (was {'enabled' if row.enabled else 'disabled'})\nreason: {reason}"
    if not apply:
        hint = obsidian_note_gate.describe_required_note([[symbol]])
        return 0, plan + f"\ndry-run: nothing written (add --apply); {hint}"
    proof = require_note(note, [[symbol]], repo_root=repo_root)
    written = (
        (await conn.execute(_SET_ENABLED, {"symbol": symbol, "enabled": enabled, "actor": actor}))
        .scalars()
        .all()
    )
    if not written:
        raise Refused("market_missing", f"{symbol} moved under us")
    await audit(
        conn,
        f"{verb}d",
        f"{symbol} {verb}d by {actor}; reason: {reason}",
        {
            "symbol": symbol,
            "enabled": enabled,
            "actor": actor,
            **obsidian_note_gate.provenance_data(proof),
        },
    )
    return 0, plan + "\napplied: updated; system_events written"


async def set_mint(
    conn: Connection,
    symbol: str,
    mint: str,
    *,
    apply: bool,
    actor: str,
    reason: str,
    note: str | None = None,
    repo_root: Path | None = None,
) -> tuple[int, str]:
    row = await _market(conn, symbol)
    if row.mint == mint:
        return 0, f"{symbol} already maps to {mint}; nothing to do"
    plan = f"set-mint {symbol}: {row.mint} -> {mint}\nreason: {reason}"
    if not apply:
        hint = obsidian_note_gate.describe_required_note([[symbol]])
        return 0, plan + f"\ndry-run: nothing written (add --apply); {hint}"
    proof = require_note(note, [[symbol]], repo_root=repo_root)
    written = (
        (await conn.execute(_SET_MINT, {"symbol": symbol, "mint": mint, "actor": actor}))
        .scalars()
        .all()
    )
    if not written:
        raise Refused("market_missing", f"{symbol} moved under us")
    await audit(
        conn,
        "mint_changed",
        f"{symbol} mint changed {row.mint} -> {mint} by {actor}; reason: {reason}",
        {
            "symbol": symbol,
            "old_mint": row.mint,
            "new_mint": mint,
            "actor": actor,
            **obsidian_note_gate.provenance_data(proof),
        },
    )
    return 0, plan + "\napplied: updated; system_events written"
