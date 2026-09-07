"""The one path that admits a proposal — T3.12.

Everything an entry needs happens here, in **one** transaction, under the
contract's fixed lock order (system -> organization -> portfolio):

1. the origin is resolved and refused if it may not become a proposal at all;
2. a replay is answered with the stored decision, without re-evaluating;
3. the wallet is locked (``portfolio_risk_state``), and only then is the state
   read, are dead reservations expired, and is the participation budget summed —
   a state read before the lock is a state that was already false when it
   arrived (M3 joint decision, item 4);
4. the pure engine decides (``hunter_risk.evaluate``);
5. the decision, its FIFO place, the reservation, the audit row and the outbox
   event are written **together**. Either all of them are true or none is.

Two things are deliberately *not* here. There is no network under the lock: the
event is queued in the outbox and published later by its dispatcher. And the
durable kill-switch latch is not moved from here — see :data:`_DETECTORS`, which
records why the contract's "the check is also the detector" cannot be honoured
from this path under the privileges the schema grants today.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from hunter_core.admission.decide import decide_pending
from hunter_core.admission.dedupe import (
    AdmittedProposal,
    ensure_pending_is_the_same_request,
    ensure_same_request,
    find_admitted,
    find_pending,
)
from hunter_core.admission.inputs import unmeasured_decision, verify_market
from hunter_core.admission.participation import ParticipationRepository
from hunter_core.admission.record import (
    hold_reservation,
    insert_proposal,
    next_admission_seq,
    record_decision,
    set_admission_seq,
)
from hunter_core.admission.reservation import expire_reservations
from hunter_core.admission.sources import ProposalRequest, admission_key, resolve_source
from hunter_core.domain.enums import ProposalSource, ProposalStatus, ReservationState
from hunter_core.domain.types import ensure_utc, uuid7
from hunter_core.logging import get_logger
from hunter_core.portfolio.state import build_portfolio_state
from hunter_core.risk.scopes import effective_state
from hunter_risk.decision import RiskDecision
from hunter_risk.evaluate import evaluate
from hunter_risk.inputs import EntryProposal
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.enums import KillSwitchState
    from hunter_risk.inputs import BetaEstimate, MarketLiquidity, MarketSpec
    from hunter_risk.limits import RiskLimits

__all__ = ["AdmissionResult", "admit"]

logger = get_logger(__name__)


class AdmissionResult(BaseModel):
    """What one admission produced, decided or replayed."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    organization_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    source: ProposalSource
    status: ProposalStatus
    admission_seq: int | None
    decision: RiskDecision
    reservation_state: ReservationState
    reserved_notional: Decimal | None = None
    reserved_cash: Decimal | None = None
    reserved_risk: Decimal | None = None
    reserved_until: datetime | None = None
    decided_at: datetime
    replayed: bool = False
    """True when this answer came from a row that already existed."""

    unavailable: tuple[str, ...] = ()
    """Why the wallet could not be fully measured, in the panel's words."""

    @property
    def approved(self) -> bool:
        return self.decision.approved


def _replay(existing: AdmittedProposal, organization_id: uuid.UUID) -> AdmissionResult:
    return AdmissionResult(
        proposal_id=existing.proposal_id,
        organization_id=organization_id,
        portfolio_id=existing.portfolio_id,
        market_id=existing.market_id,
        source=existing.source,
        status=existing.status,
        admission_seq=existing.admission_seq,
        decision=existing.decision,
        reservation_state=existing.reservation_state,
        reserved_notional=existing.reserved_notional,
        reserved_cash=existing.reserved_cash,
        reserved_risk=existing.reserved_risk,
        reserved_until=existing.reserved_until,
        decided_at=existing.decided_at,
        replayed=True,
    )


def _waited_since(started: float) -> timedelta:
    """How long the wallet lock was actually waited for, from a monotonic clock.

    Added to the evaluation instant, so waiting behind another admission cannot
    make a book look *younger* than it is: every age the engine measures is
    measured against ``as_of``, and the wait is real time (Astra, T3.12 review).
    The whole duration, not whole seconds — with a book already 9,8 s old and a
    wait of 0,4 s, rounding the wait to zero is precisely the case that slips a
    10,2 s book past a 10 s limit (Astra, diff review, finding 2).

    ``time.monotonic`` rather than the wall clock: an NTP step during the wait
    must not become a jump in the age of a market observation.
    """
    return timedelta(seconds=max(0.0, time.monotonic() - started))


_DETECTORS = ("daily_loss", "drawdown")
"""RISK_ENGINE.md §3.1: "Reprovar em 16 ou 17 também **aciona** a transição de
kill switch (§5) — o check não é só um veto, é o detector".

**Not done here, and the reason is a privilege, not a preference.** The move
would be ``hunter_core.risk.kill_switch.evaluate_and_persist`` in this very
transaction, which is what the contract asks for (Astra, diff review, finding
3) — but it writes ``portfolios.kill_switch_state``, and that table is
``hunter_app``'s (``ddl/tables.py``: ``APP_WRITE_TABLES``), while admission has
to run as ``hunter_worker`` to advance ``fifo_v1`` on ``portfolio_risk_state``,
which is the worker's. The two halves of the same evaluation live in two roles
that cannot be combined in one transaction, and forcing it turns an honest
rejection into *permission denied for table portfolios* — a 500 in place of a
recorded decision.

So the latch is left to whoever can write it, the rejection is recorded with the
loss that produced it, and the contradiction is escalated instead of papered
over (notes-T3.12.md §2, coupling D). ``test_a_rejection_by_daily_loss_records_
the_loss_without_latching`` is the characterisation of what happens today.
"""


