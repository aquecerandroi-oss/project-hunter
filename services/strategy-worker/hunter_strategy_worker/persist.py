"""The one transaction a shadow decision is written in — SHADOW-LAB.md §6.

Signal, initial outcome, slot and outbox row commit together or not at all, and
the stream message is only ACKed after that commit. Three consequences that are
the point of the design:

- a published event can never describe a decision that is not in the database;
- a redelivery cannot create a second signal (``ON CONFLICT (id) DO NOTHING`` on
  a deterministic ``uuid5``) nor a second event (``shadow_outbox.event_id`` is
  unique);
- and the envelope is written exactly once. If the insert conflicts, **nothing**
  is rewritten: the second attempt does not get to restate what the strategy
  saw, because by then it would be restating it with today's data.

**One decision writes three rows instead of four when its cohort is a replay**
(T3.19b). ``shadow_outbox`` exists so a *live* decision reaches the consumers of
``shadow.signals.emitted`` — and the only consumer that matters is the execution
bridge, which refuses any cohort other than ``prospective`` by name
(``cohort_not_live``, ``bridge_screen.py``, T3.15e). A replay is nobody's event:
publishing it would put half a million rows a day through a dispatcher whose lag
is a readiness check, to be refused one by one at the far end. The rule is read
off the cohort here — the one place every decision passes through — and not from
a flag the caller could forget: an event that must not exist is not a
responsibility to delegate.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.agents_shadow import ShadowOutbox
from hunter_core.domain.enums import (
    OutcomeResult,
    ShadowCohort,
    SignalStatus,
    TradeDirection,
)
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.record import ShadowRecord

logger = get_logger(__name__)

__all__ = ["is_published_cohort", "persist_decision"]


def is_published_cohort(cohort: str) -> bool:
    """Whether decisions of ``cohort`` get a ``shadow_outbox`` row.

    Everything except a replay does. A replication sibling still publishes: its
    signals are a forward population that the bridge screens like any other (and
    refuses, by ``purpose`` and by cohort), and the outbox is where the Lab's
    consumers see it happen. A ``replay:<run_id>`` is history being recomputed —
    there is no "it happened" to announce.
    """
    return not cohort.startswith(ShadowCohort.REPLAY_PREFIX)


async def persist_decision(session: AsyncSession, record: ShadowRecord) -> bool:
    """Write the four rows. Returns ``False`` when the signal already existed.

    ``False`` is not an error: it is a redelivery or a restart meeting its own
    previous work, and the correct response is to ACK and move on.
    """
    inserted = await session.scalar(
        pg_insert(AgentSignal)
        .values(
            id=record.signal_id,
            strategy_version_id=record.strategy_version_id,
            market_id=record.market_id,
            params_hash=record.params_hash,
            direction=TradeDirection.LONG,
            confidence=record.confidence,
            entry_zone={
                "type": "next_1m_open",
                "entry_bar_open": record.plan.entry_bar_open.isoformat(),
            },
            stop=record.stop,
            targets=[format(level, "f") for level in record.targets],
            invalidations=record.invalidations,
            expected_holding_s=record.horizon_s,
            reason=record.reason,
            supporting_features=record.supporting_features,
            regime_id=record.regime_id,
            emitted_at=record.decision_at,
            expires_at=record.plan.entry_bar_open + timedelta(seconds=record.horizon_s),
            status=SignalStatus.ACTIVE,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(AgentSignal.id)
    )
    if inserted is None:
        logger.info("shadow_signal_already_persisted", signal_id=str(record.signal_id))
        return False
    await session.execute(
        pg_insert(SignalOutcome)
        .values(
            signal_id=record.signal_id,
            virtual_stop=record.stop,
            virtual_targets=[format(level, "f") for level in record.targets],
            result=OutcomeResult.OPEN,
            tracking_state=record.tracking_state,
            no_entry_reason=record.no_entry_reason,
            meta=record.meta,
        )
        .on_conflict_do_nothing(index_elements=["signal_id"])
    )
    if is_published_cohort(record.cohort):
        await session.execute(
            pg_insert(ShadowOutbox)
            .values(
                event_id=record.signal_id,
                stream=Streams.SHADOW_SIGNALS_EMITTED,
                payload=record.payload,
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
    return True
