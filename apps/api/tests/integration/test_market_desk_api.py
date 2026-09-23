"""T4.82 on real Postgres: the ``spot/1`` desk trail and the news lane.

``GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/desk`` and
``.../events`` — the two reads behind the confluence screen (design
``docs/design/tela-confluencia-mercado.md`` §7a items 3 and 4).

The headline assertion is the **interval intersection**: a position opened at
10:00 and still open must come back from an 11:45 query. Everything else here
guards a specific way the payload could lie — a refusal filtered out as noise,
a venue-less headline dropped, a decimal rendered as a float, a window
silently truncated.

Every test seeds its own uniquely-named symbol, because ``spot_desk_markets``
is keyed on ``binance_symbol`` and the database is shared across the file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.db.models.market_events import MarketEvent
from hunter_core.db.models.spot_desk import SpotDeskMarket, SpotOrder, SpotPosition
from hunter_core.domain.enums import StrategyVersionStatus

from . import lab_fixtures as fx
from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

TEN = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
CURSOR = datetime(2026, 9, 23, 11, 45, tzinfo=UTC)
SINCE = CURSOR - timedelta(minutes=15)
UNTIL = CURSOR + timedelta(minutes=15)

MINT = "So11111111111111111111111111111111111111112"


def _window(since: datetime = SINCE, until: datetime = UNTIL) -> dict[str, str]:
    return {"since": since.isoformat(), "until": until.isoformat()}


async def _org(client: httpx.AsyncClient, make_actor: Callable[[str], Actor]) -> Actor:
    return await create_org(client, make_actor(f"desk-{uuid.uuid4().hex[:8]}"), "Desk RBAC Org")


async def _seed_desk_market(
    session_factory: async_sessionmaker[AsyncSession], *, enabled: bool = True
) -> str:
    """One row of the executable map, uniquely named. No FK to ``markets``:
    ``0057`` deliberately keyed it on the Binance symbol alone."""
    symbol = f"T482{uuid.uuid4().hex[:8].upper()}USDT"
    async with session_factory() as session:
        session.add(
            SpotDeskMarket(
                binance_symbol=symbol,
                base=symbol.removesuffix("USDT"),
                mint=MINT,
                units_per_binance_unit=Decimal("1"),
                kind="nativo",
                tier="A",
                liquidity_usd_at_seed=Decimal("50000000"),
                round_trip_cost_pct_at_seed=Decimal("0.00193"),
                enabled=enabled,
                note=None,
                updated_by="test",
            )
        )
        await session.commit()
    return symbol


async def _seed_signal(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    market_id = await fx.seed_lab_market(session_factory)
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=TEN - timedelta(days=1),
        status=StrategyVersionStatus.ACTIVE,
    )
    return await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=TEN,
    )


async def _seed_position(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    symbol: str,
    entry_at: datetime,
    exit_at: datetime | None,
) -> uuid.UUID:
    """A confirmed buy plus the position it opened — the exact pair the
    executor writes (``0057``'s ``entry_order_id`` is UNIQUE and NOT NULL)."""
    signal_id = await _seed_signal(session_factory)
    order_id, position_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session:
        session.add(
            SpotOrder(
                id=order_id,
                signal_id=signal_id,
                market_symbol=symbol,
                mint=MINT,
                side="buy",
                client_order_id=f"t482-{order_id.hex[:12]}",
                status="confirmed",
                tx_signature=f"sig-{order_id.hex}",
                fill={"lamports": 50000000},
                quote={"outAmount": "123", "priceImpactPct": "0.001"},
                admission={"checks": [], "sizing": {"binding_constraint": "ticket"}},
                received_at=entry_at,
                admitted_at=entry_at,
                settled_at=entry_at,
            )
        )
        await session.flush()
        position = SpotPosition(
            id=position_id,
            signal_id=signal_id,
            entry_order_id=order_id,
            market_symbol=symbol,
            mint=MINT,
            status="open" if exit_at is None else "closed",
            entry_at=entry_at,
            entry={"sol_per_atom": "0.0000001"},
            tokens=1000,
            sol_spent_lamports=50000000,
            initial_risk_sol=Decimal("0.0125"),
            params={"stop_frac": "0.25", "horizon_s": 14400},
        )
        if exit_at is not None:
            position.exit_at = exit_at
            position.exit_ = {"sol_received": "0.06"}
            position.pnl_sol = Decimal("0.0100000000")
            position.r_multiple = Decimal("0.8000000000")
        session.add(position)
        await session.commit()
    return position_id


async def _seed_refused_order(
    session_factory: async_sessionmaker[AsyncSession], *, symbol: str, received_at: datetime
) -> uuid.UUID:
    signal_id = await _seed_signal(session_factory)
    order_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            SpotOrder(
                id=order_id,
                signal_id=signal_id,
                market_symbol=symbol,
                mint=MINT,
                side="buy",
                client_order_id=f"t482r-{order_id.hex[:12]}",
                status="refused",
                reason="parity_above_cap",
                admission={"checks": [{"name": "parity", "cap": "0.03", "value": "0.041"}]},
                received_at=received_at,
            )
        )
        await session.commit()
    return order_id


