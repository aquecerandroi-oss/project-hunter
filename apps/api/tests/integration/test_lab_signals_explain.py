"""T3.37a — ``EXPLAIN`` for the totals/list/position queries behind
``GET /lab/shadow/signals`` on a VPS-sized table (brief: "check EXPLAIN ...;
if a partial index is needed, write the brief for database-architect (do not
edit migrations)"). Diagnostic only: no assertion on the plan shape, this test
exists to print real query plans into the test log for the T3.37 report.

Separate file (not ``test_lab_signals_pagination_api.py``): a several-thousand
row seed is slow enough that it should not tax on every run of the base
contract suite -- this one is read explicitly when someone needs the numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text

from hunter_api.repositories.lab_common import COHORT, DECISION_AT, tracking_states_for_lab_state
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import OutcomeResult, ShadowCohort, ShadowTrackingState

from . import lab_fixtures as fx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
ROW_COUNT = 6000
"""Order of magnitude of the brief's "thousands of signals (momentum v1 alone
929 evaluable)" measurement, spread over one version so the version filter
does not trivially shrink the scan."""


async def _seed_vps_sized_population(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=120)
    )
    market_id = await fx.seed_lab_market(session_factory)
    specs: list[dict[str, object]] = []
    for i in range(ROW_COUNT):
        decision_at = NOW - timedelta(minutes=5 * i)
        if i % 20 == 0:
            state, result, extra = ShadowTrackingState.ACTIVE, OutcomeResult.OPEN, {}
        elif i % 20 == 1:
            state, result, extra = (
                ShadowTrackingState.NO_ENTRY,
                OutcomeResult.OPEN,
                {"no_entry_reason": "geometry"},
            )
        elif i % 20 == 2:
            state, result, extra = (
                ShadowTrackingState.CENSORED,
                OutcomeResult.OPEN,
                {"censored_reason": f"gap:{decision_at.isoformat()}"},
            )
        elif i % 20 == 3:
            state, result, extra = ShadowTrackingState.PENDING_ENTRY, OutcomeResult.OPEN, {}
        else:
            entry_bar_open = decision_at + timedelta(minutes=1)
            state, result, extra = (
                ShadowTrackingState.TERMINAL,
                OutcomeResult.TARGET,
                {
                    "entry_bar_open": entry_bar_open,
                    "entry_ts": entry_bar_open,
                    "exit_ts": decision_at + timedelta(hours=1),
                    "exit_price": Decimal("103"),
                    "r_multiple": Decimal("1.5"),
                },
            )
        specs.append(
            {
                "strategy_version_id": version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "tracking_state": state,
                "result": result,
                **extra,
            }
        )
    await fx.seed_shadow_population(session_factory, specs)
    return str(version_id), str(market_id)


async def _explain(session: AsyncSession, stmt) -> str:
    compiled = stmt.compile(dialect=session.bind.dialect, compile_kwargs={"literal_binds": True})
    result = await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compiled}"))
    return "\n".join(row[0] for row in result.all())


async def test_explain_totals_and_list_and_position_queries_on_a_vps_sized_table(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    version_id, _market_id = await _seed_vps_sized_population(session_factory)
    async with session_factory() as session:
        base_filters = [
            COHORT == ShadowCohort.PROSPECTIVE,
            AgentSignal.strategy_version_id == version_id,
        ]

        totals_stmt = (
            select(
                func.count()
                .filter(SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL)
                .label("closed"),
                func.count()
                .filter(SignalOutcome.tracking_state == ShadowTrackingState.ACTIVE)
                .label("open"),
                func.count()
                .filter(
                    SignalOutcome.tracking_state.in_(tracking_states_for_lab_state("pending") or ())
                )
                .label("pending"),
                func.count().label("total"),
            )
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*base_filters)
        )
        totals_plan = await _explain(session, totals_stmt)
        print("\n--- EXPLAIN totals (state not applied) ---\n" + totals_plan)

        list_stmt = (
            select(AgentSignal, SignalOutcome, Market.symbol, DECISION_AT.label("decision_at"))
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*base_filters)
            .order_by(DECISION_AT.desc(), AgentSignal.id.desc())
            .limit(201)
        )
        list_plan = await _explain(session, list_stmt)
        print("\n--- EXPLAIN first page, page_size=200, state=all ---\n" + list_plan)

        # a deep cursor: the row at roughly the midpoint of the terminal
        # population, to see the cost of a "page ~N" position count
        mid_row = (
            await session.execute(
                select(DECISION_AT.label("decision_at"), AgentSignal.id)
                .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
                .where(*base_filters, SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL)
                .order_by(DECISION_AT.desc(), AgentSignal.id.desc())
                .offset(ROW_COUNT // 2)
                .limit(1)
            )
        ).one()
        rank_stmt = (
            select(func.count())
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(
                *base_filters,
                SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL,
                (DECISION_AT > mid_row.decision_at)
                | ((DECISION_AT == mid_row.decision_at) & (AgentSignal.id >= mid_row.id)),
            )
        )
        rank_plan = await _explain(session, rank_stmt)
        print(
            "\n--- EXPLAIN page position (rank of a mid-dataset cursor), state=closed ---\n"
            + rank_plan
        )

        # worst case: no strategy_version_id filter at all (the Lab's "every
        # version" default) -- ix_agent_signals_version_emitted cannot help,
        # so this is the query that shows whether cohort/decision_at need
        # their own index once the table is this size.
        no_version_filters = [COHORT == ShadowCohort.PROSPECTIVE]
        totals_no_version_stmt = (
            select(func.count())
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*no_version_filters)
        )
        totals_no_version_plan = await _explain(session, totals_no_version_stmt)
        print(
            "\n--- EXPLAIN totals, NO strategy_version_id filter (worst case) ---\n"
            + totals_no_version_plan
        )

        list_no_version_stmt = (
            select(AgentSignal, SignalOutcome, Market.symbol, DECISION_AT.label("decision_at"))
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*no_version_filters)
            .order_by(DECISION_AT.desc(), AgentSignal.id.desc())
            .limit(201)
        )
        list_no_version_plan = await _explain(session, list_no_version_stmt)
        print(
            "\n--- EXPLAIN first page, NO strategy_version_id filter (worst case) ---\n"
            + list_no_version_plan
        )

    # diagnostic-only: assert just enough to fail loudly if seeding broke
    assert version_id
