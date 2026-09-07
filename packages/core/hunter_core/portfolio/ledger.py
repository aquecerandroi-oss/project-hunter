"""Appending to the equity curve.

Everything here is measured in the operating currency; the BRL reading is
derived at the end, from the observation the point names.

**A point of the curve names the rate it used.** With no usable observation the
USDT side of the point is still written and the BRL side is *unavailable with a
reason*, never extrapolated and never back-filled with today's rate (M3 joint
decision, item 1). Both that refusal and a point built on a stale mark are
audited, not just returned in memory (adversarial review of ``8a6a69f``,
deve-corrigir 5) — ``portfolio_equity_snapshots`` has no column of its own for
either yet, which is the debt ``.claude/state/notes-T3.3.md`` files for T3.1c.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION, EquitySnapshotRepository
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.portfolio.attribution import LEDGER_CONTEXT, BrlAttribution, attribute_brl
from hunter_core.portfolio.marking import (
    MarkedPosition as MarkedPosition,  # re-exported: callers import marking from here too
)
from hunter_core.portfolio.marking import (
    NonLongPosition as NonLongPosition,  # re-exported for the same reason
)
from hunter_core.portfolio.marking import mark_positions as mark_positions  # re-exported
from hunter_core.portfolio.opening import (
    PAPER_FX_POLICY,
    FxObservationRejected,
    FxPolicy,
    validate_fx_observation,
)
from hunter_core.portfolio.positions import market_identity as market_identity  # re-exported
from hunter_core.portfolio.positions import to_open_positions as to_open_positions  # re-exported
from hunter_core.portfolio.positions import (
    to_pending_entries as to_pending_entries,  # re-exported
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.portfolio.state import PortfolioStateBuild

log = get_logger(__name__)

_ZERO = Decimal(0)

BrlUnavailableReason = Literal["no_fx_observation", "fx_rejected"]


class EquityPoint(BaseModel):
    """One point of the curve, as it was written, with its BRL reading."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: uuid.UUID
    ts: datetime
    resolution: Timeframe
    cash: Decimal
    equity: Decimal
    exposure_notional: Decimal
    unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    peak_equity: Decimal
    open_positions: int
    fx_observation_id: uuid.UUID | None
    """The observation this point was **converted with**. Null when there was
    none, and null when the one offered was refused: naming an observation the
    BRL figure did not come from would be provenance that lies."""

    brl: BrlAttribution | None
    brl_unavailable_reason: BrlUnavailableReason | None
    brl_unavailable_detail: str | None
    """Which rule refused the observation, in the validator's own words."""


