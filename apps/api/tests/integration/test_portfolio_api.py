"""The wallet's read API over HTTP — T3.8a.

Opens a real paper wallet through ``hunter_core.portfolio.opening.
open_paper_wallet`` (T3.3) against a real FX observation, then reads it back
through every route ``routers/portfolio.py`` exposes. Nothing here is a
stub: the positions/orders/trades pages are genuinely empty because those
tables have no writer yet (T3.4/T3.5), not because the route fakes it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.portfolio.opening import open_paper_wallet

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

CAPITAL_BRL = Decimal("100000")
RATE = Decimal("5.4321")


async def _observe_fx(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    rate: Decimal = RATE,
    observed_at: datetime,
    available_at: datetime | None = None,
) -> uuid.UUID:
    """Persist one ``fx_observations`` row as ``hunter_worker`` — T3.11's role."""
    observation_id = uuid7()
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                "available_at, raw) VALUES (:id, 'USDTBRL', :rate, 'binance.spot.ticker', "
                ":observed, :available, '{}'::jsonb)"
            ),
            {
                "id": observation_id,
                "rate": rate,
                "observed": observed_at,
                "available": available_at or observed_at,
            },
        )
    return observation_id


class Wallet:
    def __init__(self, actor: Actor, portfolio_id: uuid.UUID) -> None:
        self.actor = actor
        self.portfolio_id = portfolio_id

    @property
    def base(self) -> str:
        return f"/api/v1/orgs/{self.actor.org_id}/portfolios/{self.portfolio_id}"


async def _open(
    session_factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    fx_observation_id: uuid.UUID,
    as_of: datetime,
) -> uuid.UUID:
    assert actor.org_id is not None and actor.workspace_id is not None
    # T3.68b finding 10: ``hunter_app`` (the default role) lost INSERT on
    # ``portfolio_equity_snapshots`` in ``0007_paper_roles`` — opening writes
    # the curve's first point, so this has to run as ``hunter_worker``, same
    # as ``test_manual_orders.py``/``test_risk_limits_api.py``'s own helpers
    # and the real ``infra/scripts/open_paper_wallet.py``.
    async with tenant_session(
        session_factory, actor.org_id, actor.user_id, db_role="hunter_worker"
    ) as session:
        fx = await FxObservationRepository(session).get(fx_observation_id)
        assert fx is not None
        result = await open_paper_wallet(
            session,
            organization_id=actor.org_id,
            workspace_id=actor.workspace_id,
            fx=fx,
            as_of=as_of,
            capital_brl=CAPITAL_BRL,
        )
    return result.portfolio_id


@pytest_asyncio.fixture
async def wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> Wallet:
    """An organization with its principal paper wallet opened for real, at R$100.000."""
    unique = uuid.uuid4().hex[:8]
    actor = await create_org(client, make_actor(f"pf-{unique}"), f"Portfolio {unique}")
    now = utcnow()
    fx_id = await _observe_fx(session_factory, observed_at=now)
    portfolio_id = await _open(session_factory, actor, fx_observation_id=fx_id, as_of=now)
    return Wallet(actor, portfolio_id)


