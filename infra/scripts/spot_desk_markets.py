#!/usr/bin/env python3
"""Audited edits to the ``spot/1`` market map (T4.74-6, design
``docs/design/spot1-lab-solana.md`` §2) — the only sanctioned way to touch
``spot_desk_markets``/``spot_positions.sell_requested_*``; never a hand edit.

    uv run python infra/scripts/spot_desk_markets.py --list
    uv run python infra/scripts/spot_desk_markets.py --enable SUIUSDT \\
        --reason "R63 §5.5 revista: liquidez subiu" --apply
    uv run python infra/scripts/spot_desk_markets.py --disable WIFUSDT \\
        --reason "custo subiu acima de 0,4 %" --apply
    uv run python infra/scripts/spot_desk_markets.py --set-mint WIFUSDT <MINT> \\
        --reason "mint trocado pela Jupiter" --apply
    uv run python infra/scripts/spot_desk_markets.py --sell-now <POSITION_ID> \\
        --reason "Everton pediu para fechar na mão" --apply

Dry-run by default: prints the exact change, writes nothing. ``--apply``
writes and leaves one ``system_events`` row (component ``spot_desk``, actor
from ``--actor``, default ``"Everton"``) — the pattern of ``meme_rule_set.py``
(T4.16). Every write (``--enable``/``--disable``/``--set-mint``/``--sell-now``)
requires ``--reason`` of 10+ characters; ``--list`` needs none.

``--set-mint`` validates the new mint is 32-44 base58 characters
(``spot_desk_markets_plan.validate_mint``) before touching the database — it
does not resolve the mint on chain (the executor's own RPC read on the next
tick is what proves the mint exists and writes ``decimals`` back).
``--sell-now POSITION_ID`` sets ``spot_positions.sell_requested_at/by``; the
exit loop (T4.74-5, ``spot_exits.py``) reads it as the ``sell_requested`` exit
reason. A position that is not ``open`` refuses ``position_not_open`` — a
closed position has nothing left to sell.

Refusals, by name and nothing written: ``reason_required``, ``market_missing``,
``invalid_mint``, ``position_missing``, ``position_not_open``. No act (or more
than one) on the command line is a usage error, not a refusal.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
every other ops script here. Exit codes: 0 done (or a clean dry-run/nothing to
do), 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from meme_ops_db import migration_url, record_event
from spot_desk_markets_plan import (
    COMPONENT,
    MarketRow,
    Refused,
    format_table,
    require_reason,
    validate_mint,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "list_markets", "main", "parse_args", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


_MARKETS = text(
    "SELECT binance_symbol, mint, kind, tier, round_trip_cost_pct_at_seed, enabled "
    "FROM spot_desk_markets ORDER BY binance_symbol"
)
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
_POSITION_STATUS = text("SELECT id, status FROM spot_positions WHERE id = CAST(:id AS uuid)")
_SELL_NOW = text(
    "UPDATE spot_positions SET sell_requested_at = now(), sell_requested_by = :actor "
    "WHERE id = CAST(:id AS uuid) AND status = 'open' RETURNING id"
)


async def list_markets(conn: Connection) -> list[MarketRow]:
    rows = (await conn.execute(_MARKETS)).mappings()
    return [MarketRow.from_mapping(dict(r)) for r in rows]


async def _market(conn: Connection, symbol: str) -> MarketRow:
    rows = (await conn.execute(_MARKET_BY_SYMBOL, {"symbol": symbol})).mappings()
    for row in rows:
        return MarketRow.from_mapping(dict(row))
    raise Refused("market_missing", symbol)


async def _audit(conn: Connection, event: str, message: str, data: Mapping[str, Any]) -> None:
    await record_event(
        conn, component=COMPONENT, level="info", event=event, message=message, data=data
    )


async def _set_enabled(
    conn: Connection, symbol: str, enabled: bool, *, apply: bool, actor: str, reason: str
) -> tuple[int, str]:
    row = await _market(conn, symbol)
    verb, label = ("enable", "enabled") if enabled else ("disable", "disabled")
    if row.enabled == enabled:
        return 0, f"{symbol} is already {label}; nothing to do"
    plan = f"{verb} {symbol} (was {'enabled' if row.enabled else 'disabled'})\nreason: {reason}"
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    written = (
        (await conn.execute(_SET_ENABLED, {"symbol": symbol, "enabled": enabled, "actor": actor}))
        .scalars()
        .all()
    )
    if not written:
        raise Refused("market_missing", f"{symbol} moved under us")
    await _audit(
        conn,
        f"{verb}d",
        f"{symbol} {verb}d by {actor}; reason: {reason}",
        {"symbol": symbol, "enabled": enabled, "actor": actor},
    )
    return 0, plan + "\napplied: updated; system_events written"


async def _set_mint(
    conn: Connection, symbol: str, mint: str, *, apply: bool, actor: str, reason: str
) -> tuple[int, str]:
    row = await _market(conn, symbol)
    if row.mint == mint:
        return 0, f"{symbol} already maps to {mint}; nothing to do"
    plan = f"set-mint {symbol}: {row.mint} -> {mint}\nreason: {reason}"
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    written = (
        (await conn.execute(_SET_MINT, {"symbol": symbol, "mint": mint, "actor": actor}))
        .scalars()
        .all()
    )
    if not written:
        raise Refused("market_missing", f"{symbol} moved under us")
    await _audit(
        conn,
        "mint_changed",
        f"{symbol} mint changed {row.mint} -> {mint} by {actor}; reason: {reason}",
        {"symbol": symbol, "old_mint": row.mint, "new_mint": mint, "actor": actor},
    )
    return 0, plan + "\napplied: updated; system_events written"


async def _sell_now(
    conn: Connection, position_id: str, *, apply: bool, actor: str, reason: str
) -> tuple[int, str]:
    rows = (await conn.execute(_POSITION_STATUS, {"id": position_id})).mappings()
    row = next(iter(rows), None)
    if row is None:
        raise Refused("position_missing", position_id)
    status = str(row["status"])
    if status != "open":
        raise Refused("position_not_open", f"{position_id} is {status}")
    plan = f"sell-now {position_id} (status open)\nreason: {reason}"
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    written = (await conn.execute(_SELL_NOW, {"id": position_id, "actor": actor})).scalars().all()
    if not written:
        raise Refused("position_not_open", f"{position_id} moved under us")
    await _audit(
        conn,
        "sell_requested",
        f"sell requested for {position_id} by {actor}; reason: {reason}",
        {"position_id": position_id, "actor": actor},
    )
    return 0, plan + "\napplied: sell_requested_at set; system_events written"


async def run(
    conn: Connection,
    *,
    enable: str | None = None,
    disable: str | None = None,
    set_mint: tuple[str, str] | None = None,
    sell_now: str | None = None,
    apply: bool = False,
    reason: str | None = None,
    actor: str = "Everton",
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``--apply`` and a reason."""
    if enable is None and disable is None and set_mint is None and sell_now is None:
        return 0, format_table(await list_markets(conn))
    checked_reason = require_reason(reason)
    if enable is not None:
        return await _set_enabled(
            conn, enable, True, apply=apply, actor=actor, reason=checked_reason
        )
    if disable is not None:
        return await _set_enabled(
            conn, disable, False, apply=apply, actor=actor, reason=checked_reason
        )
    if set_mint is not None:
        symbol, mint = set_mint
        return await _set_mint(
            conn, symbol, validate_mint(mint), apply=apply, actor=actor, reason=checked_reason
        )
    assert sell_now is not None
    return await _sell_now(conn, sell_now, apply=apply, actor=actor, reason=checked_reason)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],  # type: ignore[union-attr]
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--enable", metavar="SYMBOL", default=None)
    parser.add_argument("--disable", metavar="SYMBOL", default=None)
    parser.add_argument(
        "--set-mint", dest="set_mint", nargs=2, metavar=("SYMBOL", "MINT"), default=None
    )
    parser.add_argument("--sell-now", dest="sell_now", metavar="POSITION_ID", default=None)
    parser.add_argument("--reason", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor", default="Everton")
    args = parser.parse_args(argv)
    acts = [args.enable, args.disable, args.set_mint, args.sell_now]
    if not args.list and not any(acts):
        parser.error("one of --list, --enable, --disable, --set-mint or --sell-now is required")
    if sum(1 for a in acts if a is not None) > 1:
        parser.error("--enable/--disable/--set-mint/--sell-now are acts; run one at a time")
    return args


async def _main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(
                    conn,
                    enable=args.enable,
                    disable=args.disable,
                    set_mint=tuple(args.set_mint) if args.set_mint else None,
                    sell_now=args.sell_now,
                    apply=args.apply,
                    reason=args.reason,
                    actor=args.actor,
                )
            except Refused as refused:
                print(f"refused: {refused}", file=sys.stderr)
                return EX_REFUSED
        print(report)
        return code
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
