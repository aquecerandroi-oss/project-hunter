"""Integration tests for ``GET /api/v1/opportunities`` and ``/{id}``."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.db.models.analysis import OpportunityHistory
from hunter_core.domain.enums import AnomalyType, OpportunityStage, OpportunityStatus

from . import analysis_fixtures as fx
from .conftest import Actor, build_custom_app, create_org, running

if TYPE_CHECKING:
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.clerk_api import StaticProfileSource

pytestmark = pytest.mark.integration


async def test_list_opportunities_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/opportunities")
    assert response.status_code == 401


async def test_list_opportunities_omits_decomposition_and_detail_carries_it(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """MF-2: the decomposition is a detail-view field.

    Shipping the whole JSONB breakdown for every row of every page meant
    reading and decoding the largest column in the table for data no list
    renders. The detail endpoint still returns it in full.
    """
    exchange, symbol, market_id = await fx.seed_market(session_factory)
    decomposition = {"momentum": {"value": "70.0000", "weight": "0.2000"}}
    opportunity_id = await fx.seed_opportunity(
        session_factory,
        market_id,
        status=OpportunityStatus.HOT,
        decomposition=decomposition,
    )
    actor: Actor = make_actor("opportunities-list-decomposition")

    listed = await client.get(f"/api/v1/opportunities?exchange={exchange}", headers=actor.headers)
    detail = await client.get(f"/api/v1/opportunities/{opportunity_id}", headers=actor.headers)

    assert listed.status_code == 200, listed.text
    row = listed.json()["items"][0]
    assert row["symbol"] == symbol
    assert "decomposition" not in row
    assert row["in_position"] is None

    assert detail.status_code == 200, detail.text
    assert detail.json()["decomposition"] == decomposition


async def test_get_opportunity_detail_includes_explanation_and_baseline_ids(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    regime_id = await fx.seed_regime(session_factory)
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    baseline_id = str(uuid.uuid4())
    feature_snapshot = {
        "baseline_ids": [baseline_id],
        "features": {"values": {"atr_14_pct": {"value": "0.0123", "quality": "ok"}}},
    }
    explanation = {"text": "Volume +417% vs baseline; estágio EARLY."}
    opportunity_id = await fx.seed_opportunity(
        session_factory,
        market_id,
        regime_id=regime_id,
        explanation=explanation,
        feature_snapshot=feature_snapshot,
    )
    await fx.seed_anomaly(session_factory, market_id, anomaly_type=AnomalyType.VOLUME_SPIKE)
    actor: Actor = make_actor("opportunities-detail")

    response = await client.get(f"/api/v1/opportunities/{opportunity_id}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["explanation"] == explanation
    assert body["baseline_ids"] == [baseline_id]
    assert body["regime_id"] == str(regime_id)
    assert len(body["anomalies"]) == 1
    assert body["anomalies"][0]["type"] == "VOLUME_SPIKE"
    assert body["in_position"] is None


async def test_get_opportunity_detail_404_for_unknown_id(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("opportunities-404")

    response = await client.get(f"/api/v1/opportunities/{uuid.uuid4()}", headers=actor.headers)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_get_opportunity_detail_history_hides_envelope_unless_requested(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    opportunity_id = await fx.seed_opportunity(session_factory, market_id, score=Decimal("70.00"))
    envelope: dict[str, object] = {"as_of": "2026-09-05T12:00:00Z", "baseline_ids": []}
    async with session_factory() as session:
        session.add(
            OpportunityHistory(
                opportunity_id=opportunity_id,
                ts=datetime.now(UTC),
                score=Decimal("65.00"),
                status=OpportunityStatus.WATCHING,
                stage=OpportunityStage.NONE,
                decomposition={},
                envelope=envelope,
            )
        )
        await session.commit()
    actor: Actor = make_actor("opportunities-history-envelope")

    without_envelope = await client.get(
        f"/api/v1/opportunities/{opportunity_id}", headers=actor.headers
    )
    with_envelope = await client.get(
        f"/api/v1/opportunities/{opportunity_id}?include_envelope=true", headers=actor.headers
    )

    assert without_envelope.status_code == 200, without_envelope.text
    assert with_envelope.status_code == 200, with_envelope.text
    assert without_envelope.json()["history"][0]["envelope"] is None
    assert with_envelope.json()["history"][0]["envelope"] == envelope


async def test_get_opportunity_detail_in_position_derivation_with_org(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    opportunity_id = await fx.seed_opportunity(session_factory, market_id)
    org = await create_org(client, make_actor("opportunities-in-position"), "opp-in-position-org")
    assert org.org_id is not None
    assert org.workspace_id is not None
    await fx.seed_open_position(
        session_factory, org_id=org.org_id, workspace_id=org.workspace_id, market_id=market_id
    )

    response = await client.get(
        f"/api/v1/opportunities/{opportunity_id}?org_id={org.org_id}", headers=org.headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["in_position"] is True


async def test_list_opportunities_pagination_round_trip_never_skips_or_duplicates(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """MF-2: the page window is a keyset ``(score, id)`` seek in SQL.

    Five rows walked two at a time to the end. The two tied scores are the
    2nd and 3rd, so the tie straddles the page-1/page-2 boundary and the
    ``id`` half of the cursor is what has to place them — a tie living inside
    one page would never exercise it.
    """
    exchange_code, exchange_id = await fx.seed_exchange(session_factory)
    expected: set[str] = set()
    for score in ("90.00", "80.00", "80.00", "70.00", "60.00"):
        _symbol, market_id = await fx.seed_market_on(session_factory, exchange_id)
        opportunity_id = await fx.seed_opportunity(session_factory, market_id, score=Decimal(score))
        expected.add(str(opportunity_id))
    actor: Actor = make_actor("opportunities-pagination")

    seen: list[str] = []
    scores: list[str] = []
    cursor: str | None = None
    for _ in range(5):  # bounded: a broken cursor must fail the test, not spin
        url = f"/api/v1/opportunities?exchange={exchange_code}&limit=2"
        if cursor is not None:
            url = f"{url}&cursor={cursor}"
        page = await client.get(url, headers=actor.headers)
        assert page.status_code == 200, page.text
        body = page.json()
        seen.extend(item["id"] for item in body["items"])
        scores.extend(item["score"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert cursor is None
    assert len(seen) == len(set(seen))
    assert set(seen) == expected
    assert scores == sorted(scores, key=Decimal, reverse=True)


async def test_get_opportunity_envelope_caps_history_limit(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """MF-3: ``include_envelope=true`` with ``history_limit=500`` is 500 full
    recomputation proofs in one response — 422 naming the cap, never a silent
    truncation the caller would chart as a complete trajectory.
    """
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    opportunity_id = await fx.seed_opportunity(session_factory, market_id)
    actor: Actor = make_actor("opportunities-envelope-cap")

    too_many = await client.get(
        f"/api/v1/opportunities/{opportunity_id}?include_envelope=true&history_limit=500",
        headers=actor.headers,
    )
    at_the_cap = await client.get(
        f"/api/v1/opportunities/{opportunity_id}?include_envelope=true&history_limit=50",
        headers=actor.headers,
    )
    without_envelope = await client.get(
        f"/api/v1/opportunities/{opportunity_id}?history_limit=500", headers=actor.headers
    )

    assert too_many.status_code == 422, too_many.text
    assert too_many.headers["content-type"].startswith("application/problem+json")
    body = too_many.json()
    assert body["type"].endswith("envelope-history-limit")
    assert "50" in body["detail"]
    assert at_the_cap.status_code == 200, at_the_cap.text
    assert without_envelope.status_code == 200, without_envelope.text


async def test_opportunities_serve_list_and_detail_on_a_one_connection_pool(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """MF-1 on both routes: the detail handler derived the organization while
    already holding its own session, so it needed two pooled connections."""
    exchange, _symbol, market_id = await fx.seed_market(session_factory)
    opportunity_id = await fx.seed_opportunity(session_factory, market_id)
    org = await create_org(client, make_actor("opportunities-1conn"), "opp-1conn-org")
    assert org.org_id is not None

    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        db_pool_size=1,
        db_max_overflow=0,
    )
    async with running(app) as tight_client:
        listed = await tight_client.get(
            f"/api/v1/opportunities?exchange={exchange}&org_id={org.org_id}", headers=org.headers
        )
        detail = await tight_client.get(
            f"/api/v1/opportunities/{opportunity_id}?org_id={org.org_id}", headers=org.headers
        )

    assert listed.status_code == 200, listed.text
    assert detail.status_code == 200, detail.text
    assert listed.json()["items"][0]["in_position"] is False
    assert detail.json()["in_position"] is False


async def test_list_opportunities_symbol_search_escapes_like_wildcards(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``?q=%`` is a literal percent sign, not "every market" — with a positive
    control on the same data so the empty result cannot come from the filter
    being broken outright."""
    exchange_code, exchange_id = await fx.seed_exchange(session_factory)
    symbol, market_id = await fx.seed_market_on(session_factory, exchange_id)
    await fx.seed_opportunity(session_factory, market_id)
    actor: Actor = make_actor("opportunities-like-escape")

    wildcard = await client.get(
        f"/api/v1/opportunities?exchange={exchange_code}&q=%25", headers=actor.headers
    )
    real_substring = await client.get(
        f"/api/v1/opportunities?exchange={exchange_code}&q={symbol[2:8]}", headers=actor.headers
    )

    assert wildcard.status_code == 200, wildcard.text
    assert real_substring.status_code == 200, real_substring.text
    assert wildcard.json()["items"] == []
    assert [item["symbol"] for item in real_substring.json()["items"]] == [symbol]
