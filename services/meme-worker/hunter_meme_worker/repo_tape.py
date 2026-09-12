"""The tape half of the T4.2c repository: ``swap-api`` trades into ``meme_trades``
and the two reads the fold and the prioritiser make — as ``hunter_worker``,
never as owner (``repo.py``'s discipline). Split from ``repo_boards.py`` for the
350-line budget.

**What a ``swap-api`` row does not say stays NULL** (``.claude/state/notes-T4.2.md``
§contrato, amendment 2 of T4.2c): ``commitment`` (no finality stated),
``outer_ix_index``/``inner_ix_index`` (no instruction index), ``is_mayhem_agent``
(no attribution). ``event_index`` is the ordinal of the trade among the trades
of the same transaction *in the batch being written*, ordered by the source's
own ``slotIndexId`` — ``0`` for the one trade a transaction has in every row
of the live captures (230 of 230). ``quote_mint`` is native SOL because the
row was accepted only when ``quote_is_native_sol`` held (``swap_api.py``);
``token_decimals`` is 6 because the curve's token is (``normalize.py`` refuses
any other on the curve read). Dedupe is the schema's
``ON CONFLICT (block_time, signature, event_index) DO NOTHING``.

**Two venues since T4.11** (``meme_trades.program``, ``0029``): the bonding
curve (``pump``) and the canonical PumpSwap pool the mint migrates into
(``pump_amm``) — the tape of a bet that holds through the migration
(EXP-M4). Any other venue (``raydium_cpmm`` was observed live) is still
skipped, as ``unsupported_venue``. The two reads the **fold** makes stay
curve-only (``coalesce(program, 'pump') = 'pump'``), so ``meme_features_v3``
means today exactly what it meant yesterday; the pool's tape is read by
``lab_repo_pool.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT
from hunter_meme_worker.features_tape import TapeTrade

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.board_models import NormalizedSwapTrade

CURVE_TOKEN_DECIMALS = 6
SWAP_API_SOURCE = "swap_api"
CURVE_PROGRAM = "pump"
POOL_PROGRAM = "pump_amm"
PROGRAMS: tuple[str, ...] = (CURVE_PROGRAM, POOL_PROGRAM)
"""``meme_trades.program`` (``0029``): the curve and the canonical PumpSwap pool."""
UNSUPPORTED_VENUE = "unsupported_venue"


@dataclass(frozen=True, slots=True)
class TradeRow:
    """One row of ``meme_trades`` from the ``swap-api`` tape."""

    block_time: datetime
    signature: str
    event_index: int
    mint: str
    slot: int
    received_at: datetime
    trader: str
    side: str
    sol_lamports: int
    token_amount: Decimal
    price: Decimal
    quote_mint: str = NATIVE_SOL_QUOTE_MINT
    token_decimals: int = CURVE_TOKEN_DECIMALS
    commitment: str | None = None
    outer_ix_index: int | None = None
    inner_ix_index: int | None = None
    is_mayhem_agent: bool | None = None
    source: str = SWAP_API_SOURCE
    program: str = CURVE_PROGRAM


def trade_rows(trades: Sequence[NormalizedSwapTrade]) -> tuple[list[TradeRow], dict[str, int]]:
    """Curve and pool trades in native SOL become rows; the rest is counted by reason."""
    skipped: dict[str, int] = {}
    accepted = [t for t in trades if t.program in PROGRAMS and t.quote_is_native_sol]
    for trade in trades:
        if trade.program not in PROGRAMS:
            skipped[UNSUPPORTED_VENUE] = skipped.get(UNSUPPORTED_VENUE, 0) + 1
        elif not trade.quote_is_native_sol:
            skipped["unsupported_quote"] = skipped.get("unsupported_quote", 0) + 1
    ordinal: dict[str, int] = {}
    rows: list[TradeRow] = []
    for trade in sorted(accepted, key=lambda t: t.slot_index_id):
        index = ordinal.get(trade.signature, 0)
        ordinal[trade.signature] = index + 1
        assert trade.sol_lamports is not None  # quote_is_native_sol guarantees it
        rows.append(
            TradeRow(
                block_time=trade.observed_at,
                signature=trade.signature,
                event_index=index,
                mint=trade.mint,
                slot=trade.slot,
                received_at=trade.received_at,
                trader=trade.trader,
                side=trade.side,
                sol_lamports=trade.sol_lamports,
                token_amount=trade.token_amount,
                price=trade.price,
                program=trade.program,
            )
        )
    return rows, skipped


_TRADE_COLUMNS = tuple(TradeRow.__dataclass_fields__)
_INSERT_TRADE = text(
    f"INSERT INTO meme_trades ({', '.join(_TRADE_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _TRADE_COLUMNS)}) "
    "ON CONFLICT (block_time, signature, event_index) DO NOTHING"
)


async def insert_trades(session: AsyncSession, rows: Sequence[TradeRow]) -> int:
    """Returns how many rows were *offered*; duplicates are the schema's business."""
    if not rows:
        return 0
    await session.execute(_INSERT_TRADE, [asdict(row) for row in rows])
    return len(rows)


