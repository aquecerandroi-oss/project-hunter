"""Integration tests for ``GET /api/v1/radar`` — real Postgres, T2.1 models.

Every opportunity/anomaly/market row is seeded through
``analysis_fixtures.py``, which builds exactly the T2.1 SQLAlchemy models —
no dict constructed by hand to look like a row.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_api.repositories.radar_common import FEATURE_KEY_VOLATILITY, FEATURE_KEY_VOLUME
from hunter_core.domain.enums import (
    AnomalyType,
    KillSwitchState,
    MarketRegime,
    OpportunityStage,
    OpportunityStatus,
)

from . import analysis_fixtures as fx
from .conftest import Actor, build_custom_app, create_org, running

if TYPE_CHECKING:
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.clerk_api import StaticProfileSource

pytestmark = pytest.mark.integration


async def test_list_radar_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/radar")
    assert response.status_code == 401


async def test_list_radar_empty_when_no_opportunities_matches_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id, score=Decimal("10.00"))
    actor: Actor = make_actor("radar-empty")

    response = await client.get("/api/v1/radar?score_min=99", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["as_of"] is not None
    assert body["org_scoped"] is False


async def test_list_radar_never_lists_a_market_without_an_opportunity(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, _symbol, market_id = await fx.seed_market(session_factory)
    # A second market with NO opportunity row at all.
    await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id, score=Decimal("60.00"))
    actor: Actor = make_actor("radar-no-fabricated-rows")

    response = await client.get(f"/api/v1/radar?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["market_id"] == str(market_id)


async def test_list_radar_row_shape_and_null_derivation_without_org(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(
        session_factory,
        market_id,
        score=Decimal("62.50"),
        confidence=Decimal("0.6600"),
        status=OpportunityStatus.WATCHING,
        stage=OpportunityStage.EARLY,
    )
    actor: Actor = make_actor("radar-row-shape")

    response = await client.get(f"/api/v1/radar?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["exchange"] == exchange
    assert row["symbol"] == symbol
    assert row["score"] == "62.50"
    assert row["confidence"] == "0.6600"
    assert row["status"] == "WATCHING"
    assert row["stage"] == "EARLY"
    assert row["in_position"] is None
    assert row["risk_blocked"] is None
    assert isinstance(row["change"], str)
    assert Decimal(row["change"]) == Decimal("0")


async def test_list_radar_score_min_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _s1, low_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, low_id, score=Decimal("20.00"))
    _e2, _s2, high_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, high_id, score=Decimal("80.00"))
    actor: Actor = make_actor("radar-score-min")

    response = await client.get("/api/v1/radar?score_min=50", headers=actor.headers)

    assert response.status_code == 200, response.text
    market_ids = {item["market_id"] for item in response.json()["items"]}
    assert str(high_id) in market_ids
    assert str(low_id) not in market_ids


async def test_list_radar_status_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _e1, _s1, hot_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, hot_id, status=OpportunityStatus.HOT)
    _e2, _s2, normal_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, normal_id, status=OpportunityStatus.NORMAL)
    actor: Actor = make_actor("radar-status-filter")

    response = await client.get("/api/v1/radar?status=HOT", headers=actor.headers)

    assert response.status_code == 200, response.text
    market_ids = {item["market_id"] for item in response.json()["items"]}
    assert str(hot_id) in market_ids
    assert str(normal_id) not in market_ids


async def test_list_radar_stage_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _e1, _s1, extended_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, extended_id, stage=OpportunityStage.EXTENDED)
    _e2, _s2, none_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, none_id, stage=OpportunityStage.NONE)
    actor: Actor = make_actor("radar-stage-filter")

    response = await client.get("/api/v1/radar?stage=EXTENDED", headers=actor.headers)

    assert response.status_code == 200, response.text
    market_ids = {item["market_id"] for item in response.json()["items"]}
    assert str(extended_id) in market_ids
    assert str(none_id) not in market_ids


async def test_list_radar_symbol_search(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id)
    actor: Actor = make_actor("radar-symbol-search")
    needle = symbol[2:8]

    response = await client.get(f"/api/v1/radar?q={needle}", headers=actor.headers)

    assert response.status_code == 200, response.text
    symbols = {item["symbol"] for item in response.json()["items"]}
    assert symbol in symbols


async def test_list_radar_anomaly_type_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id)
    await fx.seed_anomaly(session_factory, market_id, anomaly_type=AnomalyType.VOLUME_SPIKE)
    _e2, _s2, other_market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, other_market_id)
    actor: Actor = make_actor("radar-anomaly-filter")

    response = await client.get("/api/v1/radar?anomaly_type=VOLUME_SPIKE", headers=actor.headers)

    assert response.status_code == 200, response.text
    market_ids = {item["market_id"] for item in response.json()["items"]}
    assert str(market_id) in market_ids
    assert str(other_market_id) not in market_ids


async def test_list_radar_regime_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    regime_id = await fx.seed_regime(session_factory, regime=MarketRegime.BTC_BULL)
    _e1, _s1, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id, regime_id=regime_id)
    _e2, _s2, no_regime_market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, no_regime_market_id)
    actor: Actor = make_actor("radar-regime-filter")

    response = await client.get("/api/v1/radar?regime=BTC_BULL", headers=actor.headers)

    assert response.status_code == 200, response.text
    market_ids = {item["market_id"] for item in response.json()["items"]}
    assert str(market_id) in market_ids
    assert str(no_regime_market_id) not in market_ids
    assert response.json()["items"][0]["regime"] == "BTC_BULL"


async def test_list_radar_in_position_status_without_org_is_422(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id)
    actor: Actor = make_actor("radar-in-position-no-org")

    response = await client.get("/api/v1/radar?status=IN_POSITION", headers=actor.headers)

    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_list_radar_org_id_for_an_organization_the_caller_is_not_a_member_of_is_404(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
) -> None:
    actor: Actor = make_actor("radar-org-not-member")
    other = make_actor("radar-org-not-member-target")
    other = await create_org(client, other, "radar-org-not-member-target-org")

    response = await client.get(f"/api/v1/radar?org_id={other.org_id}", headers=actor.headers)

    assert response.status_code == 404


async def test_list_radar_in_position_derivation_never_leaks_across_organizations(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The RLS-critical case: org A has an open position on the market, org B
    does not — the same global opportunity row must read ``in_position``
    differently for each, and org B's read must never see org A's position.
    """
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id, status=OpportunityStatus.HOT)

    org_a = await create_org(client, make_actor("radar-rls-a"), "radar-rls-org-a")
    org_b = await create_org(client, make_actor("radar-rls-b"), "radar-rls-org-b")
    assert org_a.org_id is not None
    assert org_a.workspace_id is not None
    await fx.seed_open_position(
        session_factory,
        org_id=org_a.org_id,
        workspace_id=org_a.workspace_id,
        market_id=market_id,
    )

    response_a = await client.get(f"/api/v1/radar?org_id={org_a.org_id}", headers=org_a.headers)
    response_b = await client.get(f"/api/v1/radar?org_id={org_b.org_id}", headers=org_b.headers)

    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    row_a = next(i for i in response_a.json()["items"] if i["market_id"] == str(market_id))
    row_b = next(i for i in response_b.json()["items"] if i["market_id"] == str(market_id))
    assert row_a["in_position"] is True
    assert row_b["in_position"] is False
    assert response_a.json()["org_scoped"] is True

    # Filtering org B by IN_POSITION must return nothing for this market.
    filtered_b = await client.get(
        f"/api/v1/radar?org_id={org_b.org_id}&status=IN_POSITION", headers=org_b.headers
    )
    assert all(item["market_id"] != str(market_id) for item in filtered_b.json()["items"])

    filtered_a = await client.get(
        f"/api/v1/radar?org_id={org_a.org_id}&status=IN_POSITION", headers=org_a.headers
    )
    assert any(item["market_id"] == str(market_id) for item in filtered_a.json()["items"])


