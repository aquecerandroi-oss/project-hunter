"""``POST/GET .../order-requests`` over HTTP — T3.68.

Opens a real paper wallet (``hunter_core.portfolio.opening.open_paper_wallet``,
T3.3) and seeds a real SPOT market row plus a real Redis ticker, then drives
the route exactly as an operator would. The engine's own decision — approved
or refused — is taken through ``hunter_core.admission.service.admit`` in a
second, later transaction as ``hunter_worker``, precisely the way
``services/execution-worker/hunter_execution_worker/admission_cycle.py``'s 1 s
poll would (this suite cannot import that service — ``apps/api`` does not
depend on it, by design), which is also why an audited decision is asserted
rather than a specific ``approved``/``rejected`` outcome for the plain filing
test: what T3.68 adds is the *filing* path; a full, passing sizing walk is
T3.5's own proof (``services/execution-worker/tests/test_manual_request_decided.py``).

**T3.68b, finding 2 (fixed, no longer a gap):** the *filing* act now writes
its own ``audit_logs`` row too (``order_request.filed``, actor = the real
operator — ``hunter_api.services.admission_audit.record_filing_audit``). The
engine's later *decision* still writes a second, separate row
(``hunter_core.admission.record.py``, action
``proposal.admitted``/``proposal.rejected``) — production's own
``admission_cycle.rebuild_request`` stamps that one's actor as the worker,
never the operator, which is exactly why the filing-time row exists: it is
the one place the real operator's identity survives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import select, text

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.services import admission
from hunter_core.admission.service import admit
from hunter_core.admission.sources import ProposalRequest
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.db.models.system import AuditLog
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import MarketType, OrganizationRole, TradeDirection
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.portfolio.opening import open_paper_wallet
from hunter_core.redis import keys
from hunter_core.risk import evaluate_and_persist
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk import (
    BetaEstimate,
    BookLevel,
    MarketIdentity,
    MarketLiquidity,
    MarketSpec,
    PortfolioState,
    sao_paulo_day_start_utc,
)

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER_ROLE = "hunter_worker"
CAPITAL_BRL = Decimal("100000")
FX_RATE = Decimal("5.4321")
LAST_PRICE = Decimal("30000")
STOP = Decimal("29000")
# T3.68b finding 6: within RISK_ENGINE.md v2 §3.1's ``stop_distance`` band
# ([0,3 %, 3 %]) — ``STOP`` above (3,33 %) is refused by design, everywhere
# else in this file, and deliberately so (see ``TestFilingAndDeciding``).
STOP_APPROVABLE = LAST_PRICE - Decimal("300")
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


async def _insert_fx(
    session_factory: async_sessionmaker[AsyncSession], *, observed_at: datetime
) -> uuid.UUID:
    """Persist one ``fx_observations`` row as ``hunter_worker`` — T3.11's role."""
    observation_id = uuid7()
    async with role_session(session_factory, db_role=WORKER_ROLE) as session:
        await session.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                "available_at, raw) VALUES (:id, 'USDTBRL', :rate, 'binance.spot.ticker', "
                ":observed, :observed, '{}'::jsonb)"
            ),
            {"id": observation_id, "rate": FX_RATE, "observed": observed_at},
        )
    return observation_id


class Market368:
    def __init__(self, exchange: str, symbol: str, market_id: uuid.UUID, base_asset: str) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.market_id = market_id
        self.base_asset = base_asset

    @property
    def identity(self) -> MarketIdentity:
        """The identity exactly as ``hunter_core.admission.inputs.verify_market``
        will read it back from ``markets``/``exchanges``/``assets`` — mismatch
        here is ``MarketMismatch``, not a refusal named by RISK_ENGINE.md."""
        return MarketIdentity(
            exchange=self.exchange,
            symbol=self.symbol,
            market_type=MarketType.SPOT,
            base_asset=self.base_asset,
            quote_asset="USDT",
        )