async def _get_desk(
    client: httpx.AsyncClient,
    actor: Actor,
    symbol: str,
    *,
    exchange: str = "binance",
    **params: str,
) -> httpx.Response:
    return await client.get(
        f"/api/v1/orgs/{actor.org_id}/markets/{exchange}/{symbol}/desk",
        params=params or _window(),
        headers=actor.headers,
    )


class TestTheGate:
    async def test_a_non_member_gets_404_not_403(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        """SECURITY.md §3.3 — an organization you are not in is
        indistinguishable from one that does not exist. These tables are
        global, so this dependency *is* the authorisation."""
        owner = await _org(client, make_actor)
        stranger = make_actor(f"stranger-{uuid.uuid4().hex[:8]}")
        response = await client.get(
            f"/api/v1/orgs/{owner.org_id}/markets/binance/BTCUSDT/desk",
            headers=stranger.headers,
        )
        assert response.status_code == 404

    async def test_without_a_token_it_is_401(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"/api/v1/orgs/{uuid.uuid4()}/markets/binance/BTCUSDT/desk")
        assert response.status_code == 401


class TestTheIntervalIntersection:
    async def test_a_position_opened_at_ten_and_still_open_appears_at_1145(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The design's headline case (§4A). A point query on ``entry_at``
        would answer that the desk held nothing at 11:45."""
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        position_id = await _seed_position(
            session_factory, symbol=symbol, entry_at=TEN, exit_at=None
        )
        response = await _get_desk(client, actor, symbol)
        assert response.status_code == 200, response.text
        body = response.json()
        assert [p["id"] for p in body["positions"]] == [str(position_id)]
        assert body["positions_truncated"] is False

    async def test_the_same_position_is_absent_from_a_window_before_it_opened(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        await _seed_position(session_factory, symbol=symbol, entry_at=TEN, exit_at=None)
        response = await _get_desk(
            client,
            actor,
            symbol,
            **_window(TEN - timedelta(hours=1), TEN - timedelta(minutes=30)),
        )
        assert response.json()["positions"] == []

    async def test_a_position_closed_before_the_window_is_absent(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        await _seed_position(
            session_factory, symbol=symbol, entry_at=TEN, exit_at=TEN + timedelta(minutes=30)
        )
        assert (await _get_desk(client, actor, symbol)).json()["positions"] == []

    async def test_a_position_closed_inside_the_window_carries_its_pnl_and_r(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        await _seed_position(
            session_factory, symbol=symbol, entry_at=TEN, exit_at=CURSOR - timedelta(minutes=5)
        )
        (position,) = (await _get_desk(client, actor, symbol)).json()["positions"]
        assert position["status"] == "closed"
        assert position["pnl_sol"] == "0.01", "a string, never a float"
        assert position["r_multiple"] == "0.8"
        assert position["exit_at"].startswith("2026-09-23T11:40")


class TestTheOrdersTrail:
    async def test_a_refusal_reaches_the_client_with_its_reason_and_admission(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """ "Olhamos e recusamos" (§4A) is the screen's most valuable line."""
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        order_id = await _seed_refused_order(session_factory, symbol=symbol, received_at=CURSOR)
        (order,) = (await _get_desk(client, actor, symbol)).json()["orders"]
        assert order["id"] == str(order_id)
        assert order["status"] == "refused"
        assert order["reason"] == "parity_above_cap"
        assert order["admission"]["checks"][0]["cap"] == "0.03"

    async def test_an_order_outside_the_window_is_absent(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        await _seed_refused_order(
            session_factory, symbol=symbol, received_at=UNTIL + timedelta(minutes=1)
        )
        assert (await _get_desk(client, actor, symbol)).json()["orders"] == []


class TestWhatTheDeskDoesNotOperate:
    async def test_a_symbol_outside_the_map_answers_a_null_desk_market(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        """§5, "fora do mapa, ou desligado" — an answer, not an error."""
        actor = await _org(client, make_actor)
        body = (await _get_desk(client, actor, "NOSUCHPAIRUSDT")).json()
        assert body["desk_market"] is None
        assert body["orders"] == [] and body["positions"] == []

    async def test_a_seeded_map_row_comes_back_with_its_cost_as_a_string(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        desk_market = (await _get_desk(client, actor, symbol)).json()["desk_market"]
        assert desk_market["mint"] == MINT
        assert desk_market["tier"] == "A" and desk_market["enabled"] is True
        assert desk_market["round_trip_cost_pct_at_seed"] == "0.00193"

    async def test_another_venue_never_borrows_the_binance_trail(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """``spot_desk_markets`` is keyed on ``binance_symbol``; answering a
        bybit symbol from it would be an invented trail."""
        actor = await _org(client, make_actor)
        symbol = await _seed_desk_market(session_factory)
        await _seed_position(session_factory, symbol=symbol, entry_at=TEN, exit_at=None)
        body = (await _get_desk(client, actor, symbol, exchange="bybit")).json()
        assert body["desk_market"] is None
        assert body["positions"] == [] and body["orders"] == []


class TestTheWindowContract:
    async def test_the_applied_window_is_echoed_back(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        actor = await _org(client, make_actor)
        body = (await _get_desk(client, actor, "ANYUSDT")).json()
        assert body["since"].startswith("2026-09-23T11:30")
        assert body["until"].startswith("2026-09-23T12:00")

    async def test_omitting_both_bounds_defaults_to_an_hour(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        actor = await _org(client, make_actor)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/ANYUSDT/desk", headers=actor.headers
        )
        body = response.json()
        since = datetime.fromisoformat(body["since"])
        until = datetime.fromisoformat(body["until"])
        assert until - since == timedelta(hours=1)

    async def test_an_inverted_window_is_422_and_not_an_empty_list(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        actor = await _org(client, make_actor)
        response = await _get_desk(client, actor, "ANYUSDT", **_window(UNTIL, SINCE))
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")

    async def test_a_window_past_the_cap_is_refused_rather_than_truncated(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        actor = await _org(client, make_actor)
        response = await _get_desk(
            client, actor, "ANYUSDT", **_window(UNTIL - timedelta(days=8), UNTIL)
        )
        assert response.status_code == 422
        assert "604800" in response.json()["detail"]

    async def test_a_naive_datetime_is_422(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        actor = await _org(client, make_actor)
        response = await _get_desk(
            client, actor, "ANYUSDT", since="2026-09-23T11:30:00", until="2026-09-23T12:00:00"
        )
        assert response.status_code == 422


async def _seed_event(
    session_factory: async_sessionmaker[AsyncSession], **overrides: Any
) -> uuid.UUID:
    event_id = uuid.uuid4()
    fields: dict[str, Any] = {
        "id": event_id,
        "symbol": "ZECUSDT",
        "exchange": None,
        "source": "baha",
        "kind": "listing",
        "title": "Zcash listada em novos pares",
        "url": f"https://example.test/{event_id.hex}",
        "published_at": CURSOR - timedelta(minutes=3),
        "observed_at": CURSOR - timedelta(minutes=1),
        "confidence": "reported",
        "notes": {},
        "recorded_by": "everton",
    }
    fields.update(overrides)
    async with session_factory() as session:
        session.add(MarketEvent(**fields))
        await session.commit()
    return event_id


class TestTheNewsLane:
    async def test_a_headline_naming_no_venue_reaches_every_venue(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = f"EV{uuid.uuid4().hex[:8].upper()}USDT"
        event_id = await _seed_event(session_factory, symbol=symbol, exchange=None)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
            params=_window(),
            headers=actor.headers,
        )
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [str(event_id)]

    async def test_a_headline_about_another_venue_does_not(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = f"EV{uuid.uuid4().hex[:8].upper()}USDT"
        await _seed_event(session_factory, symbol=symbol, exchange="bybit")
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
            params=_window(),
            headers=actor.headers,
        )
        assert response.json()["items"] == []

    async def test_an_item_with_no_publication_instant_is_placed_by_observed_at(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """§3 overlay 4: it is listed, with the gap named, never given an
        invented ``published_at``."""
        actor = await _org(client, make_actor)
        symbol = f"EV{uuid.uuid4().hex[:8].upper()}USDT"
        await _seed_event(session_factory, symbol=symbol, published_at=None, observed_at=CURSOR)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
            params=_window(),
            headers=actor.headers,
        )
        (item,) = response.json()["items"]
        assert item["published_at"] is None
        assert item["observed_at"].startswith("2026-09-23T11:45")

    async def test_published_and_ingested_travel_separately(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """§4C depends on the pair: the row must be able to say "published
        before the cursor, learned after it"."""
        actor = await _org(client, make_actor)
        symbol = f"EV{uuid.uuid4().hex[:8].upper()}USDT"
        await _seed_event(session_factory, symbol=symbol)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
            params=_window(),
            headers=actor.headers,
        )
        (item,) = response.json()["items"]
        assert item["published_at"] != item["ingested_at"]
        assert item["recorded_by"] == "everton"

    async def test_the_same_link_reaches_two_symbols(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Astra, review of T4.82: the unique is ``(source, url, symbol)``. One
        Binance announcement can name two pairs, and on ``(source, url)`` the
        second pair's screen would never show it."""
        actor = await _org(client, make_actor)
        tag = uuid.uuid4().hex[:8].upper()
        first, second = f"AA{tag}USDT", f"BB{tag}USDT"
        url = f"https://example.test/two-symbols-{tag}"
        await _seed_event(session_factory, symbol=first, url=url)
        await _seed_event(session_factory, symbol=second, url=url)
        for symbol in (first, second):
            response = await client.get(
                f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
                params=_window(),
                headers=actor.headers,
            )
            assert len(response.json()["items"]) == 1, symbol

    async def test_a_short_list_is_never_reported_as_truncated(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await _org(client, make_actor)
        symbol = f"EV{uuid.uuid4().hex[:8].upper()}USDT"
        await _seed_event(session_factory, symbol=symbol)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/{symbol}/events",
            params=_window(),
            headers=actor.headers,
        )
        assert response.json()["truncated"] is False

    async def test_nothing_recorded_is_an_empty_list_and_a_200(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        """A 200 with ``items: []`` is "nothing was recorded here"; the screen
        turns that into a sentence. A 5xx would be a different sentence."""
        actor = await _org(client, make_actor)
        response = await client.get(
            f"/api/v1/orgs/{actor.org_id}/markets/binance/NOTHINGUSDT/events",
            params=_window(),
            headers=actor.headers,
        )
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["truncated"] is False, (
            "an empty list and a capped list are different facts"
        )
