"""T4.61b/T4.61c — the bounded read behind the conviction ladder, guarded, and the
glue that turns an admission into :class:`~hunter_meme_executor.conviction.ConvictionEvidence`.

Three of the five rungs are already in the admission's hands (the creator
verdict, the bundled/top-10 shares, the fresh curve read). The other two come
from two statements against the radar's series, each bounded by the mint's index
and a window:

- the photos of ``meme_curve_snapshots`` in the last ``drop_window_s`` (real SOL,
  received by ``now``) — KB-0118's window, folded with the registered
  ``recent_drawdown_pct`` and the admission's own ``confirmed`` read as the
  newest point (the "same information, fresher" mechanism of §4);
- the newest ``meme_features_15s`` row of the mint inside
  ``evidence_max_age_s`` — ``unique_buyers_60s`` and ``holders_rising``.

**Guarded (T4.61c, review A1).** The read runs only with the flag **on** (off
costs nothing: no statement, no ladder), behind its own deadline, and never
raises into the entries loop: a timeout or any error is logged, written as
``conviction_read_failed`` in the admission, and judged by the ladder as the drop
it cannot see — ``entry_after_drop_unknown``, a refusal by name, like every input
that is absent (§8). Same mould as ``read_creator_flow``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_indicators.meme.drawdown import ReservePoint
from hunter_meme_executor.conviction import (
    LADDER_OFF,
    ConvictionConfig,
    ConvictionEvidence,
    ConvictionLadder,
    evaluate_conviction,
)
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_risk_meme import MemeConviction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.admission_context import AdmissionContext
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.context import ExecutorContext
    from hunter_risk_meme import MemeEntryProposal, MemeLimits

__all__ = [
    "READ_TIMEOUT_S",
    "ConvictionOutcome",
    "conviction_for",
    "evidence_from",
    "read_series_evidence",
]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
READ_TIMEOUT_S: Final = 3.0
"""The read's own deadline: an entry must not wait on a locked partition."""

_POINTS = text(
    "SELECT observed_at, received_at, real_sol_reserves FROM meme_curve_snapshots "
    "WHERE mint = :mint AND observed_at >= :peak_since AND observed_at <= :now "
    "  AND received_at <= :now "
    "ORDER BY observed_at, received_at"
)
"""``lab_repo_drawdown._RESERVES``'s shape for one mint: the partition-local
children of ``ix_meme_curve_snapshots_mint_observed`` serve it."""
_FRESH = text(
    "SELECT as_of, unique_buyers_60s, holders_rising FROM meme_features_15s "
    "WHERE mint = :mint AND as_of >= :fresh_since AND as_of <= :now "
    "ORDER BY as_of DESC LIMIT 1"
)
"""``NULL`` half when the fast lane has not written the mint inside the window."""


async def read_series_evidence(
    session: AsyncSession, mint: str, *, config: ConvictionConfig, now: datetime
) -> dict[str, Any]:
    """``{points, as_of, unique_buyers_60s, holders_rising}`` — the two bounded halves."""
    params = {
        "mint": mint,
        "now": now,
        "peak_since": now - timedelta(seconds=config.drop_window_s),
        "fresh_since": now - timedelta(seconds=config.evidence_max_age_s),
    }
    rows = (await session.execute(_POINTS, params)).mappings().all()
    fresh = (await session.execute(_FRESH, params)).mappings().first()
    points = tuple(
        ReservePoint(
            observed_at=r["observed_at"],
            received_at=r["received_at"],
            real_sol=Decimal(str(r["real_sol_reserves"])),
        )
        for r in rows
    )
    return {"points": points, **({} if fresh is None else dict(fresh))}


def evidence_from(
    built: AdmissionContext,
    curve: CurveRead,
    series: dict[str, Any],
    *,
    read_failed: str | None = None,
) -> ConvictionEvidence:
    """The admission's own inputs plus the series — no value invented."""
    verdict = cast(dict[str, Any], built.extras.get("creator_verdict") or {})
    decided_by = verdict.get("decided_by")
    buyers = series.get("unique_buyers_60s")
    return ConvictionEvidence(
        creator_decided_by=str(decided_by) if isinstance(decided_by, str) and decided_by else None,
        unique_buyers_60s=None if buyers is None else int(buyers),
        holders_rising=series.get("holders_rising"),
        evidence_as_of=series.get("as_of"),
        bundled_share_pct=built.context.bundled_share_pct,
        top10_share_pct=built.context.top10_share_pct,
        real_sol_now=Decimal(curve.account.real_sol_reserves) / LAMPORTS,
        curve_points=tuple(series.get("points") or ()),
        read_failed=read_failed,
    )


@dataclass(frozen=True, slots=True)
class ConvictionOutcome:
    """What the admission carries: the ladder (``None`` when the flag is off)
    and, when the read failed, the error's name."""

    ladder: ConvictionLadder | None
    read_failed: str | None = None

    @property
    def input(self) -> MemeConviction:
        """The engine's input: off when there is no ladder."""
        return MemeConviction() if self.ladder is None else self.ladder.to_input()

    def as_json(self) -> dict[str, Any]:
        if self.ladder is None:
            return dict(LADDER_OFF)
        payload = self.ladder.as_json()
        if self.read_failed is not None:
            payload["read_failed"] = self.read_failed
        return payload


async def conviction_for(
    ctx: ExecutorContext,
    built: AdmissionContext,
    curve: CurveRead,
    *,
    proposal: MemeEntryProposal,
    limits: MemeLimits,
    now: datetime,
) -> ConvictionOutcome:
    """Off ⇒ nothing read, nothing judged. On ⇒ read (guarded), then judge;
    a failed read is judged as the drop the ladder cannot see."""
    config = ctx.config.conviction
    if not config.enabled:
        return ConvictionOutcome(ladder=None)
    series: dict[str, Any] = {}
    failed: str | None = None
    try:
        async with asyncio.timeout(READ_TIMEOUT_S):
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                series = await read_series_evidence(session, proposal.mint, config=config, now=now)
    except TimeoutError:
        failed = "timeout"
        logger.warning("meme_executor_conviction_read_timeout", mint=proposal.mint)
    except Exception as exc:
        failed = type(exc).__name__
        logger.warning(
            "meme_executor_conviction_read_failed", mint=proposal.mint, error_type=failed
        )
    ladder = evaluate_conviction(
        evidence_from(built, curve, series, read_failed=failed),
        config,
        requested_sol=proposal.requested_sol,
        max_sol_per_trade=limits.max_sol_per_trade,
        as_of=now,
    )
    return ConvictionOutcome(ladder=ladder, read_failed=failed)
