# pyright: reportPrivateUsage=false
"""T4.31 (EXP-M9) against a real Postgres at ``head`` — the E2-b read.

What only a database can prove: the SQL of
:func:`hunter_meme_worker.lab_repo_e2b.e2b_for` sums the tape **per judged
(mint, instant)** — a later photo of the same mint sees a different share and
an earlier one never reads the trades that landed after it —, that
``completed_at`` only counts when it is at or before the judged instant, that
a mint with no tape comes back ``no_tape``; and the post-incident rule of
T4.24b: the plan of this per-tick query is an **index scan** over
``ix_meme_trades_mint_block_time``, never a sequential scan of the tape, with
the partitions pruned by the absolute floor.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.lab_repo_e2b import e2b_for

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
CREATED = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

_A_TOKEN = (
    "INSERT INTO meme_tokens (mint, symbol, creator, created_at, completed_at, first_seen_source, "
    "  first_seen_at, last_seen_at) VALUES (:mint, 'E2B', :creator, :created_at, CAST(:completed_at AS timestamptz), "
    "  'test', :created_at, :created_at) ON CONFLICT (mint) DO NOTHING"
)
_A_TRADE = (
    "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, received_at, trader, "
    "  side, sol_lamports, token_amount, price, quote_mint, token_decimals, source) "
    "VALUES (:block_time, :signature, 0, :mint, 1, :block_time, :trader, :side, :lamports, 1000, "
    "  0.00000005, '11111111111111111111111111111111', 6, 'swap_api')"
)
"""``meme_trades`` is insert-only by privilege (§33): nothing here deletes —
every test plants its own mints, exactly as ``test_lab_operator_3`` does."""


async def _plant(session: AsyncSession) -> tuple[str, str, str]:
    """``(tape, born full, dark)`` — three fresh mints and the tape of the first."""
    tag = uuid4().hex[:8]
    mint, full, dark = f"E2B_TAPE_{tag}", f"E2B_FULL_{tag}", f"E2B_DARK_{tag}"
    for mint_id, completed_at in (
        (mint, None),
        (full, CREATED + timedelta(seconds=30)),
        (dark, None),
    ):
        await session.execute(
            text(_A_TOKEN),
            {
                "mint": mint_id,
                "creator": f"C_{mint_id}",
                "created_at": CREATED,
                "completed_at": completed_at,
            },
        )
    # The tape of ``MINT``: 9 SOL from one whale at +10 s, then ten small buyers
    # of 1 SOL each at +30 s — 0,474 of the SOL at +20 s, 0,474 at the end.
    trades: list[dict[str, Any]] = [
        {
            "block_time": CREATED + timedelta(seconds=10),
            "signature": f"WHALE_{tag}",
            "mint": mint,
            "trader": "WHALE",
            "side": "buy",
            "lamports": 9_000_000_000,
        }
    ]
    trades += [
        {
            "block_time": CREATED + timedelta(seconds=30),
            "signature": f"SMALL{i}_{tag}",
            "mint": mint,
            "trader": f"SMALL{i}",
            "side": "buy",
            "lamports": 1_000_000_000,
        }
        for i in range(10)
    ]
    # A sell by the whale never counts, and neither does the tape of another mint.
    trades.append(
        {
            "block_time": CREATED + timedelta(seconds=40),
            "signature": f"WHALE_SELL_{tag}",
            "mint": mint,
            "trader": "WHALE",
            "side": "sell",
            "lamports": 5_000_000_000,
        }
    )
    trades.append(
        {
            "block_time": CREATED + timedelta(seconds=20),
            "signature": f"FULL_BUY_{tag}",
            "mint": full,
            "trader": "SNIPER",
            "side": "buy",
            "lamports": 85_000_000_000,
        }
    )
    for trade in trades:
        await session.execute(text(_A_TRADE), trade)
    return mint, full, dark


@pytest.mark.asyncio
async def test_the_tape_is_summed_per_judged_instant_and_never_past_it(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        mint, full, dark = await _plant(session)
    early = CREATED + timedelta(seconds=20)
    late = CREATED + timedelta(seconds=60)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        read = await e2b_for(session, [(mint, early), (mint, late), (full, late), (dark, late)])
    # At +20 s only the whale has bought: one buyer, the whole of the SOL.
    assert read[(mint, early)].buyers == 1
    assert read[(mint, early)].top_buyer_share == Decimal(1)
    # At +60 s the ten small buyers are there; the whale's sell is not counted.
    late_read = read[(mint, late)]
    assert late_read.buyers == 11
    assert late_read.top_buyer_share == Decimal(9) / Decimal(19)
    assert late_read.fill_seconds is None, "this curve never filled"
    # Born full: the completion is at +30 s, already observed at +60 s.
    assert read[(full, late)].fill_seconds == 30
    # No tape at all is named, never read as a clean coin.
    dark_read = read[(dark, late)]
    assert (dark_read.top_buyer_share, dark_read.buyers, dark_read.tape_reason) == (
        None,
        None,
        "no_tape",
    )


@pytest.mark.asyncio
async def test_a_completion_after_the_judged_instant_is_not_born_full(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Non-anticipation: the curve of ``FULL`` fills at +30 s, so a row judged
    at +20 s must not know it — reading it would be look-ahead."""
    async with role_session(db_session_factory, db_role=WORKER) as session:
        _, full, _ = await _plant(session)
    at_20s = CREATED + timedelta(seconds=20)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        read = await e2b_for(session, [(full, at_20s)])
    assert read[(full, at_20s)].fill_seconds is None


