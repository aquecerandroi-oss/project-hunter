"""The E2-b read of the Lab loop (T4.31, EXP-M9) — the largest buyer's share
of the SOL bought since the mint, and whether the curve was already full at
the judged instant, as ``hunter_worker`` and **bounded**.

**Where the datum comes from.** Nothing in the fast lane carries it:
``meme_features_15s`` has ``unique_buyers_60s`` but never *who* bought (the
batch activity route does not say), and ``top10_share`` (holders reader,
``meme_features_1m`` only) is a share of **supply held**, not of SOL paid.
The only source of per-buyer SOL is our own tape, ``meme_trades``
(``trader``, ``side``, ``sol_lamports``, ``block_time``) — the same table the
measurement of KB-0103/KB-0105 read (``infra/scripts/sql/research/
2026-09-16-r13-q04-apostas-medidas-e-e2b.sql``). Its coverage is partial by
construction (~21–25 % of the graduated coins in those days): a mint with no
tape comes back with ``top_buyer_share = None`` and the criterion refuses
``e2b_top_buyer_unknown``, which is one of the things EXP-M9 measures.

**Non-anticipation, twice.** The tape is summed per judged **(mint, instant)**
pair — ``block_time <= as_of`` — never up to "now": on the 15-second lane a
tick can carry rows up to ``lab_fast_backlog_s`` old, and summing to the
tick's clock would let a row read trades that landed after it. And
``completed_at`` only counts when it is at or before the same instant: a
curve that fills later is not a coin that was born full.

**Bounded, and why (the T4.24b incident).** Every predicate is index-backed
and every scan has a floor:

- ``ix_meme_trades_mint_block_time`` (``mint``, ``block_time``, DATABASE.md
  §35) serves the join: for each judged pair, one range scan of that mint's
  own trades between the mint's creation and the judged instant — the coins
  the Lab judges are minutes old, so each range is tiny;
- ``:floor`` = ``min(as_of) − TAPE_FLOOR_S`` (24 h, the age of the tracked set)
  and ``:ceiling`` = ``max(as_of)`` are **absolute** bounds on ``block_time``,
  so the planner prunes ``meme_trades``' monthly partitions (§15.2) to the one
  or two that can hold a row instead of opening every one of them; the
  per-row bound (``block_time <= j.as_of``) is correlated and prunes nothing,
  which is why both constants are there;
- ``created_at - 60 s`` is the per-coin bound (the research query's own lead:
  a buy of the same block can be stamped a hair before the creation);
- ``SET LOCAL statement_timeout = 8000`` inside a savepoint, exactly like
  ``pedigree_for``: when the read fails the tick goes on with the datum
  unread (every set refuses ``e2b_top_buyer_unknown`` by name) instead of
  dying.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.pedigree_e2b import E2bFeatures
from hunter_meme_worker.lab_repo_fast import pedigree_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals_row import GateRow

__all__ = ["TAPE_FLOOR_S", "e2b_features_from_counts", "e2b_for", "lineage_for"]

TAPE_FLOOR_S = 86_400
"""The absolute floor on ``block_time``: the tracked set is coins created in
the last 24 h, so no judged coin's tape starts earlier — and the floor is what
lets the planner prune the monthly partitions."""

CREATION_LEAD_S = 60
"""The lead the research query uses before ``created_at``: a buy of the mint's
own block can carry a ``block_time`` a hair before the creation stamp."""

_E2B = text(
    "WITH judged AS ("
    "  SELECT u.mint, u.as_of, t.created_at, "
    "         CASE WHEN t.completed_at <= u.as_of THEN t.completed_at END AS completed_at "
    "  FROM unnest(CAST(:mints AS text[]), CAST(:as_ofs AS timestamptz[])) AS u(mint, as_of) "
    "  JOIN meme_tokens t ON t.mint = u.mint "
    "), tape AS ("
    "  SELECT j.mint, j.as_of, tr.trader, sum(tr.sol_lamports) AS lamports "
    "  FROM judged j JOIN meme_trades tr ON tr.mint = j.mint AND tr.side = 'buy' "
    "   AND tr.block_time >= :floor AND tr.block_time <= :ceiling "
    "   AND tr.block_time >= j.created_at - make_interval(secs => :lead_s) "
    "   AND tr.block_time <= j.as_of "
    "  WHERE j.created_at IS NOT NULL "
    "  GROUP BY 1, 2, 3"
    ") "
    "SELECT j.mint, j.as_of, j.created_at, j.completed_at, "
    "       s.buyers, s.top_lamports, s.total_lamports "
    "FROM judged j LEFT JOIN ("
    "  SELECT mint, as_of, count(*) AS buyers, max(lamports) AS top_lamports, "
    "         sum(lamports) AS total_lamports FROM tape GROUP BY 1, 2"
    ") s ON s.mint = j.mint AND s.as_of = j.as_of"
)
"""One statement per tick for every judged ``(mint, as_of)`` pair."""

_logger = get_logger(__name__)


def e2b_features_from_counts(
    *,
    created_at: datetime | None,
    completed_at: datetime | None,
    buyers: int | None,
    top_lamports: int | None,
    total_lamports: int | None,
) -> E2bFeatures:
    """One row of :data:`_E2B` as the criterion reads it. Pure.

    The share is exact: both counters are lamports (integers on chain), so the
    quotient is a :class:`~decimal.Decimal` under the project's own context —
    never a float. ``total_lamports = 0`` is a tape that saw buys of zero SOL,
    which is not a share: ``no_sol_bought``.
    """
    fill_seconds = (
        None
        if created_at is None or completed_at is None
        else int((completed_at - created_at).total_seconds())
    )
    if buyers is None or top_lamports is None or total_lamports is None:
        return E2bFeatures(
            top_buyer_share=None, buyers=None, fill_seconds=fill_seconds, tape_reason="no_tape"
        )
    if total_lamports <= 0:
        return E2bFeatures(
            top_buyer_share=None,
            buyers=buyers,
            fill_seconds=fill_seconds,
            tape_reason="no_sol_bought",
        )
    with localcontext(CONTEXT):
        share = Decimal(top_lamports) / Decimal(total_lamports)
    return E2bFeatures(top_buyer_share=share, buyers=buyers, fill_seconds=fill_seconds)


async def e2b_for(
    session: AsyncSession, pairs: Sequence[tuple[str, datetime]]
) -> dict[tuple[str, datetime], E2bFeatures]:
    """The two legs of E2-b per judged ``(mint, instant)``, from our own tape.

    A pair missing from the answer is a pair whose datum was **not read** (the
    mint is not in ``meme_tokens``, or the read failed) — the caller refuses
    ``e2b_top_buyer_unknown`` by name, never reads it as clean.
    """
    judged = sorted(set(pairs))
    if not judged:
        return {}
    mints = [mint for mint, _ in judged]
    as_ofs = [as_of for _, as_of in judged]
    params = {
        "mints": mints,
        "as_ofs": as_ofs,
        "floor": min(as_ofs) - timedelta(seconds=TAPE_FLOOR_S),
        "ceiling": max(as_ofs),
        "lead_s": CREATION_LEAD_S,
    }
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = 8000"))
            rows = (await session.execute(_E2B, params)).mappings().all()
    except DBAPIError as exc:
        _logger.warning("meme_e2b_read_failed", pairs=len(pairs), error=type(exc.orig).__name__)
        return {}
    return {
        (str(r["mint"]), r["as_of"]): e2b_features_from_counts(
            created_at=r["created_at"],
            completed_at=r["completed_at"],
            buyers=None if r["buyers"] is None else int(r["buyers"]),
            top_lamports=None if r["top_lamports"] is None else int(r["top_lamports"]),
            total_lamports=None if r["total_lamports"] is None else int(r["total_lamports"]),
        )
        for r in rows
    }


async def lineage_for(
    session: AsyncSession, rows: Iterable[GateRow], specs: Iterable[RuleSetSpec]
) -> tuple[dict[str, PedigreeFeatures], dict[tuple[str, datetime], E2bFeatures] | None]:
    """The cross-cutting reads of one tick, for both lanes: the pedigree of
    every judged mint (T4.16, EXP-M6 — always read, every set may apply it)
    and, **only when some set of this lane asks for it**, the E2-b tape bounded
    by each row's own instant (T4.31, EXP-M9). ``None`` = nobody asked, and
    ``evaluate_gate`` then applies no E2-b at all.

    **No set on this clock → no read** (24/09/2026): with every active set on
    ``15s``, the minute lane paid the pedigree of ~320 mints (14 s on the VPS,
    cut at 8 s — ``meme_pedigree_read_failed``) for a result no gate received.
    """
    judged, lane = list(rows), tuple(specs)
    if not lane:
        return {}, None
    pedigree = await pedigree_for(session, sorted({row.mint for row in judged}))
    if not any(spec.pedigree_e2b for spec in lane):
        return pedigree, None
    return pedigree, await e2b_for(session, [(row.mint, row.end_time) for row in judged])
