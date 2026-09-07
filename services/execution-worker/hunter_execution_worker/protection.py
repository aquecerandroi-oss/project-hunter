"""The protection cycle: what a crossing means, and what it is allowed to sell.

Once a tick of the last valid SPOT trade crosses a protection, the attempt runs
**under the wallet's lock, then the position's own row lock**, and the quantity
it may sell comes from :func:`hunter_core.execution.intents.allocate_sellable`
over every live intention of that position. That is what stops a stop and a
target selling the same unit twice — a short, on spot (RISK_ENGINE.md §10).

Three things keep a fired protection alive until it is really liquidated:

- an attempt that found no usable book leaves the intention ``open`` and
  **degraded**, with an alert. The next cycle retries it with an identity of its
  own, without waiting for a new crossing: the trigger already happened, and
  requiring a second one is how a stop disappears when the tape goes quiet;
- ``pending_stop_*`` on the verdict — a stop crossing seen *behind* the crossing
  that was published — arms the stop in the **same** transaction instead of
  hoping the print survives another age budget (notes-T3.4.md §12.3, round 4);
- a ``manual`` intention (the operator's close, T3.8) needs no trigger at all: it
  *is* the decision to exit, and it uses this same lock and this same intention.

Kill switch: a blocked wallet never stops this cycle. "Travas de entrada não
podem impedir saídas de proteção" is rule 3 of the directive, so the state is not
even read here — the entry cycle is where it binds.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.execution.intents import ExitAttempt, ExitIntent, allocate_sellable
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.execution.triggers import TriggerEvaluation
from hunter_core.logging import get_logger
from hunter_execution_worker.apply import ExitApplication, apply_exit
from hunter_execution_worker.intents_repo import live_intents
from hunter_execution_worker.positions import OpenPositionRow, load_open_positions
from hunter_execution_worker.reference import MarketReference, load_markets
from hunter_execution_worker.triggering import (
    TriggerWatermarks,
    due,
    fired_key,
    protected,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.market_data import SpotMarketData, SpotSnapshot
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["ProtectionOutcome", "TriggerWatermarks", "run_protection_cycle"]

logger = get_logger(__name__)
_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ProtectionOutcome:
    """What one attempt at one intention produced."""

    intent_id: uuid.UUID
    position_id: uuid.UUID
    status: str
    reason: str = ""
    trigger: str = ""
    application: ExitApplication | None = None


async def run_protection_cycle(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    now: datetime,
    watermarks: TriggerWatermarks | None = None,
    adapter: PaperExecutionAdapter | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[ProtectionOutcome, ...]:
    """Evaluate every live position's protections and attempt whatever fired.

    ``clock`` re-stamps the evaluation instant **after** the tape is read. The
    30-minute proof of 2026-09-07 showed why: ``now`` taken at the top of the
    cycle is already in the past by the time the snapshot comes back, so a print
    that landed in between reads as ``trade_from_the_future`` and the whole batch
    goes ``unavailable`` — a stop delayed by a cycle for no reason but our own
    bookkeeping. Without a clock the instant stays exactly ``now``, which is what
    every test wants (spec §12, trap 2: no wall clock in a test).
    """
    engine = adapter or PaperExecutionAdapter()
    marks = watermarks or TriggerWatermarks()
    positions = await load_open_positions(session, wallet=wallet, lock=True)
    if not positions:
        return ()
    markets = await load_markets(session, {position.market_id for position in positions})
    outcomes: list[ProtectionOutcome] = []
    for position in positions:
        market = markets.get(position.market_id)
        if market is None:  # pragma: no cover - a position always names a market
            logger.error("protection_market_unknown", position_id=str(position.position_id))
            continue
        snapshot = await data.snapshot(market.identity)
        outcomes.extend(
            await _protect_one(
                session,
                wallet=wallet,
                position=position,
                market=market,
                snapshot=snapshot,
                now=max(now, clock()) if clock is not None else now,
                marks=marks,
                engine=engine,
                source=data.source,
            )
        )
    return tuple(outcomes)


async def _protect_one(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    position: OpenPositionRow,
    market: MarketReference,
    snapshot: SpotSnapshot,
    now: datetime,
    marks: TriggerWatermarks,
    engine: PaperExecutionAdapter,
    source: str,
) -> list[ProtectionOutcome]:
    intents = await live_intents(
        session, wallet=wallet, market=market, position_id=position.position_id, lock=True
    )
    if not intents:
        logger.error(
            "position_without_protection",
            position_id=str(position.position_id),
            market=market.identity.symbol,
        )
        return []
    evaluation = engine.check_triggers(
        protected(position, intents),
        snapshot.trades,
        now,
        tape_gap=snapshot.tape_gap,
        last_accepted_trade_id=marks.get(market.market_id),
    )
    marks.advance(market.market_id, evaluation.accepted_trade_id)
    if evaluation.state == "unavailable":
        logger.warning(
            "protection_tape_unavailable",
            position_id=str(position.position_id),
            reason=evaluation.reason,
        )
    fired = fired_key(evaluation)
    pending_stop = evaluation.pending_stop_trade_id is not None
    allocations = dict(allocate_sellable(intents, position_qty=position.qty))
    outcomes: list[ProtectionOutcome] = []
    live = position
    for intent in intents:
        if not due(intent, fired, pending_stop):
            continue
        share = allocations.get(intent, _ZERO)
        if share <= _ZERO:
            logger.warning(
                "protection_without_sellable_quantity",
                intent_id=str(intent.intent_id),
                position_id=str(position.position_id),
            )
            continue
        outcome = await _attempt(
            session,
            wallet=wallet,
            market=market,
            snapshot=snapshot,
            intent=intent,
            position=live,
            qty=share,
            evaluation=evaluation if intent.protection_key == fired else None,
            now=now,
            engine=engine,
            source=source,
        )
        outcomes.append(outcome)
        if outcome.application is not None and outcome.application.filled_qty > 0:
            # The next intention of this cycle sees the quantity the previous one
            # really took: the whole point of one lock over one balance.
            live = _after(live, outcome.application.filled_qty)
            if live.qty <= _ZERO:
                break
    return outcomes


def _decision_instant(
    intent: ExitIntent, evaluation: TriggerEvaluation | None, now: datetime
) -> datetime:
    """When this protection decided to sell — the crossing, or its first attempt."""
    if evaluation is not None and evaluation.trade_ts is not None:
        return min(evaluation.trade_ts, now)
    if intent.degraded_since is not None:
        return min(intent.degraded_since, now)
    return now


def _after(position: OpenPositionRow, sold: Decimal) -> OpenPositionRow:
    return OpenPositionRow(
        position_id=position.position_id,
        market_id=position.market_id,
        qty=position.qty - sold,
        avg_entry_price=position.avg_entry_price,
        stop_price=position.stop_price,
        realized_pnl=position.realized_pnl,
        fees_paid=position.fees_paid,
        mark_price=position.mark_price,
        opened_at=position.opened_at,
        proposal_id=position.proposal_id,
    )


async def _attempt(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    snapshot: SpotSnapshot,
    intent: ExitIntent,
    position: OpenPositionRow,
    qty: Decimal,
    evaluation: TriggerEvaluation | None,
    now: datetime,
    engine: PaperExecutionAdapter,
    source: str,
) -> ProtectionOutcome:
    """One attempt at one intention — with its own identity, always.

    ``decision_at`` is when the protection *decided*, which is the instant the
    crossing printed (or, for a retry, when the protection first went degraded)
    — never "now". The eligible book is the one received **after** that instant
    plus the declared latency (``eligible_book``), so dating the decision to the
    present would refuse every book we actually have: the snapshot in hand was
    always received before the cycle that reads it.
    """
    decided_at = _decision_instant(intent, evaluation, now)
    attempt = ExitAttempt.for_intent(
        intent,
        qty=qty,
        decision_at=decided_at,
        position_qty=position.qty,
        trigger=evaluation,
    )
    report = engine.submit_protection_exit(
        attempt,
        position.qty,
        snapshot.book,
        snapshot.last_trade,
        market.filters,
        market.fees,
        now,
        avg_price=snapshot.avg_price,
    )
    application = await apply_exit(
        session,
        wallet=wallet,
        market=market,
        attempt=attempt,
        report=report,
        position=position,
        now=now,
        source=source,
    )
    if report.status == "pending_degraded":
        logger.error(
            "protection_pending_degraded",
            intent_id=str(intent.intent_id),
            position_id=str(position.position_id),
            market=market.identity.symbol,
            reason=report.reason,
            qty=str(qty),
        )
    return ProtectionOutcome(
        intent_id=intent.intent_id,
        position_id=position.position_id,
        status=report.status,
        reason=report.reason,
        trigger=intent.protection_key,
        application=application,
    )
