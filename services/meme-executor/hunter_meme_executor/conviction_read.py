"""T4.61b — the one bounded read behind the conviction ladder, and the glue that
turns an admission into :class:`~hunter_meme_executor.conviction.ConvictionEvidence`.

Three of the five rungs are already in the admission's hands (the creator
verdict, the bundled/top-10 shares, the fresh curve read). The other two come
from one statement against the radar's series, both halves bounded by the mint's
index and a window:

- the newest ``meme_features_15s`` row of the mint inside
  ``evidence_max_age_s`` — ``unique_buyers_60s`` and ``holders_rising``;
- ``max(real_sol_reserves)`` of ``meme_curve_snapshots`` in the last
  ``drop_window_s`` — KB-0118's peak, which the admission's own ``confirmed``
  read is compared against (the "same information, fresher" mechanism of §4).

A row that does not exist is ``None`` and the ladder discounts it; nothing here
turns silence into a pass. The statement runs on every candidate that reached the
admission, flag on or off, so the shadow ladder in the order row is real.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_executor.conviction import (
    ConvictionConfig,
    ConvictionEvidence,
    ConvictionLadder,
    evaluate_conviction,
)
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_risk_meme import MemeEntryProposal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.admission_context import AdmissionContext
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.context import ExecutorContext
    from hunter_risk_meme import MemeLimits

__all__ = ["apply_ladder", "conviction_for", "evidence_from", "read_series_evidence"]

LAMPORTS = Decimal(1_000_000_000)

_SERIES = text(
    "SELECT p.peak_real_sol, p.peak_points, f.as_of, f.unique_buyers_60s, f.holders_rising "
    "FROM (SELECT max(real_sol_reserves) AS peak_real_sol, count(*) AS peak_points "
    "      FROM meme_curve_snapshots "
    "      WHERE mint = :mint AND observed_at >= :peak_since AND observed_at <= :now) AS p "
    "LEFT JOIN LATERAL ("
    "  SELECT as_of, unique_buyers_60s, holders_rising FROM meme_features_15s "
    "  WHERE mint = :mint AND as_of >= :fresh_since AND as_of <= :now "
    "  ORDER BY as_of DESC LIMIT 1) AS f ON true"
)
"""One row always (an aggregate without ``GROUP BY``), the 15 s half ``NULL``
when the fast lane has not written the mint inside the freshness window."""


async def read_series_evidence(
    session: AsyncSession, mint: str, *, config: ConvictionConfig, now: datetime
) -> dict[str, Any]:
    params = {
        "mint": mint,
        "now": now,
        "peak_since": now - timedelta(seconds=config.drop_window_s),
        "fresh_since": now - timedelta(seconds=config.evidence_max_age_s),
    }
    row = (await session.execute(_SERIES, params)).mappings().first()
    return {} if row is None else dict(row)


def evidence_from(
    built: AdmissionContext, curve: CurveRead, series: dict[str, Any]
) -> ConvictionEvidence:
    """The admission's own inputs plus the series row — no value invented."""
    verdict = cast(dict[str, Any], built.extras.get("creator_verdict") or {})
    decided_by = verdict.get("decided_by")
    peak = series.get("peak_real_sol")
    buyers = series.get("unique_buyers_60s")
    return ConvictionEvidence(
        creator_decided_by=str(decided_by) if isinstance(decided_by, str) and decided_by else None,
        unique_buyers_60s=None if buyers is None else int(buyers),
        holders_rising=series.get("holders_rising"),
        evidence_as_of=series.get("as_of"),
        bundled_share_pct=built.context.bundled_share_pct,
        top10_share_pct=built.context.top10_share_pct,
        real_sol_now=Decimal(curve.account.real_sol_reserves) / LAMPORTS,
        real_sol_peak=None if peak is None else Decimal(str(peak)),
        peak_points=int(series.get("peak_points") or 0),
    )


async def conviction_for(
    ctx: ExecutorContext,
    built: AdmissionContext,
    curve: CurveRead,
    *,
    proposal: MemeEntryProposal,
    limits: MemeLimits,
    now: datetime,
) -> ConvictionLadder:
    """Read, then judge. ``proposal.requested_sol`` is already clamped to the
    written scope (``proposal_from``); the ladder clamps it to the trade cap and
    scales from there."""
    config = ctx.config.conviction
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        series = await read_series_evidence(session, proposal.mint, config=config, now=now)
    return evaluate_conviction(
        evidence_from(built, curve, series),
        config,
        requested_sol=proposal.requested_sol,
        max_sol_per_trade=limits.max_sol_per_trade,
        min_trade_sol=limits.min_trade_sol,
    )


def apply_ladder(proposal: MemeEntryProposal, ladder: ConvictionLadder) -> MemeEntryProposal:
    """The proposal the engine evaluates: the sized request when the ladder is
    applied, the untouched one otherwise (flag off, or a refusal — the engine
    still records every check at the flat size, and the refusal is written by
    its own name after the decision)."""
    if not ladder.applied:
        return proposal
    return MemeEntryProposal.model_validate(
        {**proposal.model_dump(), "requested_sol": ladder.requested_sol}
    )
