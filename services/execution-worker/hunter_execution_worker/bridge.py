"""The shadow → admission bridge: one cycle, one slot, one proposal (T3.14).

What happens in a cycle, in order:

1. every shadow decision this wallet has not filed a proposal for yet is read
   from Postgres (:func:`~hunter_execution_worker.bridge_repo.pending_signals`).
   The **durable queue is that query**: nothing is remembered between cycles, so
   a candidate that lost one cycle is simply still there in the next one, and a
   restart is a no-op (item 4);
2. each one is screened, and every refusal is named, logged and counted
   (:mod:`hunter_execution_worker.bridge_screen`);
3. the survivors are ordered by **D3**
   (:mod:`hunter_execution_worker.bridge_rank`);
4. the **first one only** is submitted, through the same admission service the
   operator's order goes through. One slot per cycle (D3); the others stay
   eligible while their 120 s window is open.

Two properties are deliberate and worth stating.

**The chosen one is not replaced when its book is missing.** A candidate whose
market data cannot be assembled is *deferred*, and the cycle submits nothing —
promoting the runner-up would mean the entry that got capital was decided by a
transient read of the hot state rather than by D3.

**Idempotency is not the guard's job alone.** ``client_key`` is
``shadow:{signal_id}``, so the same signal always mints the same
``trade_proposals.idempotency_key``: a redelivered event, a restart mid-cycle or
two workers racing all converge on one proposal, and the second attempt is
answered with the first one's decision instead of taking a second FIFO place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.admission.sources import ProposalRequest
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.logging import get_logger
from hunter_execution_worker import metrics
from hunter_execution_worker.admission_cycle import RequestInputs, decide_requests
from hunter_execution_worker.bridge_inputs import (
    liquidity_for,
    marks_for_open_positions,
    prices_with,
)
from hunter_execution_worker.bridge_rank import Ranked, count_outcome, rank_candidates
from hunter_execution_worker.bridge_universe import beta_map
from hunter_execution_worker.config import PRODUCER
from hunter_execution_worker.risk_profile import wallet_limits

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.service import AdmissionResult
    from hunter_execution_worker.market_data import SpotMarketData
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["BridgeOutcome", "run_bridge_cycle"]

logger = get_logger(__name__)

_BPS = Decimal(10_000)
_TWO = Decimal(2)


@dataclass(slots=True)
class BridgeOutcome:
    """What one bridge cycle did, in the words the counter uses."""

    submitted: AdmissionResult | None = None
    signal_id: uuid.UUID | None = None
    candidates: int = 0
    waiting: int = 0
    refusals: list[str] = field(default_factory=lambda: [])
    deferred: str | None = None

    @property
    def approved(self) -> bool:
        return self.submitted is not None and self.submitted.approved


def _request(chosen: Ranked, *, wallet: WalletRef) -> ProposalRequest:
    """The admission request of one shadow signal.

    ``requested_notional`` is deliberately absent: the ceiling is the engine's to
    compute, and a bridge that proposed a size would be sizing the entry itself.
    The signal's own target travels as ``ProposalRequest.target``
    (``0009_paper_geometry``, DATABASE.md §21.6, closing the pendency
    ``notes-T3.14.md`` §5.1 registered) — ``signal_id`` also travels, so the
    level stays reachable by a join even where the payload is absent.

    ``entry_ref``/``stop``/``target`` are read off ``screened``, not
    ``screened.signal``: for a scaled perpetual (``1000SHIBUSDT``, item 4)
    ``Screened`` already divides the frozen levels by the spot market's scale.
    """
    screened = chosen.screened
    entry_ref, stop, costs = screened.entry_ref, screened.stop, screened.assumed_costs
    if entry_ref is None or stop is None or costs is None:  # pragma: no cover
        # Unreachable: ``_geometry_reason`` refuses all three before a signal can
        # become a candidate. Raising rather than asserting because an ``assert``
        # disappears under ``-O``, and this is the guard on the numbers that
        # decide money.
        raise RuntimeError(f"signal {screened.signal_id} reached submission without its geometry")
    return ProposalRequest(
        client_key=f"shadow:{screened.signal_id}",
        organization_id=wallet.organization_id,
        portfolio_id=wallet.portfolio_id,
        market_id=chosen.market.market_id,
        market=chosen.market.identity,
        # The signal's own direction, not a constant: ``_geometry_reason`` has
        # already refused anything but LONG (spot, long-only in M3), and reading
        # it back keeps the request a copy of the decision rather than a claim
        # about it.
        direction=screened.signal.direction,
        entry_ref=entry_ref,
        stop=stop,
        target=screened.target,
        requested_notional=None,
        assumed_costs=costs,
        agent_id=screened.agent_id,
        signal_id=screened.signal_id,
        actor_id=PRODUCER,
        actor_type="worker",
    )


def _defer(result: BridgeOutcome, chosen: Ranked, reason: str, **extra: object) -> None:
    """Deferred, not refused: nothing is written, the slot is not spent, and the
    candidate is read again next cycle while its 120 s window is open."""
    result.deferred = reason
    count_outcome(reason)
    logger.info(
        "bridge_candidate_deferred",
        signal_id=str(chosen.screened.signal_id),
        market=chosen.market.identity.symbol,
        reason=reason,
        **extra,
    )


async def _submit(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    chosen: Ranked,
    data: SpotMarketData,
    now: datetime,
    exit_cost_rate: Decimal,
    adapter: PaperExecutionAdapter,
    result: BridgeOutcome,
) -> None:
    """Build the market picture and hand the one chosen candidate to ``admit``."""
    screened = chosen.screened
    spot = screened.spot
    if spot is None or screened.beta is None:  # pragma: no cover - screening guarantees both
        return
    liquidity = await liquidity_for(
        session, spot=spot, market=chosen.market, snapshot=chosen.snapshot, now=now
    )
    if isinstance(liquidity, str):
        _defer(result, chosen, liquidity)
        return
    coverage = await marks_for_open_positions(
        session, wallet=wallet, data=data, policy=adapter.policy.marking_policy, now=now
    )
    if not coverage.complete:
        # Admission needs a wallet it can measure: with a position priced at the
        # last durable mark, equity, drawdown and aggregate risk are estimates
        # (T3.29 item 4). Same rule as the manual path.
        _defer(result, chosen, "marks_incomplete", mark_quality=str(coverage.quality))
        return
    resolved = await wallet_limits(session, wallet=wallet)
    if resolved.limits is None:
        # T3.69b: the wallet's limits are its linked ``risk_profiles`` row, and
        # without a usable one nothing is admitted — deferred, so the signal's
        # own window keeps running and the slot is not spent (ACTIVATION.md §8b).
        _defer(result, chosen, resolved.state, detail=resolved.detail)
        return
    prices = prices_with(coverage.marks, market_id=spot.market_id, price=liquidity.last_price)
    betas = await beta_map(session, market_ids=prices.keys(), now=now)
    admitted = await decide_requests(
        session,
        wallet=wallet,
        requests=[
            (
                _request(chosen, wallet=wallet),
                RequestInputs(
                    liquidity=liquidity,
                    beta=screened.beta,
                    prices=prices,
                    betas={key: estimate.value for key, estimate in betas.items()},
                    exit_cost_rate=exit_cost_rate,
                ),
            )
        ],
        now=now,
        source="agent",
        limits=resolved.limits,
    )
    if not admitted:  # pragma: no cover - decide_requests only skips unknown markets
        return
    result.submitted = admitted[0]
    result.signal_id = screened.signal_id
    # T3.79: the admission hop -- the signal's own emitted_at (agent_signals,
    # read into ShadowSignal by bridge_repo) to this decision's decided_at.
    # Only the autonomy path has a signal to time against; a manual request
    # never reaches this function.
    metrics.observe_admission_lag(
        emitted_at=screened.signal.emitted_at, decided_at=admitted[0].decided_at
    )
    count_outcome("approved" if admitted[0].approved else "rejected")
    logger.info(
        "bridge_proposal_submitted",
        signal_id=str(screened.signal_id),
        proposal_id=str(admitted[0].proposal_id),
        market=chosen.market.identity.symbol,
        approved=admitted[0].approved,
        replayed=admitted[0].replayed,
        binding_constraint=(
            None
            if admitted[0].decision.sizing is None
            else admitted[0].decision.sizing.binding_constraint
        ),
        score=str(screened.score) if screened.score is not None else None,
    )


async def run_bridge_cycle(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    now: datetime,
    exit_cost_rate: Decimal,
    adapter: PaperExecutionAdapter | None = None,
    reported: dict[uuid.UUID, str] | None = None,
) -> BridgeOutcome:
    """One slot: screen, order by D3, submit at most one proposal.

    ``reported`` is the per-wallet once-per-(signal, reason) map — see
    :func:`~hunter_execution_worker.bridge_rank.rank_candidates`. ``None``
    logs and counts every refusal every pass.
    """
    engine = adapter or PaperExecutionAdapter()
    result = BridgeOutcome()
    ranked = await rank_candidates(
        session, wallet=wallet, data=data, now=now, refusals=result.refusals, reported=reported
    )
    result.candidates = len(ranked)
    if not ranked:
        return result
    chosen, waiting = ranked[0], ranked[1:]
    result.waiting = len(waiting)
    for item in waiting:
        count_outcome("waiting")
        logger.debug(
            "bridge_candidate_waiting",
            signal_id=str(item.screened.signal_id),
            market=item.market.identity.symbol,
        )
    await _submit(
        session,
        wallet=wallet,
        chosen=chosen,
        data=data,
        now=now,
        exit_cost_rate=exit_cost_rate,
        adapter=engine,
        result=result,
    )
    return result
