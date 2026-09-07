"""Reads that assemble one wallet's list row, summary and anchor — T3.8a.

No new invariant is decided here: every number is read through
``hunter_core.portfolio`` (T3.3) and ``hunter_core.risk`` (T3.6), already
proved under their own tests. This module is the seam that turns their return
shapes into ``hunter_api.schemas.portfolio`` for one HTTP response, inside the
single ``OrgSession`` transaction the request already opened (ARCHITECTURE.md
§9: one pooled connection per request).

There is no tenant repository for *reading* a wallet's summary in
``packages/core`` — ``PortfolioRepository`` there owns the write path (T3.3) —
so this module is that missing read, kept in ``apps/api`` rather than added to
a package this task does not own.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from hunter_api.repositories.base import clamp_page_size, decode_cursor, encode_cursor
from hunter_api.schemas.portfolio import (
    AnchorOut,
    BrlDecompositionOut,
    FxObservationOut,
    KillSwitchSummaryOut,
    PortfolioListItemOut,
    PortfolioRiskStateOut,
    PortfolioSummaryOut,
)
from hunter_api.schemas.risk import ScopeStatesOut, TransitionOut
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.repositories.ledger import LedgerRepository
from hunter_core.db.repositories.portfolio import PortfolioRepository
from hunter_core.domain.types import ensure_utc
from hunter_core.portfolio.attribution import attribute_brl
from hunter_core.portfolio.opening import (
    PAPER_FX_POLICY,
    FxObservationRejected,
    validate_fx_observation,
)
from hunter_core.portfolio.state import PortfolioStateBuild, WalletNotOpen, build_portfolio_state
from hunter_core.risk import effective_state, latest_transition, load_locked_state

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.db.models.fx import FxObservation

_ZERO = Decimal(0)


def _fx_out(observation: FxObservation) -> FxObservationOut:
    return FxObservationOut(
        id=observation.id,
        pair=observation.pair,
        source=observation.source,
        rate=observation.rate,
        observed_at=ensure_utc(observation.observed_at),
        available_at=ensure_utc(observation.available_at),
    )


async def list_portfolios(
    session: AsyncSession, org_id: uuid.UUID, *, limit: int | None, cursor: str | None
) -> tuple[list[PortfolioListItemOut], str | None]:
    """Every live wallet of the organization — today, at most the paper principal."""
    size = clamp_page_size(limit)
    statement = (
        select(Portfolio)
        .where(Portfolio.organization_id == org_id, Portfolio.deleted_at.is_(None))
        .order_by(Portfolio.created_at, Portfolio.id)
    )
    after = decode_cursor(cursor)
    if after is not None:
        statement = statement.where(tuple_(Portfolio.created_at, Portfolio.id) > after)
    rows: Sequence[Portfolio] = (await session.execute(statement.limit(size + 1))).scalars().all()
    page = rows[:size]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > size else None
    items = [
        PortfolioListItemOut(
            id=row.id,
            workspace_id=row.workspace_id,
            name=row.name,
            type=row.type,
            status=row.status,
            is_arena=row.is_arena,
            base_currency=row.base_currency,
            created_at=ensure_utc(row.created_at),
        )
        for row in page
    ]
    return items, next_cursor


async def get_anchor(
    session: AsyncSession, org_id: uuid.UUID, portfolio_id: uuid.UUID
) -> AnchorOut | None:
    anchor = await PortfolioRepository(session, org_id).get_anchor(portfolio_id)
    if anchor is None:
        return None
    fx = await FxObservationRepository(session).get(anchor.fx_observation_id)
    if fx is None:  # pragma: no cover - the anchor's FK is RESTRICT, never SET NULL
        raise LookupError(f"anchor of portfolio {portfolio_id} names a missing fx_observation")
    return AnchorOut(
        portfolio_id=anchor.portfolio_id,
        origin_currency=anchor.origin_currency,
        origin_amount=anchor.origin_amount,
        operating_currency=anchor.operating_currency,
        credited_amount=anchor.credited_amount,
        rate=anchor.rate,
        conversion_residual=anchor.conversion_residual,
        rounding_policy=anchor.rounding_policy,
        anchored_at=ensure_utc(anchor.anchored_at),
        fx_observation=_fx_out(fx),
    )


async def _brl_reading(
    build: PortfolioStateBuild, session: AsyncSession, as_of: datetime
) -> tuple[BrlDecompositionOut | None, str | None, str | None]:
    """The wallet's *live* BRL reading — mirrors ``hunter_core.portfolio.ledger.
    record_equity_point`` exactly, without writing a curve point.

    Returns ``(decomposition, reason, detail)``; exactly one of the first and
    the other two is not ``None`` (M3 joint decision, item 1: BRL is either
    read or unavailable with a reason, never guessed).
    """
    fx = await FxObservationRepository(session).latest_available(
        pair=PAPER_FX_POLICY.pair, source=PAPER_FX_POLICY.source, as_of=as_of
    )
    if fx is None:
        return None, "no_fx_observation", None
    try:
        validate_fx_observation(fx, as_of=as_of, policy=PAPER_FX_POLICY)
    except FxObservationRejected as refusal:
        return None, "fx_rejected", refusal.reason
    attribution = attribute_brl(
        equity=build.equity,
        credited=build.credited,
        opening_rate=build.opening_rate,
        current_rate=fx.rate,
    )
    return (
        BrlDecompositionOut(
            opening_brl=attribution.opening_brl,
            operational_brl=attribution.operational_brl,
            currency_brl=attribution.currency_brl,
            equity_brl=attribution.equity_brl,
            total_brl=attribution.total_brl,
            opening_rate=attribution.opening_rate,
            current_rate=attribution.current_rate,
            fx_observation=_fx_out(fx),
        ),
        None,
        None,
    )


async def _kill_switch_summary(
    session: AsyncSession, portfolio_id: uuid.UUID
) -> KillSwitchSummaryOut:
    scopes = await effective_state(session, portfolio_id)
    reason = await session.scalar(
        select(Portfolio.kill_switch_reason).where(Portfolio.id == portfolio_id)
    )
    transition = await latest_transition(session, portfolio_id)
    return KillSwitchSummaryOut(
        effective=scopes.effective,
        blocks_entries=scopes.blocks_entries,
        scopes=ScopeStatesOut(
            system=scopes.system, organization=scopes.organization, portfolio=scopes.portfolio
        ),
        reason=reason,
        last_transition=None
        if transition is None
        else TransitionOut(
            from_state=transition.from_state,
            to_state=transition.to_state,
            reason=transition.reason,
            actor_type=transition.actor_type,
            actor_id=transition.actor_id,
            evidence=transition.evidence,
            created_at=transition.created_at,
        ),
    )


async def build_summary(
    session: AsyncSession, org_id: uuid.UUID, portfolio_id: uuid.UUID, as_of: datetime
) -> PortfolioSummaryOut | None:
    """The whole wallet at ``as_of``, or ``None`` for "not this organization's"."""
    wallet = await PortfolioRepository(session, org_id).get(portfolio_id)
    if wallet is None:
        return None
    try:
        build = await build_portfolio_state(
            session,
            organization_id=org_id,
            portfolio_id=portfolio_id,
            as_of=as_of,
            marks={},
            exit_cost_rate=_ZERO,
        )
    except WalletNotOpen:
        # A ``portfolios`` row with no lock row and/or no anchor was never
        # really opened (``hunter_core.portfolio.opening`` is the only writer
        # of both, atomically) — the same 404 as "not this organization's".
        return None

    reservations = await LedgerRepository(session, org_id).held_reservations(portfolio_id)
    reserved_notional = sum((row.reserved_notional for row in reservations), _ZERO)
    reserved_cash = sum((row.reserved_cash for row in reservations), _ZERO)
    reserved_risk = sum((row.reserved_risk for row in reservations), _ZERO)

    brl, brl_reason, brl_detail = await _brl_reading(build, session, as_of)
    kill_switch = await _kill_switch_summary(session, portfolio_id)
    locked = await load_locked_state(session, portfolio_id)

    risk_state = PortfolioRiskStateOut(
        trading_day=locked.trading_day,
        trading_day_timezone=locked.trading_day_timezone,
        trading_day_start_utc=locked.trading_day_start_utc,
        equity_day_start=locked.equity_day_start,
        day_reference_observed_at=locked.day_reference_observed_at,
        peak_equity=locked.peak_equity,
        peak_equity_observed_at=locked.peak_equity_at,
        peak_sampling_interval_s=locked.peak_sampling_interval_s,
        daily_loss_pct=None if build.state is None else build.state.daily_loss_pct,
        drawdown_pct=None if build.state is None else build.state.drawdown_pct,
        kill_switch=kill_switch,
    )
    return PortfolioSummaryOut(
        id=wallet.id,
        organization_id=wallet.organization_id,
        workspace_id=wallet.workspace_id,
        name=wallet.name,
        type=wallet.type,
        status=wallet.status,
        base_currency=wallet.base_currency,
        as_of=ensure_utc(as_of),
        cash=build.cash,
        equity=build.equity,
        exposure_notional=build.exposure_notional,
        unrealized_pnl=build.unrealized_pnl,
        realized_pnl_cum=build.realized_pnl_cum,
        open_position_count=build.open_position_count,
        reserved_cash=reserved_cash,
        reserved_notional=reserved_notional,
        reserved_risk=reserved_risk,
        # Derived from the mark/identity gaps directly, never from ``state is
        # None`` (Astra, review of this diff, MUST-FIX 3): the builder also
        # returns ``state=None`` when only the *daily reference* is missing
        # (state.py, "daily_reference" in unavailable), which says nothing
        # about whether prices were fresh — an all-cash wallet just after
        # midnight has no stale price to report.
        marks_complete=not ({"marks", "market_identity"} & set(build.unavailable)),
        unavailable=list(build.unavailable),
        brl=brl,
        brl_unavailable_reason=brl_reason,
        brl_unavailable_detail=brl_detail,
        risk_state=risk_state,
    )