async def test_list_radar_risk_blocked_reflects_the_organizations_kill_switch(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id)
    org = await create_org(client, make_actor("radar-risk-blocked"), "radar-risk-blocked-org")
    assert org.org_id is not None
    await fx.set_org_kill_switch(
        session_factory,
        org.org_id,
        state=KillSwitchState.EMERGENCY,
        reason="fixture-kill-switch",
    )

    response = await client.get(f"/api/v1/radar?org_id={org.org_id}", headers=org.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["market_id"] == str(market_id))
    assert row["risk_blocked"] is True


async def test_list_radar_warning_kill_switch_does_not_block_entries(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """RISK_ENGINE.md §5: ``WARNING`` still allows entries (half-sized) — a
    real bug caught by Astra's diff review treated any non-``ACTIVE`` state,
    ``WARNING`` included, as blocked.
    """
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id)
    org = await create_org(client, make_actor("radar-risk-warning"), "radar-risk-warning-org")
    assert org.org_id is not None
    await fx.set_org_kill_switch(
        session_factory, org.org_id, state=KillSwitchState.WARNING, reason="daily-loss-70pct"
    )

    response = await client.get(f"/api/v1/radar?org_id={org.org_id}", headers=org.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["market_id"] == str(market_id))
    assert row["risk_blocked"] is False
    assert row["risk_blocked_reason"] is None


