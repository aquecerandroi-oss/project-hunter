"""The order cycle: an approved proposal with a standing reservation becomes a fill.

One approved proposal gets **one attempt** (RISK_ENGINE.md §10, M3 joint
decision item 3): whatever does not fill is cancelled for good, there is no
automatic parcelling, and the ``orders`` row — keyed ``entry:{proposal_id}`` — is
what makes that terminal across a restart and a redelivery alike.

Three refusals happen *before* the attempt is spent, and each is a different
thing:

- **blocked** — the kill switch re-read in this very transaction blocks entries.
  The reservation is left alone here; releasing pendings is the kill switch
  cycle's own job, audited as such;
- **deferred** — the SPOT market picture is incomplete (no book, no usable print,
  no ``avgPrice`` for the ``NOTIONAL`` filter). Nothing is written and nothing is
  spent: the proposal is looked at again next second and, if the data never
  arrives, the 30 s reservation expires and is released **with its reason**. A
  transient absence must not burn a decision, and no absence may ever produce a
  fill;
- **reservation_closed** — the reservation died between the decision and here
  (the ``expired × consumed`` race). ``ReservationCycleClosed`` on the fill path
  means *the reservation died, do not settle*, and it is **never retried**
  (adversarial review of 2026-09-07, condition 3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.admission.reservation import ReservationCycleClosed, close_reservation
from hunter_core.domain.enums import ReservationState
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.logging import get_logger
from hunter_core.risk.scopes import effective_state
from hunter_execution_worker import metrics
from hunter_execution_worker.apply import EntryApplication, apply_entry
from hunter_execution_worker.entry_inputs import missing_inputs
from hunter_execution_worker.positions import load_open_position
from hunter_execution_worker.reference import MarketReference, load_market
from hunter_risk.decision import RiskDecision

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.risk.scopes import EffectiveKillSwitch
    from hunter_execution_worker.market_data import SpotMarketData
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["EntryOutcome", "execute_approved_entries"]

logger = get_logger(__name__)
_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class EntryOutcome:
    """What one approved proposal produced this cycle."""

    proposal_id: uuid.UUID
    status: str
    reason: str = ""
    application: EntryApplication | None = None


@dataclass(frozen=True, slots=True)
class _Approved:
    proposal_id: uuid.UUID
    market_id: uuid.UUID
    decision: RiskDecision
    decided_at: datetime
    reserved_until: datetime | None

    def overdue(self, now: datetime) -> bool:
        """Has the 30 s tenure already run out at ``now``?"""
        return self.reserved_until is not None and self.reserved_until <= now


async def _approved_with_reservation(
    session: AsyncSession, *, wallet: WalletRef
) -> tuple[_Approved, ...]:
    """Approved proposals still holding their reservation, in FIFO order.

    ``reservation_state = 'held'`` closes the "one attempt" half: the first
    attempt closes the cycle (``consumed`` or ``released``), so a proposal that
    was attempted never comes back — the durable guarantee, without a flag.

    **``reserved_until`` is read with it, and it is not decoration.** The state
    says the commitment is standing; the tenure says whether it still may be.
    The guardian's review of ``7ecafd2`` reproduced the gap: a proposal approved
    at 15:30:00 with ``reserved_until`` 15:30:30 was executed by the cycle of
    15:35:00, 270 s after the wallet gave the cash, the slot and the
    participation budget back to everybody else. The row is carried up and the
    cycle expires it here, in the same transaction, instead of filling it.
    """
    rows = await session.execute(
        text(
            "SELECT p.id AS proposal_id, p.market_id, p.risk_decision, p.decided_at, "
            "p.reserved_until FROM trade_proposals p WHERE p.organization_id = :org "
            "AND p.portfolio_id = :pf "
            "AND p.status = 'approved' AND p.reservation_state = 'held' "
            "ORDER BY p.admission_seq FOR UPDATE OF p"
        ),
        {"org": wallet.organization_id, "pf": wallet.portfolio_id},
    )
    return tuple(
        _Approved(
            proposal_id=row.proposal_id,
            market_id=row.market_id,
            decision=RiskDecision.model_validate(row.risk_decision),
            decided_at=row.decided_at,
            reserved_until=row.reserved_until,
        )
        for row in rows
    )


async def execute_approved_entries(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    now: datetime,
    scopes: EffectiveKillSwitch | None = None,
    adapter: PaperExecutionAdapter | None = None,
) -> tuple[EntryOutcome, ...]:
    """Turn every approved, reserved proposal into at most one attempt each."""
    engine = adapter or PaperExecutionAdapter()
    switch = scopes or await effective_state(session, wallet.portfolio_id, lock=True)
    approved = await _approved_with_reservation(session, wallet=wallet)
    outcomes: list[EntryOutcome] = []
    for proposal in approved:
        if proposal.overdue(now):
            outcomes.append(
                await _expire(
                    session,
                    wallet=wallet,
                    proposal=proposal,
                    data=data,
                    now=now,
                    engine=engine,
                )
            )
            continue
        outcomes.append(
            await _execute_one(
                session,
                wallet=wallet,
                proposal=proposal,
                data=data,
                now=now,
                blocked=switch.blocks_entries,
                engine=engine,
            )
        )
    return tuple(outcomes)


async def _expire(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    proposal: _Approved,
    data: SpotMarketData,
    now: datetime,
    engine: PaperExecutionAdapter,
) -> EntryOutcome:
    """Give a dead reservation back, saying which input never arrived.

    The expiry cycle sweeps the same rows every 5 s with a generic motive; this
    one runs in the transaction that *would* have filled, so it is the only
    place that still knows why the entry kept being deferred
    (``no_book``, ``book_before_latency``, ``avg_price_not_collected``). Storing
    that instead of "reserved_until reached" is what turns a wallet that entered
    nothing into a diagnosable fact (review of ``7ecafd2``, suggestion 7).
    """
    missing = await _deferral_reason(session, proposal=proposal, data=data, now=now, engine=engine)
    await close_reservation(
        session,
        organization_id=wallet.organization_id,
        proposal_id=proposal.proposal_id,
        target=ReservationState.EXPIRED,
        now=now,
        reason=f"reserved_until reached with no order; last deferral: {missing or 'none'}",
    )
    logger.warning(
        "entry_reservation_expired",
        proposal_id=str(proposal.proposal_id),
        reserved_until=proposal.reserved_until.isoformat() if proposal.reserved_until else None,
        reason=missing or "none",
    )
    return EntryOutcome(proposal.proposal_id, "expired", missing or "reserved_until_reached")


async def _deferral_reason(
    session: AsyncSession,
    *,
    proposal: _Approved,
    data: SpotMarketData,
    now: datetime,
    engine: PaperExecutionAdapter,
) -> str:
    """Which input this proposal was still waiting for — or an empty string."""
    market = await load_market(session, proposal.market_id)
    if market is None:
        return "market_unknown"
    snapshot = await data.snapshot(market.identity)
    return missing_inputs(
        snapshot, market, policy=engine.policy, decision_at=proposal.decided_at, now=now
    )


async def _execute_one(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    proposal: _Approved,
    data: SpotMarketData,
    now: datetime,
    blocked: bool,
    engine: PaperExecutionAdapter,
) -> EntryOutcome:
    if blocked:
        return EntryOutcome(proposal.proposal_id, "blocked", "kill_switch_blocks_entries")
    market = await load_market(session, proposal.market_id)
    if market is None:
        return EntryOutcome(proposal.proposal_id, "deferred", "market_unknown")
    if await load_open_position(session, wallet=wallet, market_id=market.market_id) is not None:
        # M3 never holds two positions in the same coin (D3, and the 10 %
        # per-coin ceiling). Adding to one would need an averaging rule the
        # contract does not have, so the entry is refused rather than modelled.
        return await _refuse(
            session, wallet=wallet, proposal=proposal, reason="position_exists", now=now
        )
    snapshot = await data.snapshot(market.identity)
    missing = missing_inputs(
        snapshot, market, policy=engine.policy, decision_at=proposal.decided_at, now=now
    )
    if missing:
        logger.warning(
            "entry_deferred",
            proposal_id=str(proposal.proposal_id),
            market=market.identity.symbol,
            reason=missing,
        )
        return EntryOutcome(proposal.proposal_id, "deferred", missing)
    try:
        order = MarketEntryOrder.from_decision(proposal.decision, decision_at=proposal.decided_at)
    except Exception as exc:  # an unapproved decision may not become an order
        logger.error("entry_order_refused", proposal_id=str(proposal.proposal_id), error=str(exc))
        return await _refuse(
            session, wallet=wallet, proposal=proposal, reason="not_an_approved_entry", now=now
        )
    report = engine.submit_market_entry(
        order,
        snapshot.book,
        snapshot.last_trade,
        market.filters,
        market.fees,
        now,
        avg_price=snapshot.avg_price,
    )
    target = ReservationState.CONSUMED if report.filled else ReservationState.RELEASED
    try:
        await close_reservation(
            session,
            organization_id=wallet.organization_id,
            proposal_id=proposal.proposal_id,
            target=target,
            now=now,
            reason=f"entry attempt {report.status}",
        )
    except ReservationCycleClosed as closed:
        # Never retried: the reservation is gone, so the capital it held is
        # gone with it, and settling a fill against it would spend a
        # commitment the wallet already gave back.
        logger.error(
            "entry_reservation_closed",
            proposal_id=str(proposal.proposal_id),
            execution_key=report.execution_key,
            error=str(closed),
        )
        raise
    application = await apply_entry(
        session,
        wallet=wallet,
        market=market,
        order=order,
        report=report,
        now=now,
        source=data.source,
    )
    if report.filled:
        # T3.79: the fill hop -- the admission decision's own decided_at to
        # this attempt's own clock, the instant the fill actually applied.
        metrics.observe_fill_lag(decided_at=proposal.decided_at, filled_at=now)
    return EntryOutcome(proposal.proposal_id, report.status, report.reason, application)


async def _refuse(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    proposal: _Approved,
    reason: str,
    now: datetime,
    market: MarketReference | None = None,
) -> EntryOutcome:
    """Give the reservation back and never look at this proposal again."""
    await close_reservation(
        session,
        organization_id=wallet.organization_id,
        proposal_id=proposal.proposal_id,
        target=ReservationState.RELEASED,
        now=now,
        reason=reason,
    )
    logger.warning("entry_refused", proposal_id=str(proposal.proposal_id), reason=reason)
    return EntryOutcome(proposal.proposal_id, "rejected", reason)
