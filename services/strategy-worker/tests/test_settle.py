"""``settle()`` reads funding through a real Postgres — S2-funding round 4.

The one scenario this file exists for: a real ``funding_rates`` row landing a
few ms *after* ``exit_ts`` is the other half of a cluster whose sibling is
still inside the trade's window. If the loader's query stops exactly at
``exit_ts``, that row is invisible to :func:`resolve_funding` and the
straddling duplicate is charged as if it were a lone, resolved settlement
instead of being flagged unestablishable (Astra, S2-funding review, round 4
must-fix 1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.settle import settle
from hunter_strategy_worker.walker import Progress, TrackingPlan

from .builders import ensure_partitions, seed_market

pytestmark = pytest.mark.integration

ENTRY = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
EXIT = ENTRY + timedelta(hours=1)
COSTS = AssumedCosts(
    spread_bps=Decimal("2"), slippage_bps=Decimal("5"), fee_bps=Decimal("4"), max_entry_delay_s=120
)


@pytest.fixture
async def market_id(db_session_factory: Any) -> Any:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, ENTRY)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM funding_rates"))
        _exchange_id, market_id = await seed_market(session)
    return market_id


async def _insert_funding(session: Any, *, market_id: Any, at: datetime, rate: str) -> None:
    await session.execute(
        text(
            "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
            "VALUES (:m, :t, :r, :p)"
        ),
        {"m": market_id, "t": at, "r": Decimal(rate), "p": Decimal("100")},
    )


def _plan() -> TrackingPlan:
    return TrackingPlan(
        entry_bar_open=ENTRY,
        stop=Decimal("99"),
        target1=Decimal("103"),
        horizon_s=4 * 3600,
        costs=COSTS,
    )


def _terminal_progress() -> Progress:
    """Exit exactly at the open of ``EXIT`` — not ambiguous on its own."""
    return Progress(
        tracking_state=ShadowTrackingState.TERMINAL,
        result=OutcomeResult.TARGET,
        entry=Decimal("100"),
        entry_ts=ENTRY,
        exit_base=Decimal("103"),
        exit_observed=Decimal("103"),
        exit_ts=EXIT,
        exit_at_open=True,
        exit_bar_open=EXIT,
    )


class TestFundingAcrossTheExitBoundary:
    async def test_a_row_five_ms_after_exit_makes_the_cluster_boundary_uncertain(
        self, market_id: Any, db_session_factory: Any
    ) -> None:
        """Two compatible representations of one settlement, one exactly at
        ``exit_ts`` (inside the window) and one 5 ms later (outside it): the
        loader must still see both, or this test would instead charge 0.02
        with no reason — this file's counter-example."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _insert_funding(
                session, market_id=market_id, at=ENTRY - timedelta(hours=8), rate="0.0001"
            )
            await _insert_funding(session, market_id=market_id, at=ENTRY, rate="0.0001")
            await _insert_funding(session, market_id=market_id, at=EXIT, rate="0.0002")
            await _insert_funding(
                session, market_id=market_id, at=EXIT + timedelta(milliseconds=5), rate="0.0002"
            )
            settlement = await settle(
                session, market_id=market_id, plan=_plan(), progress=_terminal_progress()
            )
        assert settlement.r_multiple is None
        assert settlement.meta["r_net_reason"] is not None
        assert settlement.meta["r_net_reason"].startswith("funding_boundary_uncertain")

    async def test_a_lone_row_at_exit_with_nothing_after_is_still_charged_normally(
        self, market_id: Any, db_session_factory: Any
    ) -> None:
        """Control case: without the straddling sibling, the same settlement
        at exactly ``exit_ts`` resolves as before — the wider read must not
        turn a genuinely lone settlement into a false boundary conflict."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _insert_funding(
                session, market_id=market_id, at=ENTRY - timedelta(hours=8), rate="0.0001"
            )
            await _insert_funding(session, market_id=market_id, at=ENTRY, rate="0.0001")
            await _insert_funding(session, market_id=market_id, at=EXIT, rate="0.0002")
            settlement = await settle(
                session, market_id=market_id, plan=_plan(), progress=_terminal_progress()
            )
        assert settlement.r_multiple is not None
        assert settlement.meta["r_net_reason"] is None
        assert Decimal(settlement.meta["funding"]["per_unit"]) == Decimal("0.02")
