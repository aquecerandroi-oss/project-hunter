"""``GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk/limits`` — T3.25.

Opens a real paper wallet (T3.3's ``open_paper_wallet``, no ``risk_profile_id``
— the same gap the module docstring of ``services/risk_limits.py`` names) and
proves the preset this route reports is byte-for-byte ``hunter_risk.limits.
PAPER_V1``, per the brief's "prove by test that the numbers equal PAPER_V1".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.portfolio.opening import open_paper_wallet
from hunter_risk.limits import PAPER_V1

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

CAPITAL_BRL = Decimal("100000")
RATE = Decimal("5.4321")


async def _observe_fx(
    session_factory: async_sessionmaker[AsyncSession], *, observed_at: datetime
) -> uuid.UUID:
    from sqlalchemy import text

    observation_id = uuid7()
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                "available_at, raw) VALUES (:id, 'USDTBRL', :rate, 'binance.spot.ticker', "
                ":observed, :observed, '{}'::jsonb)"
            ),
            {"id": observation_id, "rate": RATE, "observed": observed_at},
        )
    return observation_id


class Wallet:
    def __init__(self, actor: Actor, portfolio_id: uuid.UUID) -> None:
        self.actor = actor
        self.portfolio_id = portfolio_id

    @property
    def base(self) -> str:
        return f"/api/v1/orgs/{self.actor.org_id}/portfolios/{self.portfolio_id}/risk"


@pytest_asyncio.fixture
async def wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> Wallet:
    unique = uuid.uuid4().hex[:8]
    actor = await create_org(client, make_actor(f"rl-{unique}"), f"RiskLimits {unique}")
    assert actor.org_id is not None and actor.workspace_id is not None
    now = utcnow()
    fx_id = await _observe_fx(session_factory, observed_at=now)
    # ``open_paper_wallet`` writes the opening equity-curve point, and only
    # ``hunter_worker`` may INSERT into ``portfolio_equity_snapshots``
    # (notes-T3.5.md §4, item 5) — ``hunter_app`` (this helper's usual role,
    # and the one every route in this suite runs as) cannot open a wallet.
    async with tenant_session(
        session_factory, actor.org_id, actor.user_id, db_role="hunter_worker"
    ) as session:
        fx = await FxObservationRepository(session).get(fx_id)
        assert fx is not None
        result = await open_paper_wallet(
            session,
            organization_id=actor.org_id,
            workspace_id=actor.workspace_id,
            fx=fx,
            as_of=now,
            capital_brl=CAPITAL_BRL,
        )
    return Wallet(actor, result.portfolio_id)


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/orgs/{uuid.uuid4()}/portfolios/{uuid.uuid4()}/risk/limits"
    )
    assert response.status_code == 401


async def test_unknown_portfolio_is_404(client: httpx.AsyncClient, wallet: Wallet) -> None:
    response = await client.get(
        f"/api/v1/orgs/{wallet.actor.org_id}/portfolios/{uuid.uuid4()}/risk/limits",
        headers=wallet.actor.headers,
    )
    assert response.status_code == 404
    assert response.json()["type"].endswith("portfolio-not-found")


async def test_preset_equals_paper_v1_with_no_risk_profile_wired(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    """``open_paper_wallet`` (fixture above, and every production caller) never
    sets ``risk_profile_id`` — the numbers must still be ``PAPER_V1``."""
    response = await client.get(f"{wallet.base}/limits", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    preset = body["preset"]
    assert preset["source"] == "engine_default"
    assert preset["profile"] == PAPER_V1.profile == "paper_v1"
    assert Decimal(preset["risk_per_trade_pct"]) == PAPER_V1.risk_per_trade_pct == Decimal("0.0025")
    assert (
        Decimal(preset["max_aggregate_planned_risk_pct"])
        == PAPER_V1.max_aggregate_planned_risk_pct
        == Decimal("0.01")
    )
    assert Decimal(preset["max_participation_pct"]) == Decimal("0.01")
    assert Decimal(preset["max_asset_exposure_pct"]) == Decimal("0.10")
    assert Decimal(preset["max_total_exposure_pct"]) == Decimal("0.40")
    assert Decimal(preset["max_beta_btc_exposure"]) == Decimal("0.50")
    assert preset["max_concurrent_positions"] == 5
    assert Decimal(preset["warning_size_multiplier"]) == Decimal("0.5")
    assert Decimal(preset["kill_switch_warning"]["daily_loss_pct"]) == Decimal("0.01")
    assert Decimal(preset["kill_switch_warning"]["drawdown_pct"]) == Decimal("0.04")
    assert Decimal(preset["kill_switch_blocked"]["daily_loss_pct"]) == Decimal("0.02")
    assert Decimal(preset["kill_switch_blocked"]["drawdown_pct"]) == Decimal("0.08")
    assert Decimal(preset["min_liquidity_usd_24h"]) == Decimal("50000000")


async def test_usage_reports_zero_exposure_for_a_freshly_opened_wallet(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    response = await client.get(f"{wallet.base}/limits", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    usage = response.json()["usage"]
    assert usage["open_position_count"] == 0
    assert usage["pending_entry_count"] == 0
    assert Decimal(usage["reserved_cash"]) == 0
    assert Decimal(usage["reserved_notional"]) == 0
    assert Decimal(usage["reserved_risk"]) == 0


async def test_response_embeds_the_kill_switch_and_recent_transitions(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    response = await client.get(f"{wallet.base}/limits", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kill_switch"]["portfolio_id"] == str(wallet.portfolio_id)
    assert body["kill_switch"]["effective"] == "ACTIVE"
    assert body["recent_transitions"] == []


async def test_a_wallet_from_another_organization_is_404(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    wallet: Wallet,
) -> None:
    other = await create_org(client, make_actor("rl-other"), "RiskLimits Other")
    response = await client.get(
        f"/api/v1/orgs/{other.org_id}/portfolios/{wallet.portfolio_id}/risk/limits",
        headers=other.headers,
    )
    assert response.status_code == 404