async def test_list_radar_garbage_cursor_returns_422_problem_json(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("radar-garbage-cursor")

    response = await client.get(
        "/api/v1/radar?cursor=!!!not-a-valid-cursor!!!", headers=actor.headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cursor")


async def test_list_radar_pagination_round_trip_by_score(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange_code, exchange_id = await fx.seed_exchange(session_factory)
    market_ids: list[str] = []
    for score in ("30.00", "40.00", "50.00"):
        _symbol, mid = await fx.seed_market_on(session_factory, exchange_id)
        await fx.seed_opportunity(session_factory, mid, score=Decimal(score))
        market_ids.append(str(mid))
    actor: Actor = make_actor("radar-pagination")

    first = await client.get(
        f"/api/v1/radar?exchange={exchange_code}&limit=2", headers=actor.headers
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/radar?exchange={exchange_code}&limit=2&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["next_cursor"] is None

    seen = [item["market_id"] for item in first_body["items"]] + [
        item["market_id"] for item in second_body["items"]
    ]
    assert set(market_ids) == set(seen)
    assert len(seen) == len(set(seen))


async def test_list_radar_serves_an_org_scoped_request_on_a_one_connection_pool(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """MF-1: one pooled connection per request, never two.

    ``db_pool_size=1, db_max_overflow=0`` makes the invariant testable instead
    of a comment: a handler that holds its own session while opening the
    organization-derivation session waits ``pool_timeout`` (30s) for a
    connection only it could release, and ends in a
    ``sqlalchemy.exc.TimeoutError``. With production's 5+5 the same bug needs
    ten concurrent callers to reproduce, which no test suite should have to
    arrange.
    """
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, market_id, score=Decimal("80.00"))
    org = await create_org(client, make_actor("radar-single-connection"), "radar-1conn-org")
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
        response = await tight_client.get(f"/api/v1/radar?org_id={org.org_id}", headers=org.headers)

    assert response.status_code == 200, response.text
    assert response.json()["org_scoped"] is True


async def test_list_radar_symbol_search_escapes_like_wildcards(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``?q=%`` is a literal percent sign, not "every market" — with a positive
    control on the same data, so the empty result cannot come from the filter
    being broken outright."""
    exchange_code, exchange_id = await fx.seed_exchange(session_factory)
    symbol, market_id = await fx.seed_market_on(session_factory, exchange_id)
    await fx.seed_opportunity(session_factory, market_id)
    actor: Actor = make_actor("radar-like-escape")

    wildcard = await client.get(
        f"/api/v1/radar?exchange={exchange_code}&q=%25", headers=actor.headers
    )
    real_substring = await client.get(
        f"/api/v1/radar?exchange={exchange_code}&q={symbol[2:8]}", headers=actor.headers
    )

    assert wildcard.status_code == 200, wildcard.text
    assert real_substring.status_code == 200, real_substring.text
    assert wildcard.json()["items"] == []
    assert [item["symbol"] for item in real_substring.json()["items"]] == [symbol]


@pytest.mark.parametrize(
    ("label", "query"),
    [
        ("score-nan", "score_min=NaN"),
        ("score-inf", "score_min=Infinity"),
        ("vol-nan", "volatility_min=NaN"),
        ("vol-huge", "volatility_max=1e400"),
    ],
)
async def test_list_radar_non_finite_decimal_query_is_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor], label: str, query: str
) -> None:
    """A ``Decimal`` query parameter with no finite bound accepts ``NaN``/
    ``Infinity``, which then reaches Postgres as a comparison that either
    errors or silently matches nothing."""
    actor: Actor = make_actor(f"radar-{label}")

    response = await client.get(f"/api/v1/radar?{query}", headers=actor.headers)

    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_list_radar_volatility_filter_and_volume_sort_read_the_real_envelope_shape(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Regression for the HIGH bug found in Astra/T2.7's cross-package review:
    ``feature_value_expr`` used to read
    ``feature_snapshot["features"]["values"][key]["value"]``, but the real
    envelope (``hunter_indicators.opportunity.envelope.opportunity_envelope``,
    T2.4) nests the vector under ``"vector"``, not ``"features"``. The bug was
    silent — no error, just an excluded row and a NULL sort key — so this test
    seeds a ``feature_snapshot`` built by *calling* ``opportunity_envelope()``
    (``analysis_fixtures.py::real_feature_snapshot``) and proves both the
    ``volatility`` filter and the ``volume`` sort actually read it.
    """
    _e1, _s1, high_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(
        session_factory,
        high_id,
        feature_snapshot=fx.real_feature_snapshot(
            {FEATURE_KEY_VOLATILITY: "0.05", FEATURE_KEY_VOLUME: "9"}
        ),
    )
    # No feature_snapshot at all: the default (`{}`) reads NULL at the same
    # path, so this row must be excluded by the filter and sort last.
    _e2, _s2, low_id = await fx.seed_market(session_factory)
    await fx.seed_opportunity(session_factory, low_id)
    actor: Actor = make_actor("radar-envelope-shape")

    filtered = await client.get("/api/v1/radar?volatility_min=0.01", headers=actor.headers)
    assert filtered.status_code == 200, filtered.text
    market_ids = {item["market_id"] for item in filtered.json()["items"]}
    assert str(high_id) in market_ids
    assert str(low_id) not in market_ids

    sorted_response = await client.get("/api/v1/radar?sort=volume&order=desc", headers=actor.headers)
    assert sorted_response.status_code == 200, sorted_response.text
    ids_in_order = [item["market_id"] for item in sorted_response.json()["items"]]
    assert ids_in_order.index(str(high_id)) < ids_in_order.index(str(low_id))


async def test_list_radar_cursor_with_a_non_finite_score_is_422_not_500(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    """A hand-built cursor holding ``NaN`` reached Postgres before this."""
    raw = f"NaN|{uuid.uuid4()}"
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    actor: Actor = make_actor("radar-nan-cursor")

    response = await client.get(f"/api/v1/radar?cursor={cursor}", headers=actor.headers)

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cursor")
