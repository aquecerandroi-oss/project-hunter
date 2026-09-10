"""T3.69b — the wallet's limits are its linked ``risk_profiles`` row, or nothing is admitted.

The §0 wallet of ``conftest.py`` (``open_paper_wallet``, no ``risk_profile_id``
— no production caller sets one) is exactly the VPS wallet before
``docs/ACTIVATION.md`` §8b is run. Against a real Postgres, through the
execution-worker's own path
(:func:`hunter_execution_worker.admission_cycle.decide_requests`, the one
function both the manual cycle and the autonomy bridge admit through), this
file proves the three states that matter:

- **no linked profile** → nothing is admitted, no ``trade_proposals`` row is
  written, and the refusal is named ``risk_profile_missing``. That is the
  intended fail-closed state, not an outage: the operator has two commands;
- **linked to the seeded row** → the same request is admitted and approved
  exactly as before, with the limits read back **from the row** (0,25 % per
  trade, five slots), not from the code constant;
- **linked to a row somebody edited** → refused by name
  (``risk_profile_diverged``), because the constant stays the guard: a widened
  ceiling nobody decided must never become the applied limit.

No number changes anywhere in this file: the linked row is
``PAPER_V1.model_dump(mode="json")``, which is what
``infra/scripts/seed_risk_reference.py`` writes.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.db.session import tenant_session
from hunter_core.domain.types import uuid7
from hunter_execution_worker.admission_cycle import RequestInputs, decide_requests
from hunter_execution_worker.risk_profile import DIVERGED, LINKED, MISSING, wallet_limits
from hunter_risk.limits import PAPER_V1

from .conftest import (
    ENGINE_ROLE,
    NO_EXIT_COST,
    NOW,
    Wallet,
    at,
    beta_for,
    liquidity_for,
    market_reference,
    request_for,
    wallet_ref,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

LINK_SQL = (
    "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) "
    "VALUES (:id, :org, 'Paper v1', 'paper_v1', CAST(:limits AS jsonb))"
)


async def link_profile(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    limits: dict[str, Any] | None = None,
) -> uuid.UUID:
    """``ACTIVATION.md`` §8b, in one transaction: seed the row, point the wallet.

    As ``hunter_app``: ``risk_profiles`` and ``portfolios`` are its tables
    (``ddl/tables.py``), the worker only reads them. Tenant-scoped rather than a
    system preset because ``FORCE ROW LEVEL SECURITY`` reserves the
    ``organization_id IS NULL`` rows for the migrating role that seeds them.
    """
    from sqlalchemy import text

    profile_id = uuid7()
    stored = PAPER_V1.model_dump(mode="json") if limits is None else limits
    async with tenant_session(factory, wallet.org_id, wallet.user_id, db_role="hunter_app") as sess:
        await sess.execute(
            text(LINK_SQL),
            {"id": profile_id, "org": wallet.org_id, "limits": json.dumps(stored)},
        )
        await sess.execute(
            text("UPDATE portfolios SET risk_profile_id = :profile WHERE id = :id"),
            {"profile": profile_id, "id": wallet.portfolio_id},
        )
    return profile_id


async def admit_through_the_worker(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    client_key: str,
    now: Any = NOW,
) -> tuple[Any, ...]:
    """One pass of the worker's admission path, on the §0 SOL market."""
    market = wallet.market("SOLUSDT")
    request = request_for(wallet, market, client_key=client_key)
    inputs = RequestInputs(
        liquidity=liquidity_for(market, as_of=now),
        beta=beta_for(as_of=now),
        prices={item.id: Decimal(100) for item in wallet.markets.values()},
        betas=wallet.betas,
        exit_cost_rate=NO_EXIT_COST,
    )
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        # The reference the cycle would have loaded; ``decide_requests`` reads
        # the market row itself, so this only proves the fixture's identity.
        assert market_reference(market).market_id == request.market_id
        return await decide_requests(
            session, wallet=wallet_ref(wallet), requests=[(request, inputs)], now=now
        )


async def count_proposals(engine: AsyncEngine, wallet: Wallet) -> int:
    from sqlalchemy import text

    async with engine.begin() as connection:
        rows = await connection.execute(
            text("SELECT count(*) FROM trade_proposals WHERE portfolio_id = :id"),
            {"id": wallet.portfolio_id},
        )
        return int(rows.scalar_one())


async def resolved_state(factory: async_sessionmaker[AsyncSession], wallet: Wallet) -> Any:
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await wallet_limits(session, wallet=wallet_ref(wallet))


async def test_a_wallet_without_a_linked_profile_admits_nothing(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """The VPS wallet as it stands before §8b: fail closed, by name."""
    resolved = await resolved_state(factory, wallet)
    assert resolved.state == MISSING
    assert resolved.limits is None

    admitted = await admit_through_the_worker(factory, wallet, client_key="t369b-unlinked")

    assert admitted == ()
    assert await count_proposals(engine, wallet) == 0


async def test_a_linked_profile_equal_to_the_engine_admits_as_before(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """§8b run: the row is the applied source, and it is Everton's numbers."""
    await link_profile(factory, wallet)
    resolved = await resolved_state(factory, wallet)
    assert resolved.state == LINKED
    assert resolved.limits == PAPER_V1
    assert resolved.limits.risk_per_trade_pct == Decimal("0.0025")

    admitted = await admit_through_the_worker(factory, wallet, client_key="t369b-linked")

    assert len(admitted) == 1
    result = admitted[0]
    assert result.approved, result.decision.rejection_reasons
    assert result.reservation_state.value == "held"
    # The §0 numbers of V1, unchanged by the profile now being read from a row.
    assert result.decision.sizing is not None
    assert result.decision.sizing.qty == Decimal("18.518")
    assert result.decision.sizing.binding_constraint == "risk_per_trade"
    assert await count_proposals(engine, wallet) == 1


async def test_a_linked_profile_that_moved_a_ceiling_admits_nothing(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """A row edited to 1 % per trade is four times Everton's number. The engine
    does not adopt it and does not silently fall back to the constant either —
    it refuses, and the operator sees which field moved."""
    await link_profile(
        factory, wallet, limits=PAPER_V1.model_dump(mode="json") | {"risk_per_trade_pct": "0.01"}
    )
    resolved = await resolved_state(factory, wallet)
    assert resolved.state == DIVERGED
    assert resolved.detail == "risk_per_trade_pct"

    admitted = await admit_through_the_worker(factory, wallet, client_key="t369b-diverged")

    assert admitted == ()
    assert await count_proposals(engine, wallet) == 0


async def test_linking_the_profile_makes_the_same_wallet_admit_again(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine, wallet: Wallet
) -> None:
    """Reversible without a restart: the refusal is a state of the row, not of
    the process — the operator runs §8b and the next pass admits."""
    first = await admit_through_the_worker(factory, wallet, client_key="t369b-before")
    assert first == ()

    await link_profile(factory, wallet)
    later = await admit_through_the_worker(
        factory, wallet, client_key="t369b-after", now=at(seconds=1)
    )

    assert len(later) == 1
    assert later[0].approved
    assert await count_proposals(engine, wallet) == 1