async def admit(
    session: AsyncSession,
    request: ProposalRequest,
    *,
    source: str | ProposalSource,
    liquidity: MarketLiquidity,
    spec: MarketSpec,
    beta: BetaEstimate,
    prices: Mapping[uuid.UUID, Decimal],
    exit_cost_rate: Decimal,
    now: datetime,
    betas: Mapping[uuid.UUID, Decimal] | None = None,
    limits: RiskLimits = PAPER_V1,
    system: KillSwitchState | None = None,
) -> AdmissionResult:
    """Admit one entry proposal, or refuse it — the only way capital is committed.

    ``prices`` and ``betas`` are the caller's declared price source and beta
    revision, exactly as ``build_portfolio_state`` requires them: a ledger that
    fetched them would be choosing them silently. ``liquidity`` arrives without
    the participation figure, which is read here from the durable log and
    written into it: a pure function cannot see the other proposals of the same
    cycle, and a ceiling counted per order would be the splitting the directive
    forbids.
    """
    moment = ensure_utc(now)
    origin = request.origin(resolve_source(source))
    key = admission_key(origin, request.client_key)
    org = request.organization_id

    existing = await find_admitted(session, organization_id=org, idempotency_key=key)
    if existing is not None:
        ensure_same_request(existing, request, origin)
        return _replay(existing, org)

    await verify_market(session, request)
    started = time.monotonic()
    scopes = await effective_state(session, request.portfolio_id, system=system, lock=True)
    as_of = moment + _waited_since(started)

    existing = await find_admitted(session, organization_id=org, idempotency_key=key)
    if existing is not None:
        ensure_same_request(existing, request, origin)
        return _replay(existing, org)

    await expire_reservations(
        session, organization_id=org, portfolio_id=request.portfolio_id, now=as_of
    )
    build = await build_portfolio_state(
        session,
        organization_id=org,
        portfolio_id=request.portfolio_id,
        as_of=as_of,
        marks=prices,
        exit_cost_rate=exit_cost_rate,
        betas=betas,
    )
    used = await ParticipationRepository(session, org).used(
        portfolio_id=request.portfolio_id,
        market_id=request.market_id,
        cut=as_of - timedelta(seconds=limits.participation_window_s),
    )
    # The API files the request and the engine decides **that row** (§19.4), so
    # the proposal's identity is the filed row's whenever there is one.
    pending = await find_pending(session, organization_id=org, idempotency_key=key)
    if pending is not None:
        ensure_pending_is_the_same_request(pending, request, origin)
    proposal_id = pending.proposal_id if pending is not None else uuid7()
    if build.state is None:
        decision = unmeasured_decision(
            request,
            proposal_id=proposal_id,
            limits=limits,
            scopes=scopes,
            beta_validated=beta.validated,
            reasons=build.unavailable,
        )
    else:
        decision = evaluate(
            EntryProposal(
                proposal_id=proposal_id,
                portfolio_id=request.portfolio_id,
                agent_id=request.agent_id,
                market=request.market,
                direction=request.direction,
                entry_ref=request.entry_ref,
                stop=request.stop,
                requested_notional=request.requested_notional,
                assumed_costs=request.assumed_costs,
                agent_enabled=request.agent_enabled,
                signal_valid=request.signal_valid,
            ),
            build.state,
            limits,
            liquidity.model_copy(update={"participation_used_quote": used}),
            KillSwitchInputs(
                system=scopes.system,
                organization=scopes.organization,
                portfolio=scopes.portfolio,
            ),
            beta,
            spec=spec,
        )

    written = (
        await decide_pending(
            session,
            request,
            proposal_id=proposal_id,
            source=origin,
            decision=decision,
            scopes=scopes,
            as_of=as_of,
        )
        if pending is not None
        else await insert_proposal(
            session,
            request,
            proposal_id=proposal_id,
            source=origin,
            key=key,
            decision=decision,
            scopes=scopes,
            as_of=as_of,
        )
    )
    if not written:
        # Another transaction committed this key while this one was deciding: it
        # waited on the unique index rather than on the wallet lock. Nothing has
        # been reserved or counted yet, so the loser answers with the winner's
        # decision and takes no place in the queue.
        existing = await find_admitted(session, organization_id=org, idempotency_key=key)
        if existing is None:  # pragma: no cover - the conflict proves the row is there
            raise RuntimeError(f"idempotency key {key} conflicted but no proposal was found")
        ensure_same_request(existing, request, origin)
        return _replay(existing, org)

    seq = await next_admission_seq(session, organization_id=org, portfolio_id=request.portfolio_id)
    await set_admission_seq(session, organization_id=org, proposal_id=proposal_id, seq=seq)
    reservation = None
    if decision.approved and decision.sizing is not None:
        reservation = await hold_reservation(
            session,
            request,
            proposal_id=proposal_id,
            notional=decision.sizing.notional,
            risk=decision.sizing.planned_risk_quote,
            as_of=as_of,
        )
    await record_decision(
        session,
        request,
        proposal_id=proposal_id,
        source=origin,
        decision=decision,
        seq=seq,
        reservation=reservation,
        scopes=scopes,
        as_of=as_of,
        unavailable_reasons=build.unavailable,
    )
    return AdmissionResult(
        proposal_id=proposal_id,
        organization_id=org,
        portfolio_id=request.portfolio_id,
        market_id=request.market_id,
        source=origin,
        status=ProposalStatus.APPROVED if decision.approved else ProposalStatus.REJECTED,
        admission_seq=seq,
        decision=decision,
        reservation_state=(
            ReservationState.HELD if reservation is not None else ReservationState.NONE
        ),
        reserved_notional=reservation.notional if reservation else None,
        reserved_cash=reservation.cash if reservation else None,
        reserved_risk=reservation.risk if reservation else None,
        reserved_until=reservation.until if reservation else None,
        decided_at=as_of,
        unavailable=build.unavailable,
    )
