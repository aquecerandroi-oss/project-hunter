"""T3.5b items 1, 7 and 9 — what the order cycle refuses before it spends a fill.

Three refusals, each one a scenario the guardian's review of ``7ecafd2``
reproduced in Postgres:

- **the tenure is a fact, not a decoration.** A proposal approved at 15:30:00
  reserves the wallet's capital until 15:30:30. The cycle of 15:35:00 must not
  execute it — 270 s after the commitment died the wallet's cash, its slot and
  its participation budget were already given back to everybody else;
- **an expiry says why it never got its order**, and "reserved_until reached" is
  not the answer: the useful fact is the input that never arrived
  (``no_book``, ``avg_price_not_collected``, ``book_before_latency``);
- **§11 at the fill.** The organization is blocked *between* the decision and
  the order. The entry is refused by the state re-read in the very transaction
  that would have written the fill, not by the one the decision saw.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.domain.enums import ReservationState

from .builders import NOW, create_tenant, open_wallet
from .scenarios import (
    admit_one,
    block_the_organization,
    count_of,
    entry_snapshot,
    no_book_snapshot,
    reservation_of,
    run_entries,
    static,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

RESERVED_UNTIL = NOW + timedelta(seconds=30)
"""15:30:30 — the 30 s tenure of ``PIPELINE.md`` §5, on the row itself."""

LATE = NOW + timedelta(minutes=5)
"""15:35:00 — the cycle that must not execute it."""


async def _expiry_audit(engine: AsyncEngine, proposal_id: object) -> dict[str, object]:
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT metadata FROM audit_logs WHERE entity_id = :id "
                    "AND action = 'proposal.reservation_expired' ORDER BY created_at DESC LIMIT 1"
                ),
                {"id": proposal_id},
            )
        ).one_or_none()
    return {} if row is None else dict(row.metadata)


class TestAnExpiredReservationIsNeverExecuted:
    async def test_the_cycle_five_minutes_late_expires_it_instead_of_filling_it(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)
        assert decision.approved
        before = await reservation_of(db_engine, decision.proposal_id)
        # The tenure is stamped from the wall clock inside ``admit``, not from the
        # injected instant, so the assertion is the window and not the microsecond.
        assert RESERVED_UNTIL <= before.reserved_until < NOW + timedelta(seconds=31)

        # A perfectly eligible book, one second old at 15:35:00. Nothing about
        # the market refuses this entry — only the dead reservation does.
        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant, at=LATE - timedelta(seconds=1))),
            now=LATE,
        )

        assert [outcome.status for outcome in outcomes] == ["expired"]
        after = await reservation_of(db_engine, decision.proposal_id)
        assert after.reservation_state == ReservationState.EXPIRED.value
        # ``status`` is the other axis: the decision does not stop being true
        # when the tenure runs out (DATABASE.md §18.3).
        assert after.status == "approved"
        assert await count_of(db_engine, wallet, "orders") == 0
        assert await count_of(db_engine, wallet, "fills") == 0
        assert await count_of(db_engine, wallet, "positions") == 0

    async def test_the_expiry_records_the_input_that_never_arrived(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, no_book_snapshot(tenant, ts=LATE - timedelta(seconds=1))),
            now=LATE,
        )

        assert [(o.status, o.reason) for o in outcomes] == [("expired", "no_book")]
        metadata = await _expiry_audit(db_engine, decision.proposal_id)
        assert "no_book" in str(metadata.get("reason", ""))
        assert str(metadata["reason"]).startswith("reserved_until reached")


class TestTheStateIsReReadInTheTransactionThatWouldFill:
    async def test_an_organization_blocked_after_the_decision_stops_the_order(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)
        assert decision.approved

        await block_the_organization(db_engine, wallet, now=NOW + timedelta(seconds=1))

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant)),
            now=NOW + timedelta(seconds=2),
        )

        assert [(o.status, o.reason) for o in outcomes] == [
            ("blocked", "kill_switch_blocks_entries")
        ]
        assert await count_of(db_engine, wallet, "orders") == 0
        assert await count_of(db_engine, wallet, "fills") == 0
        assert await count_of(db_engine, wallet, "positions") == 0
        # The reservation is left standing: releasing pendings is the kill
        # switch cycle's own act, audited as such (RISK_ENGINE.md §5).
        assert (await reservation_of(db_engine, decision.proposal_id)).reservation_state == (
            ReservationState.HELD.value
        )


class TestTheTenureIsReadFromTheRow:
    async def test_a_reservation_still_inside_its_tenure_is_executed_normally(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The guard must refuse the dead reservation and nothing else."""
        tenant = await create_tenant(db_engine)
        wallet = await open_wallet(db_session_factory, db_engine, tenant)
        decision = await admit_one(db_session_factory, wallet)

        outcomes = await run_entries(
            db_session_factory,
            wallet,
            static(tenant, entry_snapshot(tenant, at=NOW + timedelta(seconds=29))),
            now=NOW + timedelta(seconds=29),
        )

        assert [outcome.status for outcome in outcomes] == ["filled"]
        assert (await reservation_of(db_engine, decision.proposal_id)).reservation_state == (
            ReservationState.CONSUMED.value
        )
        assert await count_of(db_engine, wallet, "positions") == 1
