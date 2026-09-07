"""T3.14 item 2 — which shadow signals may become a proposal, and why not.

Every refusal here is a *named* one. The bridge never drops a signal silently:
each screening produces either a candidate or a ``Refusal`` with a reason that
is logged and counted in ``hunter_bridge_candidates_total{outcome}``, because a
wallet that admits nothing and a bridge that is not running look identical from
outside unless the refusals are visible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.db.session import tenant_session
from hunter_execution_worker.bridge_repo import ENTRY_WINDOW, pending_signals
from hunter_execution_worker.bridge_screen import Screened, screen_signal
from hunter_execution_worker.wallet import WalletRef

from . import shadow_builders as shadow
from .builders import NOW, Tenant, Wallet, create_tenant, open_wallet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
BAR = NOW - timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Fixture:
    """One tenant with a wallet, a spot market, a perpetual and a version."""

    tenant: Tenant
    wallet: Wallet
    perp_market_id: uuid.UUID
    version_id: uuid.UUID

    @property
    def ref(self) -> WalletRef:
        return WalletRef(self.tenant.org_id, self.wallet.portfolio_id)


async def _setup(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    *,
    spot_volume: Decimal | None = Decimal(120_000_000),
    with_beta: bool = True,
    active_version: bool = True,
) -> Fixture:
    tenant = await create_tenant(engine)
    wallet = await open_wallet(factory, engine, tenant)
    perp_market_id = await shadow.add_perp_market(engine, tenant)
    version_id = await shadow.create_version(engine, active=active_version, at=BAR)
    await shadow.set_spot_volume(engine, tenant.market_id, volume=spot_volume)
    await shadow.create_agent(
        engine,
        organization_id=tenant.org_id,
        workspace_id=tenant.workspace_id,
        portfolio_id=wallet.portfolio_id,
        version_id=version_id,
    )
    if with_beta:
        await shadow.set_beta(engine, tenant.market_id, as_of=NOW)
    return Fixture(tenant, wallet, perp_market_id, version_id)


async def _screen(
    factory: async_sessionmaker[AsyncSession],
    fixture: Fixture,
    *,
    now: datetime = NOW,
) -> list[Screened]:
    """Read the pending signals of the wallet and screen each one."""
    wallet = fixture.ref
    async with tenant_session(factory, wallet.organization_id, db_role=WORKER_ROLE) as session:
        signals = await pending_signals(session, wallet=wallet, now=now)
        return [await screen_signal(session, wallet=wallet, signal=s, now=now) for s in signals]


async def test_a_live_signal_of_an_active_version_is_a_candidate(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    fixture = await _setup(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert len(screened) == 1
    candidate = screened[0]
    assert candidate.refused is None, candidate.refused
    assert candidate.spot_market_id == fixture.tenant.market_id
    assert candidate.entry_ref == Decimal(100)
    assert candidate.stop == Decimal("97.5")


async def test_research_only_is_refused_at_the_door(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """SHADOW-LAB §10: evidence never becomes an order, and it is *counted*."""
    fixture = await _setup(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["research_only"]


async def test_a_signal_of_an_inactive_version_is_refused(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    fixture = await _setup(db_session_factory, db_engine, active_version=False)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["version_inactive"]


async def test_without_a_beta_the_signal_is_refused_beta_unavailable(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """The directive's rule: no validated beta, the asset stays in shadow."""
    fixture = await _setup(db_session_factory, db_engine, with_beta=False)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["beta_unavailable"]


async def test_a_spot_pair_below_the_floor_is_refused(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    fixture = await _setup(db_session_factory, db_engine, spot_volume=Decimal(10_000_000))
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["spot_volume_below_floor"]


async def test_a_spot_pair_without_a_measured_volume_is_refused_unavailable(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T3.0c has not measured this pair yet: a permission is never granted by a
    failed read (``spot_universe.tradable_symbols``, same doctrine)."""
    fixture = await _setup(db_session_factory, db_engine, spot_volume=None)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["spot_volume_unavailable"]


async def test_an_expired_entry_window_is_refused(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """SHADOW-LAB §3: the entry window is 120 s from ``source_bar_close``."""
    fixture = await _setup(db_session_factory, db_engine)
    late_bar = NOW - ENTRY_WINDOW - timedelta(seconds=5)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=late_bar,
        purpose=shadow.PURPOSE_LIVE,
    )
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["entry_window_closed"]


async def _insert_coin_position(
    engine: AsyncEngine, fixture: Fixture, *, is_residual: bool
) -> None:
    from sqlalchemy import text

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price, status, is_residual, opened_at) VALUES "
                "(gen_random_uuid(), :org, :pf, :market, 'long', 0.000482, 100, 'closing', "
                ":is_residual, :now)"
            ),
            {
                "org": fixture.tenant.org_id,
                "pf": fixture.wallet.portfolio_id,
                "market": fixture.tenant.market_id,
                "is_residual": is_residual,
                "now": NOW,
            },
        )


async def test_a_position_closing_in_the_same_coin_refuses_duplicate_position(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """Never two positions in the same coin — including one still ``closing``
    that has not settled as dust yet (``is_residual = false``)."""
    fixture = await _setup(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    await _insert_coin_position(db_engine, fixture, is_residual=False)
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == ["duplicate_position"]


async def test_a_residual_position_in_the_same_coin_does_not_refuse(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """``0009_paper_geometry``, DATABASE.md §21.1: dust is not a position, so it
    is not a commitment either — same rule ``entry.py``'s manual duplicate
    guard applies (T3.1e/review-T3.5.md item 3, "não conta ... duplicidade")."""
    fixture = await _setup(db_session_factory, db_engine)
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_LIVE,
    )
    await _insert_coin_position(db_engine, fixture, is_residual=True)
    screened = await _screen(db_session_factory, fixture)
    assert [item.refused for item in screened] == [None]