async def record_equity_point(
    session: AsyncSession,
    *,
    build: PortfolioStateBuild,
    fx: FxObservation | None,
    resolution: Timeframe = REFERENCE_RESOLUTION,
    fx_policy: FxPolicy = PAPER_FX_POLICY,
) -> EquityPoint:
    """Append ``build`` to the curve, converting to BRL only if ``fx`` may.

    **The USDT point is always written**, with or without a rate: refusing to
    record the patrimony because the BRL side is unavailable would lose the very
    history the curve exists for, and FX unavailable after the opening leaves
    USDT computable and BRL *unavailable with a reason* (M3 joint decision, item
    1).

    **The rate is validated against this point's own instant**, with the same
    policy the opening uses: pair, source, causality and the two ages. Astra's
    counter-example (review of this diff, must-fix D): rebuilding the point of
    10:00 from an observation that only became available at 11:00 would fold
    future information into a stored BRL figure and report no unavailability at
    all. A refused observation is not recorded as the point's rate either - the
    stored ``fx_observation_id`` is what the number came from, or nothing.
    """
    brl: BrlAttribution | None = None
    reason: BrlUnavailableReason | None = None
    detail: str | None = None
    if fx is None:
        reason = "no_fx_observation"
    else:
        try:
            validate_fx_observation(fx, as_of=build.as_of, policy=fx_policy)
        except FxObservationRejected as refusal:
            reason, detail = "fx_rejected", refusal.reason
        else:
            brl = attribute_brl(
                equity=build.equity,
                credited=build.credited,
                opening_rate=build.opening_rate,
                current_rate=fx.rate,
            )
    if reason is not None:
        payload: dict[str, object] = {
            "reason": reason,
            "detail": detail,
            "resolution": resolution.value,
        }
        if fx is not None:
            # The observation that failed the check — never the number the
            # point ends up storing, since a refused rate is never stored.
            payload["rejected_fx_observation_id"] = str(fx.id)
        await _audit_unavailability(
            session,
            build,
            action="portfolio.equity_point.brl_unavailable",
            log_event="equity_point_brl_unavailable",
            payload=payload,
        )
    if build.stale_marks:
        await _audit_unavailability(
            session,
            build,
            action="portfolio.equity_point.stale_marks",
            log_event="equity_point_stale_marks",
            payload={
                "resolution": resolution.value,
                "market_ids": [str(market_id) for market_id in build.stale_marks],
            },
        )

    exposure_pct = None
    drawdown_pct = None
    with localcontext(LEDGER_CONTEXT):
        if build.equity > 0:
            exposure_pct = build.exposure_notional / build.equity
            if build.peak_equity > 0 and build.equity < build.peak_equity:
                drawdown_pct = (build.peak_equity - build.equity) / build.peak_equity
            else:
                drawdown_pct = _ZERO

    converted_with = fx.id if brl is not None and fx is not None else None
    await EquitySnapshotRepository(session, build.organization_id).record(
        portfolio_id=build.portfolio_id,
        ts=build.as_of,
        cash=build.cash,
        equity=build.equity,
        exposure_notional=build.exposure_notional,
        exposure_pct=exposure_pct,
        unrealized_pnl=build.unrealized_pnl,
        realized_pnl_cum=build.realized_pnl_cum,
        peak_equity=build.peak_equity,
        drawdown_pct=drawdown_pct,
        open_positions=build.open_position_count,
        fx_observation_id=converted_with,
        resolution=resolution,
    )

    return EquityPoint(
        portfolio_id=build.portfolio_id,
        ts=ensure_utc(build.as_of),
        resolution=resolution,
        cash=build.cash,
        equity=build.equity,
        exposure_notional=build.exposure_notional,
        unrealized_pnl=build.unrealized_pnl,
        realized_pnl_cum=build.realized_pnl_cum,
        peak_equity=build.peak_equity,
        open_positions=build.open_position_count,
        fx_observation_id=converted_with,
        brl=brl,
        brl_unavailable_reason=reason,
        brl_unavailable_detail=detail,
    )


async def _audit_unavailability(
    session: AsyncSession,
    build: PortfolioStateBuild,
    *,
    action: str,
    log_event: str,
    payload: dict[str, object],
) -> None:
    """Structured log plus :class:`AuditEvent` for a point this ledger could not
    build in full — a refused rate or a mark it had to carry stale.

    Neither ``brl_unavailable_reason`` nor ``stale_marks`` has a column of its
    own on ``portfolio_equity_snapshots`` yet (adversarial review of
    ``8a6a69f``, deve-corrigir 5); until T3.1c adds one, this audit row plus the
    log line are what make a degraded point distinguishable, after the fact,
    from a healthy one whose ``fx_observation_id`` merely happens to be null.

    ``payload`` carries ``resolution`` (Astra's follow-up on this same review):
    the snapshot's primary key is ``(portfolio_id, resolution, ts)``, not just
    ``(portfolio_id, ts)``, and two lanes sampled at the same instant — a ``1m``
    point and the ``1h`` reference — must not collapse into one row here just
    because ``entity_id`` and ``ts`` happen to match.
    """
    log.warning(log_event, portfolio_id=str(build.portfolio_id), **payload)
    await SqlAuditSink(session).record(
        AuditEvent(
            actor_type="system",
            actor_id="system",
            organization_id=build.organization_id,
            action=action,
            entity_type="portfolio",
            entity_id=str(build.portfolio_id),
            after=payload,
            metadata={"ts": ensure_utc(build.as_of).isoformat()},
            ts=ensure_utc(build.as_of),
        )
    )
