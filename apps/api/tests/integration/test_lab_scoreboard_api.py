"""Integration tests for ``GET /api/v1/lab/shadow/{scoreboard,curve}`` — T3.18.

Global, no-RLS reads (DATABASE.md §16): any authenticated user, no
organization, same as ``test_lab_api.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import OperationalError

from hunter_api.repositories import lab_scoreboard as lab_scoreboard_repo
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, StrategyVersionStatus

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import uuid

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


async def _seed_resolved_signal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    version_id: uuid.UUID,
    market_id: uuid.UUID,
    decision_at: datetime,
    exit_offset: timedelta,
    result: OutcomeResult,
    r_multiple: Decimal | None,
    horizon_s: int = 3600,
) -> None:
    entry_bar_open = decision_at + timedelta(minutes=1)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=decision_at + exit_offset,
        exit_price=Decimal("100"),
        result=result,
        r_multiple=r_multiple,
        horizon_s=horizon_s,
    )


async def test_scoreboard_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/scoreboard")
    assert response.status_code == 401


async def test_scoreboard_rejects_a_naive_as_of_with_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("scoreboard-naive-as-of")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": "2026-09-06T12:00:00"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-as-of")


async def test_scoreboard_excludes_a_version_with_no_signals_by_as_of(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Brief T3.18: population is "ever emitted", not "ever activated" — an
    activated version with zero signals in the frozen population must not
    appear at all (contrast with ``/summary``'s ``activated_versions()``).
    """
    _, version_id = await fx.seed_strategy_version(session_factory, activated_at=NOW)
    actor: Actor = make_actor("scoreboard-no-signals")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    ids = {row["version"]["id"] for row in response.json()["rows"]}
    assert str(version_id) not in ids


async def test_scoreboard_is_inconclusive_below_the_maturity_threshold(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=6)

    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_offset=timedelta(hours=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
    )
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_offset=timedelta(hours=2),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
    )
    actor: Actor = make_actor("scoreboard-immature")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    row = next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))
    assert row["evaluable"] == 2
    assert row["maturity"] == {
        "evaluable": 2,
        "days": 1,
        "threshold": {"outcomes": 100, "days": 30},
        "mature": False,
    }
    assert row["verdict"] == "inconclusivo"


async def test_scoreboard_reports_every_field_over_a_mixed_population(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_a = await fx.seed_lab_market(session_factory)
    market_b = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=10)

    # two winners, one loser -> hit_rate 2/3, wins 2/3, worst_streak 1
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_a,
        decision_at=decision_at,
        exit_offset=timedelta(hours=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("2.0"),
    )
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_a,
        decision_at=decision_at + timedelta(minutes=5),
        exit_offset=timedelta(hours=2),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
    )
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_b,
        decision_at=decision_at + timedelta(minutes=10),
        exit_offset=timedelta(hours=3),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.0"),
    )
    # pending / no_entry / censored, each on their own to exercise the counts
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_a,
        decision_at=decision_at + timedelta(minutes=15),
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_a,
        decision_at=decision_at + timedelta(minutes=20),
        tracking_state=ShadowTrackingState.NO_ENTRY,
        result=OutcomeResult.OPEN,
        no_entry_reason="geometry",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_b,
        decision_at=decision_at + timedelta(minutes=25),
        tracking_state=ShadowTrackingState.CENSORED,
        result=OutcomeResult.OPEN,
        censored_reason="gap:2026-09-06T00:00:00+00:00:failed",
    )
    actor: Actor = make_actor("scoreboard-mixed")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    row = next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))
    assert row["emitted"] == 6
    assert row["evaluable"] == 3
    assert row["pending"] == 1
    assert row["no_entry"] == 1
    assert row["censored"] == 1
    assert row["distinct_days"] == 1
    assert row["distinct_markets"] == 2
    assert row["hit_rate"] == {
        "value": "0.6667",
        "reason": None,
        "numerator": 2,
        "denominator": 3,
    }
    assert row["net_profit_rate"] == {
        "value": "0.6667",
        "reason": None,
        "numerator": 2,
        "denominator": 3,
    }
    assert row["expectancy_r"]["value"] == "0.6667"
    assert row["sum_r"]["value"] == "2"
    assert row["worst_streak"] == 1
    # exit order: +2.0, -1.0, +1.0 -> cumulative 2, 1, 2 -> peak 2, trough 1
    assert row["max_drawdown_r"] == "1"
    assert row["version"]["status"] == StrategyVersionStatus.ACTIVE.value
    assert row["version"]["purpose"] == "research_only"


