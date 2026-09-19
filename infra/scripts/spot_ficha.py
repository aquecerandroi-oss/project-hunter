#!/usr/bin/env python3
"""One ``spot/1`` position, as a Markdown ficha for the vault (T4.74-6, design
``docs/design/spot1-lab-solana.md`` §7). Everton, 18/09/2026: every real buy
gets a ficha the same day.

    uv run python infra/scripts/spot_ficha.py --position <POSITION_ID>            # dry-run: prints the Markdown
    uv run python infra/scripts/spot_ficha.py --position <POSITION_ID> --write    # writes the ficha + the scoreboard line

Dry-run (default) only reads: the signal's geometry, the entry/exit quotes,
both order signatures, the parity check at entry, SOL/USD at entry and exit,
cost in R, R gross/net (``pnl_sol``/``r_multiple``) and an empty "lição"
field for Everton to fill by hand — printed, nothing written. ``--write``
creates ``obsidian/03-TRADING/Spot/Ficha-<AAAA-MM-DD>-<SÍMBOLO>-<id8>.md`` and
appends one line to ``obsidian/03-TRADING/Spot/Mesa-spot-1.md``, guarded by
the marker ``<!-- <id8> -->`` — a second ``--write`` on the same position
changes nothing on the scoreboard (the ficha file itself is re-rendered in
full, same as ``obsidian_marker_writer``'s regenerated head).

A field the row does not carry (an order not yet sent, a position still
open, an entry admission without a ``cost_r`` check) prints
``indisponível`` — never a fabricated number.

Refusals, by name and nothing written: ``position_missing``.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), read
only — this script never writes a database row. Exit codes: 0 done (or a
clean dry-run), 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from meme_ops_db import migration_url
from spot_ficha_render import (
    OrderView,
    PositionView,
    ficha_filename,
    position_id8,
    render_ficha,
    scoreboard_line,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SPOT_DIR = REPO_ROOT / "obsidian" / "03-TRADING" / "Spot"
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "load_position", "main", "parse_args", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_POSITION = text(
    "SELECT p.id::text AS id, p.market_symbol, p.mint, p.status, p.entry_at, p.entry, p.tokens, "
    "p.sol_spent_lamports, p.initial_risk_sol, p.params, p.ata_rent_lamports, p.mark_sol, "
    "p.mark_reason, p.exit_at, p.exit, p.sol_received_lamports, p.pnl_sol, p.r_multiple, "
    "p.entry_order_id::text AS entry_order_id, p.exit_order_id::text AS exit_order_id, "
    "m.base, m.kind "
    "FROM spot_positions p JOIN spot_desk_markets m ON m.binance_symbol = p.market_symbol "
    "WHERE p.id = CAST(:id AS uuid)"
)
_ORDER = text(
    "SELECT side, status, tx_signature, admission FROM spot_orders WHERE id = CAST(:id AS uuid)"
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def _order(conn: Connection, order_id: str | None) -> OrderView | None:
    if order_id is None:
        return None
    rows = (await conn.execute(_ORDER, {"id": order_id})).mappings()
    row = next(iter(rows), None)
    if row is None:
        return None
    return OrderView(
        side=str(row["side"]),
        status=str(row["status"]),
        tx_signature=row["tx_signature"],
        admission=dict(row["admission"] or {}),
    )


async def load_position(conn: Connection, position_id: str) -> PositionView:
    rows = (await conn.execute(_POSITION, {"id": position_id})).mappings()
    row = next(iter(rows), None)
    if row is None:
        raise Refused("position_missing", position_id)
    entry_order = await _order(conn, row["entry_order_id"])
    exit_order = await _order(conn, row["exit_order_id"])
    return PositionView(
        id=str(row["id"]),
        market_symbol=str(row["market_symbol"]),
        mint=str(row["mint"]),
        base=str(row["base"]),
        kind=str(row["kind"]),
        status=str(row["status"]),
        entry_at=row["entry_at"],
        entry=dict(row["entry"] or {}),
        tokens=int(row["tokens"]),
        sol_spent_lamports=int(row["sol_spent_lamports"]),
        initial_risk_sol=Decimal(str(row["initial_risk_sol"])),
        params=dict(row["params"] or {}),
        ata_rent_lamports=int(row["ata_rent_lamports"]),
        mark_sol=_decimal(row["mark_sol"]),
        mark_reason=row["mark_reason"],
        exit_at=row["exit_at"],
        exit=dict(row["exit"]) if row["exit"] else None,
        sol_received_lamports=row["sol_received_lamports"],
        pnl_sol=_decimal(row["pnl_sol"]),
        r_multiple=_decimal(row["r_multiple"]),
        entry_order=entry_order,
        exit_order=exit_order,
    )


def _append_scoreboard(view: PositionView, board: Path) -> bool:
    """Appends the row plus its marker line, unless the marker is already in
    the file — the idempotency the design's §7 promises. Returns whether it wrote."""
    marker = f"<!-- {position_id8(view.id)} -->"
    existing = board.read_text(encoding="utf-8") if board.exists() else ""
    if marker in existing:
        return False
    updated = existing if existing == "" or existing.endswith("\n") else existing + "\n"
    updated += scoreboard_line(view) + "\n"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(updated, encoding="utf-8")
    return True


def _write_ficha(ficha_path: Path, ficha_md: str) -> None:
    """File IO lives outside the event loop (ASYNC240)."""
    ficha_path.parent.mkdir(parents=True, exist_ok=True)
    ficha_path.write_text(ficha_md, encoding="utf-8")


async def run(
    conn: Connection, *, position_id: str, write: bool, spot_dir: Path = SPOT_DIR
) -> tuple[int, str]:
    view = await load_position(conn, position_id)
    ficha_md = render_ficha(view)
    ficha_path = spot_dir / ficha_filename(view)
    if not write:
        return 0, ficha_md + f"\ndry-run: nothing written (add --write); path would be {ficha_path}"
    _write_ficha(ficha_path, ficha_md)
    wrote_board = _append_scoreboard(view, spot_dir / "Mesa-spot-1.md")
    board_note = (
        "scoreboard line appended"
        if wrote_board
        else "scoreboard already had this position (idempotent)"
    )
    return 0, f"applied: wrote {ficha_path}; {board_note}"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],  # type: ignore[union-attr]
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--position", required=True, metavar="POSITION_ID")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


async def _main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            try:
                code, report = await run(conn, position_id=args.position, write=args.write)
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