async def _seed_spot_market(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    market_type: MarketType = MarketType.SPOT,
) -> Market368:
    """A fresh exchange + base/quote assets + one executable market."""
    suffix = uuid.uuid4().hex[:10]
    exchange_code = f"t368{suffix}"
    symbol = f"T368{suffix.upper()}USDT"
    base_symbol = f"B368{suffix}"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        base_asset = Asset(symbol=base_symbol)
        session.add_all([exchange, base_asset])
        await session.flush()
        quote_asset = (
            await session.execute(select(Asset).where(Asset.symbol == "USDT"))
        ).scalar_one_or_none()
        if quote_asset is None:
            quote_asset = Asset(symbol="USDT")
            session.add(quote_asset)
            await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            market_type=market_type,
            base_asset_id=base_asset.id,
            quote_asset_id=quote_asset.id,
            is_monitored=True,
            monitor_rank=1,
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.0001"),
            min_notional=Decimal("5"),
        )
        session.add(market)
        await session.commit()
        return Market368(exchange_code, symbol, market.id, base_symbol)


async def _write_ticker(
    redis_client: redis_asyncio.Redis,
    exchange: str,
    symbol: str,
    market_type: MarketType = MarketType.SPOT,
    *,
    last: Decimal = LAST_PRICE,
) -> None:
    await redis_client.hset(
        keys.ticker(exchange, symbol, market_type),
        mapping={
            "last": str(last),
            "bid": str(last - Decimal(5)),
            "ask": str(last + Decimal(5)),
            "ts": datetime.now(UTC).isoformat(),
        },
    )


class Wallet:
    def __init__(self, actor: Actor, portfolio_id: uuid.UUID, opening_equity: Decimal) -> None:
        self.actor = actor
        self.portfolio_id = portfolio_id
        self.opening_equity = opening_equity

    @property
    def base(self) -> str:
        return f"/api/v1/orgs/{self.actor.org_id}/portfolios/{self.portfolio_id}/order-requests"