class TestBrlUnavailable:
    """Runs **first** in this module, deliberately.

    ``fx_observations`` is global (DATABASE.md §18.2) and the live summary
    read picks the newest one available for the pair/source
    (``FxObservationRepository.latest_available``) — exactly right in
    production, where there is one true USDTBRL rate for every wallet. In this
    suite it means a fresh observation any *other* test's ``wallet`` fixture
    inserts would outrank the deliberately-stale one this test needs the
    summary to actually pick. Collection order in a module is definition
    order (no randomisation plugin is configured), so this class is declared
    before ``TestSummary`` precisely so nothing has inserted a fresher
    ``USDTBRL``/``binance.spot.ticker`` row yet.
    """

    async def test_a_stale_rate_makes_brl_unavailable_with_a_reason(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The rate that opened the wallet is fresh *at the opening instant* and
        stale *now* — BRL degrades without touching the USDT side (M3 joint
        decision, item 1)."""
        unique = uuid.uuid4().hex[:8]
        actor = await create_org(client, make_actor(f"pf-stale-{unique}"), f"Stale {unique}")
        observed_at = utcnow() - timedelta(seconds=700)
        fx_id = await _observe_fx(session_factory, observed_at=observed_at)
        portfolio_id = await _open(
            session_factory,
            actor,
            fx_observation_id=fx_id,
            as_of=observed_at + timedelta(seconds=5),
        )

        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/portfolios/{portfolio_id}", headers=actor.headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["brl"] is None
        assert body["brl_unavailable_reason"] == "fx_rejected"
        assert "old" in body["brl_unavailable_detail"]
        # the USDT side is never held hostage to a stale rate
        assert Decimal(body["equity"]) > 0


class TestSummary:
    async def test_the_summary_reports_equity_and_the_brl_decomposition(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        response = await client.get(wallet.base, headers=wallet.actor.headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == str(wallet.portfolio_id)
        assert body["type"] == "paper"
        assert Decimal(body["equity"]) == Decimal(body["cash"])
        assert Decimal(body["equity"]) > 0
        assert body["open_position_count"] == 0
        assert body["unavailable"] == []
        brl = body["brl"]
        assert brl is not None, body["brl_unavailable_reason"]
        assert Decimal(brl["opening_rate"]) == RATE
        assert Decimal(brl["current_rate"]) == RATE
        # at the opening instant E == E0, so the operational term is exactly zero
        assert Decimal(brl["operational_brl"]) == 0
        assert Decimal(brl["currency_brl"]) == 0
        risk_state = body["risk_state"]
        assert risk_state["daily_loss_pct"] == "0"
        assert risk_state["drawdown_pct"] == "0"
        assert risk_state["kill_switch"]["effective"] == "ACTIVE"
        assert risk_state["kill_switch"]["blocks_entries"] is False

    async def test_another_organizations_wallet_is_a_404_not_a_403(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor], wallet: Wallet
    ) -> None:
        unique = uuid.uuid4().hex[:8]
        outsider = await create_org(client, make_actor(f"pf-out-{unique}"), f"Outsider {unique}")

        response = await client.get(
            f"/api/v1/orgs/{outsider.org_id}/portfolios/{wallet.portfolio_id}",
            headers=outsider.headers,
        )

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")

    async def test_an_unknown_portfolio_is_a_404(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        response = await client.get(
            f"/api/v1/orgs/{wallet.actor.org_id}/portfolios/{uuid7()}",
            headers=wallet.actor.headers,
        )

        assert response.status_code == 404


class TestAnchor:
    async def test_the_anchor_names_the_observation_it_opened_on(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        response = await client.get(f"{wallet.base}/anchor", headers=wallet.actor.headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["origin_currency"] == "BRL"
        assert Decimal(body["origin_amount"]) == CAPITAL_BRL
        assert body["operating_currency"] == "USDT"
        assert Decimal(body["rate"]) == RATE
        assert body["fx_observation"]["pair"] == "USDTBRL"
        assert body["fx_observation"]["source"] == "binance.spot.ticker"
        assert Decimal(body["fx_observation"]["rate"]) == RATE

    async def test_another_organizations_anchor_is_a_404(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor], wallet: Wallet
    ) -> None:
        unique = uuid.uuid4().hex[:8]
        outsider = await create_org(client, make_actor(f"pf-anc-out-{unique}"), f"Out {unique}")

        response = await client.get(
            f"/api/v1/orgs/{outsider.org_id}/portfolios/{wallet.portfolio_id}/anchor",
            headers=outsider.headers,
        )

        assert response.status_code == 404


class TestEquityCurve:
    async def test_the_opening_point_is_on_the_curve_with_its_brl_reading(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        response = await client.get(f"{wallet.base}/equity-curve", headers=wallet.actor.headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert "as_of" in body
        assert len(body["items"]) == 1
        point = body["items"][0]
        assert point["fx_observation_id"] is not None
        assert point["brl_equity"] is not None
        assert point["brl_unavailable_reason"] is None
        assert Decimal(point["equity"]) == Decimal(point["cash"])

    async def test_a_naive_from_is_a_422_not_a_500(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        """No timezone on ``?from=`` must not reach the ``timestamptz`` filter
        unconverted (Astra, review of this diff, must-fix 2)."""
        response = await client.get(
            f"{wallet.base}/equity-curve?from=2026-09-06T00:00:00",
            headers=wallet.actor.headers,
        )

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")


class TestEmptyListsAreHonest:
    @pytest.mark.parametrize("path", ["positions", "orders", "trades"])
    async def test_the_list_is_empty_with_no_writer_yet(
        self, client: httpx.AsyncClient, wallet: Wallet, path: str
    ) -> None:
        response = await client.get(f"{wallet.base}/{path}", headers=wallet.actor.headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["items"] == []
        assert body["next_cursor"] is None
        assert "as_of" in body

    @pytest.mark.parametrize("path", ["positions", "orders", "trades", "equity-curve"])
    async def test_another_organizations_lists_are_a_404(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        wallet: Wallet,
        path: str,
    ) -> None:
        unique = uuid.uuid4().hex[:8]
        outsider = await create_org(client, make_actor(f"pf-list-out-{unique}"), f"Out {unique}")

        response = await client.get(
            f"/api/v1/orgs/{outsider.org_id}/portfolios/{wallet.portfolio_id}/{path}",
            headers=outsider.headers,
        )

        assert response.status_code == 404


class TestList:
    async def test_the_organizations_wallet_is_in_the_list(
        self, client: httpx.AsyncClient, wallet: Wallet
    ) -> None:
        response = await client.get(
            f"/api/v1/orgs/{wallet.actor.org_id}/portfolios", headers=wallet.actor.headers
        )

        assert response.status_code == 200, response.text
        body = response.json()
        ids = [item["id"] for item in body["items"]]
        assert str(wallet.portfolio_id) in ids

    async def test_a_fresh_organization_has_no_portfolios(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        unique = uuid.uuid4().hex[:8]
        actor = await create_org(client, make_actor(f"pf-empty-{unique}"), f"Empty {unique}")

        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/portfolios", headers=actor.headers
        )

        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