async def test_scoreboard_worst_streak_and_drawdown_over_a_losing_run(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """+2, -1, -1, -1, +0.5 in exit order -> worst streak 3; cumulative curve
    2, 1, 0, -1, -0.5 -> peak 2, trough -1 -> drawdown 3.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=10)

    for i, r_multiple in enumerate(
        (Decimal("2"), Decimal("-1"), Decimal("-1"), Decimal("-1"), Decimal("0.5"))
    ):
        await _seed_resolved_signal(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=decision_at + timedelta(minutes=i),
            exit_offset=timedelta(hours=i + 1),
            result=OutcomeResult.TARGET if r_multiple > 0 else OutcomeResult.STOP,
            r_multiple=r_multiple,
        )
    actor: Actor = make_actor("scoreboard-drawdown")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    row = next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))
    assert row["worst_streak"] == 3
    assert row["max_drawdown_r"] == "3"


async def test_scoreboard_profit_factor_is_null_with_a_reason_when_there_are_no_losses(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=6)

    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_offset=timedelta(hours=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
    )
    actor: Actor = make_actor("scoreboard-pf-no-losses")

    response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    row = next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))
    assert row["profit_factor"] == {
        "value": None,
        "reason": "no_losses",
        "sum_positive": "1.5",
        "sum_negative_abs": "0",
        "sample_size": 1,
    }


async def test_scoreboard_returns_503_when_postgres_is_unreachable(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: object, _as_of: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(lab_scoreboard_repo.LabScoreboardRepository, "versions_with_signals", _boom)
    actor: Actor = make_actor("scoreboard-503")

    response = await client.get("/api/v1/lab/shadow/scoreboard", headers=actor.headers)

    assert response.status_code == 503, response.text
    assert response.json()["type"].endswith("lab-unavailable")


async def test_curve_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/lab/shadow/curve?version_id=" + "0" * 8 + "-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


async def test_curve_requires_version_id(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("curve-missing-version-id")

    response = await client.get("/api/v1/lab/shadow/curve", headers=actor.headers)

    assert response.status_code == 422, response.text


async def test_curve_empty_state_is_200_with_no_points_not_404(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("curve-empty")

    response = await client.get(
        "/api/v1/lab/shadow/curve?version_id=" + "0" * 8 + "-0000-0000-0000-000000000000",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["points"] == []
    assert body["truncated"] is False


async def test_curve_orders_points_by_exit_time_and_accumulates_r(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=10)

    # seed out of chronological exit order to prove the endpoint sorts
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_offset=timedelta(hours=3),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.0"),
    )
    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=decision_at + timedelta(minutes=1),
        exit_offset=timedelta(hours=1),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-0.5"),
    )
    actor: Actor = make_actor("curve-order")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy_version_id"] == str(version_id)
    assert body["truncated"] is False
    points = body["points"]
    assert len(points) == 2
    assert points[0]["r"] == "-0.5"
    assert points[0]["cum_r"] == "-0.5"
    assert points[1]["r"] == "1"
    assert points[1]["cum_r"] == "0.5"


async def test_curve_excludes_unresolved_and_no_entry_rows(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=2)

    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        tracking_state=ShadowTrackingState.NO_ENTRY,
        result=OutcomeResult.OPEN,
        no_entry_reason="geometry",
    )
    actor: Actor = make_actor("curve-excludes-unresolved")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["points"] == []


async def test_curve_is_not_gated_by_horizon_maturity_unlike_the_scoreboard(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A resolved outcome whose horizon has not fully elapsed by ``as_of``
    still plots on the curve (design note in ``services/lab_curve.py``), even
    though it would be excluded from the scoreboard's aggregate stats."""
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    recent_decision = NOW - timedelta(minutes=30)

    await _seed_resolved_signal(
        session_factory,
        version_id=version_id,
        market_id=market_id,
        decision_at=recent_decision,
        exit_offset=timedelta(minutes=25),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
        horizon_s=4 * 3600,
    )
    actor: Actor = make_actor("curve-not-matured")

    scoreboard = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )
    curve = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert scoreboard.status_code == 200, scoreboard.text
    row = next(r for r in scoreboard.json()["rows"] if r["version"]["id"] == str(version_id))
    assert row["evaluable"] == 0

    assert curve.status_code == 200, curve.text
    assert len(curve.json()["points"]) == 1


async def test_curve_returns_503_when_postgres_is_unreachable(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: object, _version_id: object, _as_of: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(lab_scoreboard_repo.LabScoreboardRepository, "rows_for", _boom)
    actor: Actor = make_actor("curve-503")

    response = await client.get(
        "/api/v1/lab/shadow/curve?version_id=" + "0" * 8 + "-0000-0000-0000-000000000000",
        headers=actor.headers,
    )

    assert response.status_code == 503, response.text
    assert response.json()["type"].endswith("lab-unavailable")