async def _open_wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str,
) -> Wallet:
    unique = uuid.uuid4().hex[:8]
    actor = await create_org(client, make_actor(f"{name}-{unique}"), f"T368 {name} {unique}")
    assert actor.org_id is not None and actor.workspace_id is not None
    now = utcnow()
    fx_id = await _insert_fx(session_factory, observed_at=now)
    # As ``hunter_worker`` — ``infra/scripts/open_paper_wallet.py`` opens the
    # real wallet under this role (T3.11/0007_paper_roles): since ``0007`` the
    # API's own role (``hunter_app``) has no INSERT on
    # ``portfolio_equity_snapshots``, and opening writes the first point of the
    # curve. ``apps/api/tests/integration/test_portfolio_api.py``'s own
    # ``_open`` helper calls this under the *default* ``hunter_app`` and is
    # presently broken against a freshly migrated database for the same
    # reason — a pre-existing issue, reported in ``.claude/state/notes-T3.68.md``,
    # not fixed here (out of this task's scope).
    async with tenant_session(
        session_factory, actor.org_id, actor.user_id, db_role=WORKER_ROLE
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
    return Wallet(actor, result.portfolio_id, result.conversion.credited_amount)


@pytest_asyncio.fixture
async def wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> Wallet:
    return await _open_wallet(client, make_actor, session_factory, name="wallet")


@pytest_asyncio.fixture
async def market(session_factory: async_sessionmaker[AsyncSession]) -> Market368:
    return await _seed_spot_market(session_factory)


async def _join_viewer(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> Actor:
    """A second member of ``owner``'s organization, at exactly VIEWER."""
    joiner = make_actor(f"t368-viewer-{uuid.uuid4().hex[:8]}")
    created = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": joiner.email, "role": OrganizationRole.VIEWER.value},
        headers=owner.headers,
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    accepted = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)
    assert accepted.status_code == 200, accepted.text
    joiner.org_id = owner.org_id
    joiner.workspace_id = owner.workspace_id
    return joiner


def _body(market_id: uuid.UUID, *, stop: Decimal = STOP) -> dict[str, str]:
    return {"market_id": str(market_id), "direction": "long", "stop": str(stop)}


async def _rebuild_request(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    request_id: uuid.UUID,
    identity: MarketIdentity,
) -> ProposalRequest:
    """The exact ``ProposalRequest`` the API filed, read back from its own
    archived payload — the test's stand-in for
    ``hunter_execution_worker.admission_cycle.rebuild_request``, which this
    suite cannot import (``apps/api`` does not depend on
    ``services/execution-worker``). ``identity`` comes from the caller (a fresh
    ``markets`` lookup, like ``hunter_execution_worker.reference.load_market``)
    rather than from the payload — ``trade_proposals.request_payload`` never
    carries the full ``MarketIdentity``, only ``market_id``
    (``hunter_core.admission.sources.REQUEST_PAYLOAD_KEYS``)."""
    row = (
        await session.execute(
            text(
                "SELECT market_id, request_payload FROM trade_proposals "
                "WHERE organization_id = :org AND portfolio_id = :pf AND id = :id"
            ),
            {"org": org_id, "pf": portfolio_id, "id": request_id},
        )
    ).one()
    payload = row.request_payload
    return ProposalRequest(
        client_key=str(payload["client_key"]),
        organization_id=org_id,
        portfolio_id=portfolio_id,
        market_id=row.market_id,
        market=identity,
        direction=TradeDirection(payload["direction"]),
        entry_ref=Decimal(str(payload["entry_ref"])),
        stop=Decimal(str(payload["stop"])),
        requested_notional=(
            None
            if payload.get("requested_notional") is None
            else Decimal(str(payload["requested_notional"]))
        ),
        assumed_costs=AssumedCosts.model_validate(payload["assumed_costs"]),
        actor_id="t368-test-worker",
        actor_type="worker",
    )


def _liquidity(identity: MarketIdentity, *, now: datetime) -> MarketLiquidity:
    return MarketLiquidity(
        market=identity,
        data_quality="ok",
        last_price=LAST_PRICE,
        mid_price=LAST_PRICE,
        best_bid=LAST_PRICE - Decimal(5),
        best_ask=LAST_PRICE + Decimal(5),
        price_ts=now,
        asks=tuple(
            BookLevel(price=LAST_PRICE * (1 + Decimal(i) / 1000), qty=Decimal(10))
            for i in range(20)
        ),
        book_ts=now,
        quote_volume_24h=Decimal("260000000"),
        last_minute_quote_volume=Decimal("500000"),
        median_30m_quote_volume=Decimal("500000"),
        volume_window_complete=True,
        gap_state="ok",
        in_universe=True,
        participation_used_quote=Decimal(0),
        volume_ts=now,
    )


async def _decide(
    session_factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    market: Market368,
    request_id: uuid.UUID,
) -> dict[str, Any]:
    """Run the shared admission service against a filed row, as the worker
    would one second later — ``hunter_core.admission.service.admit``, the same
    function ``admission_cycle.decide_requests`` calls, in its own later
    transaction under ``hunter_worker``."""
    assert wallet.actor.org_id is not None
    now = utcnow()
    async with tenant_session(
        session_factory, wallet.actor.org_id, wallet.actor.user_id, db_role=WORKER_ROLE
    ) as session:
        request = await _rebuild_request(
            session,
            org_id=wallet.actor.org_id,
            portfolio_id=wallet.portfolio_id,
            request_id=request_id,
            identity=market.identity,
        )
        result = await admit(
            session,
            request,
            source="manual",
            liquidity=_liquidity(market.identity, now=now),
            spec=MarketSpec(
                market=market.identity, step_size=Decimal("0.0001"), min_notional=Decimal(5)
            ),
            beta=BetaEstimate(value=Decimal("0.5"), as_of=now, validated=True, bars=720),
            prices={},
            betas={},
            exit_cost_rate=Decimal(0),
            now=now,
        )
    return result.decision.to_jsonable()


async def _latch_kill_switch(
    session_factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Drive the wallet's kill switch to TRADING_DISABLED via a 2% daily loss —
    the exact mechanics ``apps/api/tests/integration/test_risk_api.py``'s own
    ``block`` helper uses, restated here (that helper is private to its file)."""
    assert wallet.actor.org_id is not None
    now = utcnow()
    dropped = (wallet.opening_equity * Decimal("0.97")).quantize(Decimal("0.01"))
    state = PortfolioState(
        portfolio_id=wallet.portfolio_id,
        as_of=now,
        equity=dropped,
        cash=dropped,
        peak_equity=wallet.opening_equity,
        day_start_equity=wallet.opening_equity,
        day_start_utc=sao_paulo_day_start_utc(now),
    )
    async with tenant_session(
        session_factory, wallet.actor.org_id, wallet.actor.user_id, db_role=WORKER_ROLE
    ) as session:
        await evaluate_and_persist(session, wallet.portfolio_id, state, now)


class TestFilingAndDeciding:
    async def test_202_pending_then_decided_writes_the_engines_audit_row(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        org_id = wallet.actor.org_id
        assert org_id is not None
        await _write_ticker(redis_client, market.exchange, market.symbol)
        key = f"t368-{uuid.uuid4().hex[:12]}"

        filed = await client.post(
            wallet.base,
            json=_body(market.market_id),
            headers={**wallet.actor.headers, "Idempotency-Key": key},
        )

        assert filed.status_code == 202, filed.text
        body = filed.json()
        assert body["status"] == "pending"
        assert body["decision"] is None
        request_id = uuid.UUID(body["request_id"])

        # The row exists, pending, before any decision.
        async with tenant_session(session_factory, org_id, wallet.actor.user_id) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, source FROM trade_proposals WHERE id = :id "
                        "AND organization_id = :org"
                    ),
                    {"id": request_id, "org": org_id},
                )
            ).one()
        assert (row.status, row.source) == ("pending", "manual")

        # T3.68b finding 6: this fixture's geometry (``STOP``, 3,33 % away)
        # is *always* refused by ``stop_distance`` (RISK_ENGINE.md v2 §3.1's
        # band is [0,3 %, 3 %]) — asserting ``approved in (True, False)`` here
        # was a tautology. A real approval, with a positive size and a named
        # binding constraint, is ``TestApprovedGeometry`` below.
        decision = await _decide(session_factory, wallet, market, request_id)
        assert decision["approved"] is False
        checks = {check["name"]: check for check in decision["checks"]}
        assert checks["stop_distance"]["state"] == "failed"

        read_back = await client.get(f"{wallet.base}/{request_id}", headers=wallet.actor.headers)
        assert read_back.status_code == 200, read_back.text
        detail = read_back.json()
        assert detail["status"] == "decided"
        assert detail["decision"]["approved"] == decision["approved"]

        # T3.68b finding 2: filing now leaves its own trail, with the real
        # operator's identity, next to the engine's later decision.
        async with tenant_session(session_factory, org_id, wallet.actor.user_id) as session:
            audit_rows = (
                (
                    await session.execute(
                        select(AuditLog).where(AuditLog.entity_id == str(request_id))
                    )
                )
                .scalars()
                .all()
            )
        by_action = {row.action: row for row in audit_rows}
        assert set(by_action) == {"order_request.filed", "proposal.rejected"}
        filed_row = by_action["order_request.filed"]
        assert filed_row.actor_type == "user"
        assert filed_row.actor_id == wallet.actor.user_id

    async def test_filing_the_same_key_twice_returns_the_same_request(
        self,
        client: httpx.AsyncClient,
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        await _write_ticker(redis_client, market.exchange, market.symbol)
        key = f"t368-replay-{uuid.uuid4().hex[:12]}"
        headers = {**wallet.actor.headers, "Idempotency-Key": key}

        first = await client.post(wallet.base, json=_body(market.market_id), headers=headers)
        second = await client.post(wallet.base, json=_body(market.market_id), headers=headers)

        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        assert first.json()["request_id"] == second.json()["request_id"]

    async def test_a_different_order_under_the_same_key_is_409(
        self,
        client: httpx.AsyncClient,
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        await _write_ticker(redis_client, market.exchange, market.symbol)
        key = f"t368-conflict-{uuid.uuid4().hex[:12]}"
        headers = {**wallet.actor.headers, "Idempotency-Key": key}

        first = await client.post(wallet.base, json=_body(market.market_id), headers=headers)
        assert first.status_code == 202, first.text

        conflicting = await client.post(
            wallet.base, json=_body(market.market_id, stop=STOP - Decimal(100)), headers=headers
        )

        assert conflicting.status_code == 409, conflicting.text
        assert conflicting.headers["content-type"].startswith("application/problem+json")


class TestRoleAndMarketRefusals:
    async def test_viewer_role_is_403(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        await _write_ticker(redis_client, market.exchange, market.symbol)
        viewer = await _join_viewer(client, wallet.actor, make_actor)

        response = await client.post(
            wallet.base,
            json=_body(market.market_id),
            headers={**viewer.headers, "Idempotency-Key": f"t368-viewer-{uuid.uuid4().hex[:8]}"},
        )

        assert response.status_code == 403, response.text
        assert response.headers["content-type"].startswith("application/problem+json")

    async def test_a_non_spot_market_is_422_named(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
    ) -> None:
        perp_market = await _seed_spot_market(session_factory, market_type=MarketType.PERPETUAL)

        response = await client.post(
            wallet.base,
            json=_body(perp_market.market_id),
            headers={
                **wallet.actor.headers,
                "Idempotency-Key": f"t368-perp-{uuid.uuid4().hex[:8]}",
            },
        )

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "market_not_executable_spot" in response.json()["detail"]

    async def test_an_idempotency_key_with_a_space_is_422(
        self,
        client: httpx.AsyncClient,
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        """T3.68b finding 7: the header charset is
        ``[A-Za-z0-9_.:-]`` — a space is outside it, refused before the
        value ever reaches ``admission_key``'s own ``.strip()``."""
        await _write_ticker(redis_client, market.exchange, market.symbol)

        response = await client.post(
            wallet.base,
            json=_body(market.market_id),
            headers={**wallet.actor.headers, "Idempotency-Key": "t368 has a space"},
        )

        assert response.status_code == 422, response.text


class TestTenantIsolation:
    async def test_another_organization_cannot_read_the_request(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        await _write_ticker(redis_client, market.exchange, market.symbol)
        filed = await client.post(
            wallet.base,
            json=_body(market.market_id),
            headers={**wallet.actor.headers, "Idempotency-Key": f"t368-iso-{uuid.uuid4().hex[:8]}"},
        )
        assert filed.status_code == 202, filed.text
        request_id = filed.json()["request_id"]

        outsider = await _open_wallet(client, make_actor, session_factory, name="outsider")
        response = await client.get(
            f"/api/v1/orgs/{outsider.actor.org_id}/portfolios/{wallet.portfolio_id}"
            f"/order-requests/{request_id}",
            headers=outsider.actor.headers,
        )

        assert response.status_code == 404, response.text
        assert "Organization not found" not in response.json()["detail"]
        assert response.json()["detail"] == "Portfolio not found."

        # And B's own, empty wallet never shows A's request either.
        own_list = await client.get(outsider.base, headers=outsider.actor.headers)
        assert own_list.status_code == 200, own_list.text
        assert own_list.json()["items"] == []


class TestKillSwitch:
    async def test_a_latched_kill_switch_refuses_the_entry_with_the_engines_reason(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        await _write_ticker(redis_client, market.exchange, market.symbol)
        filed = await client.post(
            wallet.base,
            json=_body(market.market_id),
            headers={**wallet.actor.headers, "Idempotency-Key": f"t368-ks-{uuid.uuid4().hex[:8]}"},
        )
        assert filed.status_code == 202, filed.text
        request_id = uuid.UUID(filed.json()["request_id"])

        await _latch_kill_switch(session_factory, wallet)

        decision = await _decide(session_factory, wallet, market, request_id)

        assert decision["approved"] is False
        checks = {check["name"]: check for check in decision["checks"]}
        assert checks["kill_switch"]["state"] == "failed"


class TestApprovedGeometry:
    async def test_a_valid_geometry_is_approved_with_a_positive_size(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: redis_asyncio.Redis,
        wallet: Wallet,
        market: Market368,
    ) -> None:
        """T3.68b finding 6: every other filing test in this file uses
        ``STOP`` (3,33 % away), which ``stop_distance`` always refuses — the
        plain filing test only ever asserted ``approved in (True, False)`` for
        that reason, a tautology. This one picks a stop 1 % away, inside
        RISK_ENGINE.md v2 §3.1's [0,3 %, 3 %] band, against the same fresh,
        liquid (``quote_volume_24h`` = R$ 260 M ≥ the R$ 50 M floor) fixture,
        and asserts a real approval with a named binding constraint and a
        positive size."""
        await _write_ticker(redis_client, market.exchange, market.symbol)
        filed = await client.post(
            wallet.base,
            json=_body(market.market_id, stop=STOP_APPROVABLE),
            headers={**wallet.actor.headers, "Idempotency-Key": f"t368-ok-{uuid.uuid4().hex[:8]}"},
        )
        assert filed.status_code == 202, filed.text
        request_id = uuid.UUID(filed.json()["request_id"])

        decision = await _decide(session_factory, wallet, market, request_id)

        assert decision["approved"] is True, decision["checks"]
        sizing = decision["sizing"]
        assert sizing is not None
        assert sizing["binding_constraint"]
        assert Decimal(sizing["qty"]) > 0


async def _insert_arena_portfolio(
    session_factory: async_sessionmaker[AsyncSession], actor: Actor
) -> uuid.UUID:
    """A second, real portfolio in ``actor``'s organization — T3.68b finding
    5's fixture. ``is_arena=True`` sits outside ``uq_portfolios_principal_paper``
    (``hunter_core.db.models.portfolios.Portfolio``, D7's "one principal
    wallet"), so it can coexist with the org's own paper wallet without this
    test touching that business rule at all. Written as ``hunter_app``
    (the default role): ``portfolios_are_born_audited``
    (``ddl/paper_roles_2.py``) only constrains a caller holding *only* the
    engine's privileges to ``type=paper, is_arena=false`` — the API "creates
    non-principal portfolios today", by that guard's own docstring."""
    assert actor.org_id is not None and actor.workspace_id is not None
    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        portfolio = Portfolio(
            organization_id=actor.org_id,
            workspace_id=actor.workspace_id,
            name="t368b-arena",
            initial_capital=Decimal("1000"),
            is_arena=True,
        )
        session.add(portfolio)
        await session.flush()
        return portfolio.id


def _org_context(org_id: uuid.UUID, user_id: uuid.UUID) -> OrgContext:
    principal = Principal(user_id=user_id, external_auth_id="t368b-test", email="t368b@example.com")
    return OrgContext(org_id=org_id, role=OrganizationRole.OWNER, principal=principal)


class TestReplayAcrossWallets:
    async def test_same_key_two_wallets_is_409_never_500(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        wallet: Wallet,
        market: Market368,
    ) -> None:
        """T3.68b finding 5: ``idempotency_key`` is unique per
        ``(organization_id, idempotency_key)`` — never per wallet.
        ``request_payload`` alone does not name the wallet (§21.1: eight
        keys, none of them ``portfolio_id``), so a second, real portfolio in
        the *same organization*, filing the identical geometry under the
        same key, used to compare equal on payload and come back naming the
        *first* wallet's proposal — which the router's own read-back then
        could not find under the caller's own ``portfolio_id``, a 500 in
        place of a 409. Exercised at ``admission.file_manual_order`` directly
        (as ``services/execution-worker/tests/test_manual_request_decided.py``
        does for the worker side), since only one *principal* paper wallet
        exists per organization and the HTTP route only ever knows the one
        the URL names."""
        assert wallet.actor.org_id is not None and wallet.actor.user_id is not None
        second_portfolio_id = await _insert_arena_portfolio(session_factory, wallet.actor)
        key = f"t368b-cross-wallet-{uuid.uuid4().hex[:12]}"
        context = _org_context(wallet.actor.org_id, wallet.actor.user_id)

        async with tenant_session(
            session_factory, wallet.actor.org_id, wallet.actor.user_id
        ) as session:
            first = await admission.file_manual_order(
                session,
                context=context,
                idempotency_key=key,
                portfolio_id=wallet.portfolio_id,
                market_id=market.market_id,
                market=market.identity,
                direction=TradeDirection.LONG,
                entry_ref=LAST_PRICE,
                stop=STOP,
                assumed_costs=COSTS,
                now=utcnow(),
            )
        assert not first.decided

        async with tenant_session(
            session_factory, wallet.actor.org_id, wallet.actor.user_id
        ) as session:
            with pytest.raises(admission.OrderReplayConflictError) as exc_info:
                await admission.file_manual_order(
                    session,
                    context=context,
                    idempotency_key=key,
                    portfolio_id=second_portfolio_id,
                    market_id=market.market_id,
                    market=market.identity,
                    direction=TradeDirection.LONG,
                    entry_ref=LAST_PRICE,
                    stop=STOP,
                    assumed_costs=COSTS,
                    now=utcnow(),
                )
        assert "order_replay_conflict" in str(exc_info.value)
