"""Mark to market, write the curve, then let the kill switch read it.

**The order is the contract, not a preference.** ``portfolio_risk_state``'s
guard bounds the peak and the day's opening by the greatest equity the curve has
ever *shown* (DATABASE.md §18.7, ``_OBSERVED_EQUITY``), so a peak written before
the point that justifies it is refused by the database. And T3.6 anchors the day
on the last 1m point observed at or before the São Paulo turn, so the point has
to exist before the evaluation that looks for it. Hence: build the state, append
the point, **then** evaluate and persist the switch — all in one transaction,
under the wallet's lock, so the number the panel reads and the latch the workers
obey can never disagree.

Three things this cycle writes that nobody else can:

- ``brl_unavailable_reason`` and ``marks_stale`` on the point itself
  (``0007_paper_roles`` §19.3). ``record_equity_point`` computes both and audits
  them but has no column to put them in, so the worker — the only role with DML
  on the curve — stamps them onto the row it just appended, in the same
  transaction;
- the **hourly mirror of the day's anchor**. The operational curve is ``1m`` and
  it is pruned at 30 days; the daily decomposition looks the reference point up
  in the ``1h`` lane, at exactly ``day_reference_observed_at``
  (``EquitySnapshotRepository.at``). Without the mirror the decomposition is
  unavailable from the second trading day onwards — the debt notes-T3.3.md §2
  filed against whoever writes the curve, which is this cycle;
- ``kill_switch.changed``, published after the evaluation (adversarial review of
  2026-09-07, condition 4). Only the engine may: it moves the latch and enqueues
  the event in one transaction, which is exactly what ``0007`` made possible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.domain.enums import Timeframe
from hunter_core.logging import get_logger
from hunter_core.portfolio.fx_policy import PAPER_FX_POLICY
from hunter_core.portfolio.ledger import EquityPoint, record_equity_point
from hunter_core.portfolio.state import build_portfolio_state
from hunter_core.risk.curve import OPERATIONAL_RESOLUTION
from hunter_core.risk.kill_switch import KillSwitchEvaluation, evaluate_and_persist
from hunter_risk.limits import PAPER_V1

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef
    from hunter_risk.limits import RiskLimits

__all__ = ["MarkToMarket", "run_mtm_cycle"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MarkToMarket:
    """One MTM cycle: the point that was written and what it made the switch do."""

    point: EquityPoint
    evaluation: KillSwitchEvaluation
    stale_marks: tuple[uuid.UUID, ...]
    unavailable: tuple[str, ...]

    @property
    def equity(self) -> Decimal:
        return self.point.equity


async def run_mtm_cycle(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    marks: Mapping[uuid.UUID, Decimal],
    betas: Mapping[uuid.UUID, Decimal] | None,
    exit_cost_rate: Decimal,
    now: datetime,
    limits: RiskLimits = PAPER_V1,
    fx: FxObservation | None = None,
) -> MarkToMarket:
    """Mark the wallet, append the point, evaluate the switch. One transaction."""
    build = await build_portfolio_state(
        session,
        organization_id=wallet.organization_id,
        portfolio_id=wallet.portfolio_id,
        as_of=now,
        marks=marks,
        exit_cost_rate=exit_cost_rate,
        betas=betas,
    )
    observation = fx if fx is not None else await _latest_fx(session, now)
    point = await record_equity_point(
        session, build=build, fx=observation, resolution=OPERATIONAL_RESOLUTION
    )
    await _stamp_quality(session, wallet=wallet, point=point, stale=bool(build.stale_marks))
    evaluation = await evaluate_and_persist(
        session, wallet.portfolio_id, build.state, now, limits=limits, publish=True
    )
    if evaluation.changed:
        # ``publish=True`` above already enqueued ``kill_switch.changed`` in the
        # core's own shape, same transaction as the latch
        # (``hunter_core.risk.transitions.record_transition``). This cycle used
        # to publish a *second* event here, in its own shape — removed, so a
        # consumer sees exactly one event per transition (T3.5d review finding
        # 1, ``.claude/state/notes-T3.5.md`` T3.5d section).
        logger.warning(
            "kill_switch_moved",
            portfolio_id=str(wallet.portfolio_id),
            previous=evaluation.previous.value,
            latched=evaluation.latched.value,
            reason=evaluation.reason,
        )
    if evaluation.reference.writes and evaluation.reference.observed_at is not None:
        await _mirror_day_anchor(
            session, wallet=wallet, observed_at=evaluation.reference.observed_at
        )
    if build.stale_marks:
        logger.warning(
            "mtm_marks_stale",
            portfolio_id=str(wallet.portfolio_id),
            markets=[str(market_id) for market_id in build.stale_marks],
        )
    return MarkToMarket(
        point=point,
        evaluation=evaluation,
        stale_marks=build.stale_marks,
        unavailable=build.unavailable,
    )


async def _latest_fx(session: AsyncSession, now: datetime) -> FxObservation | None:
    """The newest USDTBRL observation we could have acted on at ``now``.

    Never the newest *observed*: a rate that only reached us after this instant
    cannot explain it, and ``record_equity_point`` would refuse it anyway. A
    missing rate is not an error — the USDT side of the point is written and the
    BRL side is unavailable **with a reason**.
    """
    return await FxObservationRepository(session).latest_available(
        pair=PAPER_FX_POLICY.pair, source=PAPER_FX_POLICY.source, as_of=now
    )


async def _stamp_quality(
    session: AsyncSession, *, wallet: WalletRef, point: EquityPoint, stale: bool
) -> None:
    """Say on the row itself why the BRL is missing and whether the marks were old.

    Without this a point with ``fx_observation_id IS NULL`` is indistinguishable
    from one whose rate was refused, and a point built on a stale mark looks
    exactly like a freshly measured one — the extrapolation §18.2 forbids.
    """
    if point.brl_unavailable_reason is None and not stale:
        return
    await session.execute(
        text(
            "UPDATE portfolio_equity_snapshots SET brl_unavailable_reason = :reason, "
            "marks_stale = :stale WHERE organization_id = :org AND portfolio_id = :pf "
            "AND resolution = :resolution AND ts = :ts"
        ),
        {
            "reason": point.brl_unavailable_reason,
            "stale": stale,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "resolution": point.resolution.value,
            "ts": point.ts,
        },
    )


async def _mirror_day_anchor(
    session: AsyncSession, *, wallet: WalletRef, observed_at: datetime
) -> None:
    """Copy the point that anchored the day into the lane that is never pruned.

    The ``1m`` lane is the operational curve and is pruned at 30 days; the
    reference the daily decomposition reads lives in ``1h`` and is matched at
    **exactly** ``day_reference_observed_at`` (never "the nearest earlier one",
    which proves temporal order and not accounting identity — Astra, T3.3
    review). Idempotent: the primary key is ``(portfolio, resolution, ts)``.
    """
    await session.execute(
        text(
            "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, resolution, "
            "ts, cash, equity, exposure_notional, exposure_pct, unrealized_pnl, realized_pnl_cum, "
            "peak_equity, drawdown_pct, open_positions, fx_observation_id, "
            "brl_unavailable_reason, marks_stale) SELECT organization_id, portfolio_id, "
            ":reference, ts, cash, equity, exposure_notional, exposure_pct, unrealized_pnl, "
            "realized_pnl_cum, peak_equity, drawdown_pct, open_positions, fx_observation_id, "
            "brl_unavailable_reason, marks_stale FROM portfolio_equity_snapshots "
            "WHERE organization_id = :org AND portfolio_id = :pf AND resolution = :operational "
            "AND ts = :ts ON CONFLICT DO NOTHING"
        ),
        {
            "reference": REFERENCE_RESOLUTION.value,
            "operational": OPERATIONAL_RESOLUTION.value,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "ts": observed_at,
        },
    )


def resolutions() -> tuple[Timeframe, Timeframe]:
    """``(operational, reference)`` — the two lanes this cycle touches."""
    return OPERATIONAL_RESOLUTION, REFERENCE_RESOLUTION
