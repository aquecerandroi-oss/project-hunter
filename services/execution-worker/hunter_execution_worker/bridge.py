"""The shadow → admission bridge: one cycle, one slot, one proposal (T3.14).

What happens in a cycle, in order:

1. every shadow decision this wallet has not filed a proposal for yet is read
   from Postgres (:func:`~hunter_execution_worker.bridge_repo.pending_signals`).
   The **durable queue is that query**: nothing is remembered between cycles, so
   a candidate that lost one cycle is simply still there in the next one, and a
   restart is a no-op (item 4);
2. each one is screened, and every refusal is named, logged and counted
   (:mod:`hunter_execution_worker.bridge_screen`);
3. the survivors are ordered by **D3** — Radar score of the *perpetual* at the
   source bar (higher first, no score last), then estimated entry cost in R
   (lower first), then arrival, then the signal id so the order is total;
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
from hunter_execution_worker.bridge_repo import pending_signals
from hunter_execution_worker.bridge_screen import screen_signal
from hunter_execution_worker.bridge_universe import beta_map
from hunter_execution_worker.config import PRODUCER
from hunter_execution_worker.reference import load_market

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.service import AdmissionResult
    from hunter_execution_worker.bridge_screen import Screened
    from hunter_execution_worker.market_data import SpotMarketData, SpotSnapshot
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["BridgeOutcome", "entry_cost_r", "run_bridge_cycle"]

logger = get_logger(__name__)

_BPS = Decimal(10_000)
_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class _Ranked:
    """A candidate with everything the ordering and the submission need."""

    screened: Screened
    market: MarketReference
    snapshot: SpotSnapshot
    cost_r: Decimal | None


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


def entry_cost_r(screened: Screened, snapshot: SpotSnapshot) -> Decimal | None:
    """D3's second key: what entering costs, measured in R.

    Half the observed spread of the **spot** book (the part the market is telling
    us right now) plus the experiment's own declared slippage and fee hypothesis
    (the part no book can answer without a size), over the distance to the stop.
    ``None`` when the book was not observed — a candidate without a cost sorts
    after the ones with one, exactly like a candidate without a score.
    """
    book = snapshot.book
    entry_ref, stop, costs = screened.entry_ref, screened.stop, screened.assumed_costs
    if book is None or not book.asks or not book.bids or entry_ref is None or stop is None:
        return None
    if costs is None or entry_ref <= stop:
        return None
    mid = (book.bids[0].price + book.asks[0].price) / _TWO
    half_spread = max(Decimal(0), book.asks[0].price - mid)
    hypothesis = entry_ref * (costs.slippage_bps + costs.fee_bps) / _BPS
    return (half_spread + hypothesis) / (entry_ref - stop)


def _priority(item: _Ranked) -> tuple[int, Decimal, int, Decimal, datetime, str]:
    """D3, as a total order. Ties are broken by the signal id so two workers
    ranking the same cycle cannot disagree about who goes first."""
    score = item.screened.score
    cost = item.cost_r
    return (
        0 if score is not None else 1,
        -(score if score is not None else Decimal(0)),
        0 if cost is not None else 1,
        cost if cost is not None else Decimal(0),
        item.screened.signal.emitted_at,
        str(item.screened.signal_id),
    )


def _count(outcome: str) -> None:
    metrics.bridge_candidates_total.labels(outcome=outcome).inc()


async def _rank(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    now: datetime,
    result: BridgeOutcome,
) -> list[_Ranked]:
    """Screen every pending signal and order the survivors by D3."""
    ranked: list[_Ranked] = []
    for signal in await pending_signals(session, wallet=wallet, now=now):
        screened = await screen_signal(session, wallet=wallet, signal=signal, now=now)
        if not screened.eligible or screened.spot_market_id is None:
            reason = screened.refused or "spot_pair_unavailable"
            result.refusals.append(reason)
            _count(reason)
            continue
        market = await load_market(session, screened.spot_market_id)
        if market is None:  # pragma: no cover - the pair was just read from markets
            result.refusals.append("spot_market_unknown")
            _count("spot_market_unknown")
            continue
        snapshot = await data.snapshot(market.identity)
        ranked.append(
            _Ranked(
                screened=screened,
                market=market,
                snapshot=snapshot,
                cost_r=entry_cost_r(screened, snapshot),
            )
        )
    ranked.sort(key=_priority)
    return ranked


def _request(chosen: _Ranked, *, wallet: WalletRef) -> ProposalRequest:
    """The admission request of one shadow signal.

    ``requested_notional`` is deliberately absent: the ceiling is the engine's to
    compute, and a bridge that proposed a size would be sizing the entry itself.
    The signal's own target travels as ``ProposalRequest.target``
    (``0009_paper_geometry``, DATABASE.md §21.6, closing the pendency
    ``notes-T3.14.md`` §5.1 registered) — ``signal_id`` also travels, so the
    level stays reachable by a join even where the payload is absent.
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
        target=screened.signal.target,
        requested_notional=None,
        assumed_costs=costs,
        agent_id=screened.agent_id,
        signal_id=screened.signal_id,
        actor_id=PRODUCER,
        actor_type="worker",
    )


async def _submit(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    chosen: _Ranked,
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
        # Deferred, not refused: nothing is written, the slot is not spent, and
        # the candidate is read again next cycle while its window is open.
        result.deferred = liquidity
        _count(liquidity)
        logger.info(
            "bridge_candidate_deferred",
            signal_id=str(screened.signal_id),
            market=chosen.market.identity.symbol,
            reason=liquidity,
        )
        return
    marks, _positions = await marks_for_open_positions(
        session, wallet=wallet, data=data, policy=adapter.policy.marking_policy, now=now
    )
    prices = prices_with(marks, market_id=spot.market_id, price=liquidity.last_price)
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
    )
    if not admitted:  # pragma: no cover - decide_requests only skips unknown markets
        return
    result.submitted = admitted[0]
    result.signal_id = screened.signal_id
    _count("approved" if admitted[0].approved else "rejected")
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
) -> BridgeOutcome:
    """One slot: screen, order by D3, submit at most one proposal."""
    engine = adapter or PaperExecutionAdapter()
    result = BridgeOutcome()
    ranked = await _rank(session, wallet=wallet, data=data, now=now, result=result)
    result.candidates = len(ranked)
    if not ranked:
        return result
    chosen, waiting = ranked[0], ranked[1:]
    result.waiting = len(waiting)
    for item in waiting:
        _count("waiting")
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