_TAPE_MINUTE = text(
    "SELECT mint, block_time, received_at, trader, side, sol_lamports FROM meme_trades "
    "WHERE mint = ANY(:mints) AND source = 'swap_api' AND coalesce(program, 'pump') = 'pump' "
    "  AND block_time > :start AND block_time <= :end_time AND received_at <= :end_time"
)
_TAPE_CREATOR = text(
    "SELECT t.mint, t.block_time, t.received_at, t.trader, t.side, t.sol_lamports "
    "FROM meme_trades t JOIN meme_tokens k ON k.mint = t.mint AND k.creator = t.trader "
    "WHERE t.mint = ANY(:mints) AND t.source = 'swap_api' AND coalesce(t.program, 'pump') = 'pump' "
    "  AND t.block_time <= :end_time AND t.received_at <= :end_time"
)
"""Two reads with the same non-anticipation predicate (``received_at <=
end_time``): the minute's window for the counts, and the creator's whole
covered tape for ``creator_sold``/``creator_net_seller``. Both curve-only
(``0029``): a row written before the column is a curve row by construction."""

_OPEN_BETS = text("SELECT DISTINCT mint FROM meme_paper_bets WHERE status = 'open'")


async def load_tape(
    session: AsyncSession, *, mints: Sequence[str], end_time: datetime
) -> dict[str, list[TapeTrade]]:
    """The trades the fold may look at for ``end_time``, per mint."""
    if not mints:
        return {}
    params = {"mints": list(mints), "end_time": end_time, "start": end_time - timedelta(minutes=1)}
    out: dict[str, list[TapeTrade]] = {mint: [] for mint in mints}
    seen: set[tuple[str, datetime, str, str, int]] = set()
    for statement in (_TAPE_MINUTE, _TAPE_CREATOR):
        for r in (await session.execute(statement, params)).mappings():
            key = (
                str(r["mint"]),
                r["block_time"],
                str(r["trader"]),
                str(r["side"]),
                int(r["sol_lamports"]),
            )
            if key in seen:
                continue
            seen.add(key)
            out[str(r["mint"])].append(
                TapeTrade(
                    block_time=r["block_time"],
                    received_at=r["received_at"],
                    trader=str(r["trader"]),
                    side=str(r["side"]),
                    sol_lamports=int(r["sol_lamports"]),
                )
            )
    return out


async def open_bet_mints(session: AsyncSession) -> frozenset[str]:
    """The mints the Lab is marking right now — the top of every priority list."""
    return frozenset(str(m) for m in (await session.execute(_OPEN_BETS)).scalars().all())


__all__ = [
    "CURVE_PROGRAM",
    "CURVE_TOKEN_DECIMALS",
    "POOL_PROGRAM",
    "PROGRAMS",
    "SWAP_API_SOURCE",
    "UNSUPPORTED_VENUE",
    "TradeRow",
    "insert_trades",
    "load_tape",
    "open_bet_mints",
    "trade_rows",
]
