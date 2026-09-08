"""``ScoreboardRowOut.replication`` reads — brief T3.18b, item 2.

An adapter, not a second implementation: every number the replication
protocol needs comes out of
:mod:`hunter_indicators.replication` (pure, no IO — ``replication_report``),
this module only loads its inputs (``Outcome``/``SiblingArm`` populations,
``promising_at``) the way ``hunter_strategy_worker.replication_stats`` does
for the worker side, adapted to this service's own ``AsyncSession`` (that
module lives in ``services/strategy-worker``, a different deployable, and
this API does not depend on it — ``notes-T3.19.md`` §1 names this exact
fallback).

Two deliberate departures from ``replication_stats.load_outcomes``, both
required by D15 (``.claude/state/decisions-delegated-2026-09-08.md``):

1. **The parent's own population is cohort-filtered to ``prospective``.**
   ``replication_stats``'s query predates the replay engine and carries no
   cohort filter at all; once a version can be replayed under its own
   ``strategy_version_id`` (``replay:<uuid>``, T3.19b), an unfiltered query
   would let replay bars leak into the out-of-sample block, the market-halves
   split, the bootstrap and the ``parent`` verdict itself — exactly what D15
   (b) forbids ("a régua do placar continue só com prospective").
2. **Siblings are found by the ``0012`` columns alone**
   (``replication_parent_id``/``replication_index``), never by parsing
   ``changelog`` — every sibling this API can see was created after the
   migration (this brief does not need to read pre-``0012`` history), so the
   worker's changelog-``LIKE`` fallback would only add a second code path
   with nothing to exercise it.

Every sibling's *maturity* population, per D15 (a), may blend its own live
cohort (``replication:<parent>:<k>``) with any ``replay:<uuid>`` cohort
recorded under that sibling's own ``strategy_version_id`` — labelled by
``evidence`` on the way out (``schemas/lab_replication.py``).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from hunter_api.repositories.lab_common import COHORT
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, StrategyVersion
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import ShadowCohort, ShadowTrackingState
from hunter_indicators.replication import Outcome

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

__all__ = ["SEED_PATTERN", "SiblingMeta", "SiblingPopulation", "LabReplicationRepository"]

SEED_PATTERN = re.compile(r"seed=(\d+)")
"""``sibling_changelog``'s own grammar
(``services/strategy-worker/hunter_strategy_worker/replication_derive.py``):
``... | seed=<n> | pct=... | ...`` — the round's registered seed, read back
so the bootstrap this block reports reproduces the same resampling stream
every time it is asked about the same version."""

Evidence = Literal["prospective", "replay", "mixed"]


@dataclass(frozen=True, slots=True)
class SiblingMeta:
    """One row of ``strategy_versions`` naming a sibling (``0012_replication``
    columns only — see module docstring, departure 2)."""

    id: uuid.UUID
    version: str
    k: int
    changelog: str | None


@dataclass(frozen=True, slots=True)
class SiblingPopulation:
    """A sibling's outcomes, tagged with where they came from (D15)."""

    meta: SiblingMeta
    outcomes: list[Outcome]
    evidence: Evidence | None
    """``None`` when the sibling has produced zero outcomes yet."""


def _outcome_rows_stmt(
    version_id: uuid.UUID, *, as_of: datetime, cohort_condition: ColumnElement[bool]
) -> Select[tuple[Decimal | None, datetime, str, str]]:
    return (
        select(
            SignalOutcome.r_multiple,
            AgentSignal.emitted_at,
            Exchange.code,
            Market.symbol,
        )
        .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
        .join(Market, Market.id == AgentSignal.market_id)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .where(
            AgentSignal.strategy_version_id == version_id,
            AgentSignal.emitted_at <= as_of,
            SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL,
            SignalOutcome.r_multiple.is_not(None),
            cohort_condition,
        )
        .order_by(AgentSignal.emitted_at)
    )


class LabReplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def promising_at(self, version_id: uuid.UUID) -> datetime | None:
        return await self.session.scalar(
            select(StrategyVersion.promising_at).where(StrategyVersion.id == version_id)
        )

    async def siblings(self, parent_id: uuid.UUID) -> list[SiblingMeta]:
        rows = (
            await self.session.execute(
                select(
                    StrategyVersion.id,
                    StrategyVersion.version,
                    StrategyVersion.replication_index,
                    StrategyVersion.changelog,
                )
                .where(StrategyVersion.replication_parent_id == parent_id)
                .order_by(StrategyVersion.replication_index)
            )
        ).all()
        return [
            SiblingMeta(
                id=row.id, version=row.version, k=row.replication_index, changelog=row.changelog
            )
            for row in rows
            if row.replication_index is not None
        ]

    async def _outcomes(
        self, version_id: uuid.UUID, *, as_of: datetime, cohort_condition: ColumnElement[bool]
    ) -> list[Outcome]:
        stmt = _outcome_rows_stmt(version_id, as_of=as_of, cohort_condition=cohort_condition)
        rows = (await self.session.execute(stmt)).all()
        return [
            Outcome(r=row.r_multiple, decision_at=row.emitted_at, market=f"{row.code}:{row.symbol}")
            for row in rows
            if row.r_multiple is not None
        ]

    async def parent_outcomes(self, version_id: uuid.UUID, *, as_of: datetime) -> list[Outcome]:
        """The pai's own avaliável population — ``prospective`` only (D15 b)."""
        return await self._outcomes(
            version_id, as_of=as_of, cohort_condition=(COHORT == ShadowCohort.PROSPECTIVE)
        )

    async def sibling_population(
        self, sibling: SiblingMeta, parent_id: uuid.UUID, *, as_of: datetime
    ) -> SiblingPopulation:
        live_cohort = ShadowCohort.replication(parent_id, sibling.k)
        live = await self._outcomes(
            sibling.id, as_of=as_of, cohort_condition=(COHORT == live_cohort)
        )
        replay = await self._outcomes(
            sibling.id, as_of=as_of, cohort_condition=COHORT.like(f"{ShadowCohort.REPLAY_PREFIX}%")
        )
        evidence: Evidence | None
        if live and replay:
            evidence = "mixed"
        elif replay:
            evidence = "replay"
        elif live:
            evidence = "prospective"
        else:
            evidence = None
        return SiblingPopulation(meta=sibling, outcomes=[*live, *replay], evidence=evidence)