@pytest.mark.asyncio
async def test_explain_the_e2b_read_uses_the_mint_block_time_index_at_200k_trades(
    db_engine: AsyncEngine,
) -> None:
    """The T4.24b post-incident rule, for the one query this task adds: with
    200 k rows in the tape and 130 judged pairs (the size of a real tick), the
    plan is an index scan over ``ix_meme_trades_mint_block_time`` and the
    absolute floor prunes the monthly partitions — never a sequential scan of
    ``meme_trades``. Rolled back at the end: the shared container must not be
    left with 200 k rows for every other test to scan."""
    from hunter_meme_worker.lab_repo_e2b import _E2B, CREATION_LEAD_S, TAPE_FLOOR_S

    as_of = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    conn = await db_engine.connect()
    trans = await conn.begin()
    try:
        await conn.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, "
                "  created_at, symbol) "
                "SELECT 'E2B_BULK_' || gs, 'pumpfun_rest', now(), now(), "
                "  timestamptz '2026-09-25 00:00:00+00' + (gs * interval '7 seconds'), 'BULK' "
                "FROM generate_series(1, 2000) AS gs ON CONFLICT (mint) DO NOTHING"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, "
                "  received_at, trader, side, sol_lamports, token_amount, price, quote_mint, "
                "  token_decimals, source) "
                "SELECT t.created_at + (n * interval '1 second'), 'BULK_' || t.mint || '_' || n, "
                "  0, t.mint, 1, t.created_at, 'W' || (n % 37), "
                "  CASE WHEN n % 3 = 0 THEN 'sell' ELSE 'buy' END, "
                "  1000000 * n, 1000, 0.00000005, '11111111111111111111111111111111', 6, "
                "  'swap_api' "
                "FROM meme_tokens t, generate_series(1, 100) AS n "
                "WHERE t.mint LIKE 'E2B_BULK_%' ON CONFLICT DO NOTHING"
            )
        )
        await conn.execute(text("ANALYZE meme_trades"))
        await conn.execute(text("ANALYZE meme_tokens"))
        judged = [f"E2B_BULK_{i}" for i in range(1, 131)]
        plan_rows = (
            (
                await conn.execute(
                    text(f"EXPLAIN {_E2B.text}"),
                    {
                        "mints": judged,
                        "as_ofs": [as_of] * len(judged),
                        "floor": as_of - timedelta(seconds=TAPE_FLOOR_S),
                        "ceiling": as_of,
                        "lead_s": CREATION_LEAD_S,
                    },
                )
            )
            .scalars()
            .all()
        )
        plan = "\n".join(plan_rows)
        row_count = (await conn.execute(text("SELECT count(*) FROM meme_trades"))).scalar_one()
    finally:
        await trans.rollback()
        await conn.close()
    assert row_count >= 200_000, "the plan must be declared over a tape this size, not a fixture"
    # The partition-local child of ``ix_meme_trades_mint_block_time``.
    assert "mint_block_time_idx on meme_trades_2026_09" in plan, plan
    assert "Seq Scan on meme_trades" not in plan, plan
    assert "meme_trades_2026_12" not in plan, "the ceiling must prune the later partitions"
    notes = Path(__file__).resolve().parents[3] / ".claude" / "state"  # noqa: ASYNC240
    notes.joinpath("notes-T4.31-explain.txt").write_text(
        f"rows={row_count}\npairs=130\n{plan}", encoding="utf-8"
    )
