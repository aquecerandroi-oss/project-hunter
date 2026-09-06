"""Integration tests for ``GET /api/v1/lab/shadow/{summary,signals,versions}``.

contract-S3-lab.md is the fixed contract; SHADOW-LAB.md §9 is where the metric
names come from. Global, no-RLS reads (DATABASE.md §16) — any authenticated
user, no organization.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import OperationalError

from hunter_api.repositories import lab_signals as lab_signals_repo
from hunter_api.repositories import lab_versions as lab_versions_repo
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, StrategyVersionStatus

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


async def test_versions_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/versions")
    assert response.status_code == 401


async def test_versions_lists_catalogue_with_best_effort_superseded_by(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    strategy_id, v1_id = await fx.seed_strategy_version(
        session_factory, version="v1", status=StrategyVersionStatus.ACTIVE, activated_at=NOW
    )
    # supersede v1 -> v2 the way infra/scripts/activate_strategy_version.py writes it
    async with session_factory() as session:
        from hunter_core.db.models.agents import StrategyVersion

        row = await session.get(StrategyVersion, v1_id)
        assert row is not None
        row.status = StrategyVersionStatus.DEPRECATED
        row.deprecated_at = NOW
        row.changelog = "superseded by v2 (code_ref old -> new); some reason"
        await session.commit()
    _, v2_id = await fx.seed_strategy_version(
        session_factory,
        strategy_id=strategy_id,
        version="v2",
        status=StrategyVersionStatus.ACTIVE,
        activated_at=NOW,
    )

    actor: Actor = make_actor("lab-versions-catalogue")
    response = await client.get("/api/v1/lab/shadow/versions", headers=actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    v1_item = next(item for item in items if item["strategy_version_id"] == str(v1_id))
    assert v1_item["superseded_by"] == str(v2_id)
    assert any(item["strategy_version_id"] == str(v2_id) for item in items)


async def test_versions_returns_503_when_postgres_is_unreachable(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(lab_versions_repo.LabVersionsRepository, "list_all", _boom)
    actor: Actor = make_actor("lab-versions-503")

    response = await client.get("/api/v1/lab/shadow/versions", headers=actor.headers)

    assert response.status_code == 503, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("lab-unavailable")


async def test_summary_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/summary")
    assert response.status_code == 401


async def test_summary_rejects_a_naive_as_of_with_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    """Astra, diff review, must-fix 3: a naive ``as_of`` used to reach the
    maturity gate and blow up as a ``TypeError`` (tz-aware vs tz-naive
    comparison) instead of a clean validation error.
    """
    actor: Actor = make_actor("lab-summary-naive-as-of")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": "2026-09-06T12:00:00"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-as-of")


async def test_summary_rejects_a_malformed_cohort_with_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("lab-summary-bad-cohort")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "cohort": "prospectve"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text


async def test_summary_empty_state_is_honest_zeros_not_404(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(session_factory, activated_at=NOW)
    actor: Actor = make_actor("lab-summary-empty")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "SOMBRA — hipotético, sem capital, custos assumidos"
    assert body["as_of"] is not None
    version = next(v for v in body["versions"] if v["strategy_version_id"] == str(version_id))
    assert version["counts"]["signals_emitted"] == 0
    assert version["counts"]["decisions"] is None
    assert version["metrics"]["net_profit_rate"] == {"value": None, "reason": "no_sample"}
    assert version["metrics"]["profit_factor"]["reason"] == "no_sample"
    assert version["maturity"]["inconclusive"] is True
    assert version["portfolio_pnl"] is None
    assert version["portfolio_pnl_reason"] == "not_applicable"


async def test_summary_counts_and_metrics_over_a_mixed_population(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    old_decision = NOW - timedelta(hours=6)
    entry_bar_open = old_decision + timedelta(minutes=1)

    # a matured winner
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=old_decision,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=old_decision + timedelta(hours=1),
        exit_price=Decimal("103"),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
    )
    # a matured loser
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=old_decision,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=old_decision + timedelta(hours=2),
        exit_price=Decimal("99"),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
    )
    # no_entry
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=old_decision,
        tracking_state=ShadowTrackingState.NO_ENTRY,
        result=OutcomeResult.OPEN,
        no_entry_reason="late:delay",
    )
    # censored, gap with the third segment missing (real local data shape)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=old_decision,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        tracking_state=ShadowTrackingState.CENSORED,
        result=OutcomeResult.OPEN,
        censored_reason="gap:2026-09-06T00:54:00+00:00",
    )
    actor: Actor = make_actor("lab-summary-mixed")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat(), "cohort": "prospective"},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    counts = version["counts"]
    assert counts["signals_emitted"] == 4
    assert counts["terminal"]["total"] == 2
    assert counts["terminal"]["by_result"] == {
        "target": 1,
        "stop": 1,
        "expired": 0,
        "invalidated": 0,
    }
    assert counts["no_entry"]["total"] == 1
    assert counts["no_entry"]["by_reason"]["late:delay"] == 1
    assert counts["censored"]["total"] == 1
    assert counts["censored"]["by_reason"] == {"gap:unknown": 1}
    metrics = version["metrics"]
    assert metrics["net_profit_rate"]["value"] == "0.5000"
    assert metrics["hypothetical_net_expectancy_r"]["value"] == "0.2500"
    assert metrics["profit_factor"]["sample_size"] == 2
    assert metrics["profit_factor"]["sum_positive"] == "1.5000"
    assert metrics["profit_factor"]["sum_negative_abs"] == "1.0000"
    assert version["maturity"]["evaluable_outcomes"] == 2


async def test_summary_maturity_gate_excludes_a_fast_stop_before_its_horizon_elapsed(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Astra, contract review, must-fix 2 — reproduced end to end."""
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    recent_decision = NOW - timedelta(minutes=30)
    entry_bar_open = recent_decision + timedelta(minutes=1)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=recent_decision,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=recent_decision + timedelta(minutes=25),
        exit_price=Decimal("99"),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
        horizon_s=4 * 3600,
    )
    actor: Actor = make_actor("lab-summary-maturity-gate")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    assert version["counts"]["terminal"]["total"] == 1
    assert version["maturity"]["evaluable_outcomes"] == 0
    assert version["metrics"]["net_profit_rate"] == {"value": None, "reason": "no_sample"}


async def test_summary_r_ex_funding_block_matches_known_numbers_with_a_funding_gap(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``r_ex_funding`` must be read from ``meta.r_ex_funding`` on every
    evaluable outcome — never derived from ``r_multiple`` — because a matured
    outcome can have ``r_multiple = null`` (funding not settleable, ``settle.py``)
    while ``r_ex_funding`` is still a real number, since it never depends on
    funding (contract-S3-lab.md, SHADOW-LAB.md §9). This is the reproduction
    for the mutation ``r_ex_funding_of(row)`` returning ``row.r_multiple``
    instead of reading ``meta.r_ex_funding``: that mutation would drop the
    funding-gap outcome from the block's series and coverage, shifting every
    number below.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=6)
    entry_bar_open = decision_at + timedelta(minutes=1)

    # matured winner, funding settled: r_multiple == r_ex_funding
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=decision_at + timedelta(hours=1),
        exit_price=Decimal("103"),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
        r_ex_funding=Decimal("1.5"),
    )
    # matured loser, funding settled
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=decision_at + timedelta(hours=2),
        exit_price=Decimal("99"),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1.0"),
        r_ex_funding=Decimal("-1.0"),
    )
    # matured, terminal, funding NOT settleable: r_multiple is null but
    # r_ex_funding exists — this is the row the mutation would drop
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=decision_at + timedelta(hours=3),
        exit_price=Decimal("99.5"),
        result=OutcomeResult.STOP,
        r_multiple=None,
        r_ex_funding=Decimal("-0.5"),
    )
    actor: Actor = make_actor("lab-summary-r-ex-funding")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    assert version["counts"]["funding_not_settleable"] == 1
    block = version["r_ex_funding"]
    assert block["net_profit_rate"] == {"value": "0.3333", "reason": None}
    assert block["hypothetical_net_expectancy_r"] == {"value": "0.0000", "reason": None}
    pf = block["profit_factor"]
    assert pf["value"] == "1.0000"
    assert pf["sum_positive"] == "1.5000"
    assert pf["sum_negative_abs"] == "1.5000"
    assert pf["sample_size"] == 3
    assert block["sum_of_hypothetical_r"]["value"] == "0.0000"
    assert block["sum_of_hypothetical_r"]["count"] == 3
    assert block["coverage"] == {"evaluable_outcomes": 3, "r_net_evaluable_outcomes": 2}


async def test_summary_target_rate_divides_by_target_plus_stop_not_all_terminal(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A matured population with ``target``, ``stop`` *and* ``expired``/
    ``invalidated`` outcomes: ``target_rate_among_resolved_touches`` must
    divide by ``target + stop`` only (SHADOW-LAB.md §9), never by every
    terminal outcome — the reproduction for the mutation
    ``target / terminal.total``. ``net_profit_rate`` draws from a wider
    population (every evaluable outcome with a known ``r_multiple``,
    ``expired``/``invalidated`` included), so the two rates are expected to
    disagree here.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=6)
    entry_bar_open = decision_at + timedelta(minutes=1)

    for result, r_multiple, offset_h in (
        (OutcomeResult.TARGET, Decimal("1.5"), 1),
        (OutcomeResult.TARGET, Decimal("0.8"), 2),
        (OutcomeResult.STOP, Decimal("-1.0"), 3),
        (OutcomeResult.EXPIRED, Decimal("0.3"), 4),
        (OutcomeResult.INVALIDATED, Decimal("-0.2"), 5),
    ):
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at,
            entry_bar_open=entry_bar_open,
            entry_ts=entry_bar_open,
            exit_ts=decision_at + timedelta(hours=offset_h),
            exit_price=Decimal("100"),
            result=result,
            r_multiple=r_multiple,
        )
    actor: Actor = make_actor("lab-summary-target-rate-denominator")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    assert version["counts"]["terminal"]["total"] == 5
    metrics = version["metrics"]
    assert metrics["target_rate_among_resolved_touches"] == {"value": "0.6667", "reason": None}
    assert metrics["net_profit_rate"] == {"value": "0.6000", "reason": None}
    assert metrics["hypothetical_net_expectancy_r"] == {"value": "0.2800", "reason": None}
    pf = metrics["profit_factor"]
    assert pf["sum_positive"] == "2.6000"
    assert pf["sum_negative_abs"] == "1.2000"
    assert pf["sample_size"] == 5


async def test_summary_coverage_counts_distinct_markets_not_total_signals(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Two markets share one ``strategy_version_id``: ``coverage.markets_with_
    signals`` must be the count of *distinct* markets (2), not the total
    number of signals (N + M) — the reproduction for that off-by-population
    mutation. ``coverage.distinct_days`` counts decision days over every
    signal; ``maturity.distinct_days`` counts days of *matured* outcomes only —
    the two are expected to diverge here, exactly as contract-S3-lab.md
    documents.
    """
    custom_parameters = {
        "assumed_spread_bps": "3",
        "slippage_bps": "6",
        "fee_bps": "4.5",
        "max_entry_delay_s": "90",
    }
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=3),
        default_parameters=custom_parameters,
    )
    market_a = await fx.seed_lab_market(session_factory)
    market_b = await fx.seed_lab_market(session_factory)
    day_1 = NOW - timedelta(days=2)
    day_2 = NOW - timedelta(days=1)

    # market A: 3 signals on day_1; only the first is matured/terminal
    entry_bar_open = day_1 + timedelta(minutes=1)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_a,
        decision_at=day_1,
        entry_bar_open=entry_bar_open,
        entry_ts=entry_bar_open,
        exit_ts=day_1 + timedelta(hours=1),
        exit_price=Decimal("103"),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.0"),
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_a,
        decision_at=day_1 + timedelta(minutes=5),
        tracking_state=ShadowTrackingState.NO_ENTRY,
        result=OutcomeResult.OPEN,
        no_entry_reason="geometry",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_a,
        decision_at=day_1 + timedelta(minutes=10),
        tracking_state=ShadowTrackingState.ACTIVE,
        result=OutcomeResult.OPEN,
    )

    # market B: 2 signals on day_2, none matured
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_b,
        decision_at=day_2,
        tracking_state=ShadowTrackingState.CENSORED,
        result=OutcomeResult.OPEN,
        censored_reason="gap:2026-09-06T00:00:00+00:00:failed",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_b,
        decision_at=day_2 + timedelta(minutes=5),
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("lab-summary-two-markets")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    assert version["counts"]["signals_emitted"] == 5
    coverage = version["coverage"]
    assert coverage["markets_with_signals"] == 2
    assert coverage["distinct_days"] == 2
    assert coverage["assumed_costs"] == {
        "assumed_spread_bps": "3",
        "slippage_bps": "6",
        "fee_bps": "4.5",
        "max_entry_delay_s": 90,
    }
    assert version["maturity"]["distinct_days"] == 1
    assert version["maturity"]["evaluable_outcomes"] == 1


async def test_summary_lists_two_versions_with_independent_counts(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Nice-to-have: two ``strategy_version``s in the same ``/summary`` call
    must never mix each other's rows — a shared query built without a
    per-version filter would silently sum both.
    """
    _, version_a = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=2)
    )
    _, version_b = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=2)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=2)
    for _ in range(3):
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_a,
            market_id=market_id,
            decision_at=decision_at,
            tracking_state=ShadowTrackingState.PENDING_ENTRY,
            result=OutcomeResult.OPEN,
        )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_b,
        market_id=market_id,
        decision_at=decision_at,
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("lab-summary-two-versions")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    versions = {v["strategy_version_id"]: v for v in response.json()["versions"]}
    assert versions[str(version_a)]["counts"]["signals_emitted"] == 3
    assert versions[str(version_b)]["counts"]["signals_emitted"] == 1


async def test_summary_cohort_filter_separates_prospective_from_replay(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=1)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        cohort="prospective",
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("lab-summary-cohort")

    response = await client.get(
        "/api/v1/lab/shadow/summary",
        params={"window": "all", "as_of": NOW.isoformat(), "cohort": f"replay:{market_id}"},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    version = next(
        v for v in response.json()["versions"] if v["strategy_version_id"] == str(version_id)
    )
    assert version["counts"]["signals_emitted"] == 0


async def test_signals_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/signals")
    assert response.status_code == 401


async def test_signals_empty_list_is_200_not_404(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("lab-signals-empty")

    response = await client.get(
        "/api/v1/lab/shadow/signals?strategy_version_id="
        + "0" * 8
        + "-0000-0000-0000-000000000000",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None}


async def test_signals_filters_by_tracking_state_and_result_and_pages(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    ids: list[str] = []
    for offset in range(3):
        decision_at = NOW - timedelta(hours=offset + 1)
        entry_bar_open = decision_at + timedelta(minutes=1)
        signal_id = await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at,
            entry_bar_open=entry_bar_open,
            entry_ts=entry_bar_open,
            exit_ts=decision_at + timedelta(hours=1),
            exit_price=Decimal("103"),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal("1.5"),
        )
        ids.append(str(signal_id))
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=10),
        tracking_state=ShadowTrackingState.NO_ENTRY,
        result=OutcomeResult.OPEN,
        no_entry_reason="geometry",
    )
    actor: Actor = make_actor("lab-signals-filter")

    filtered = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&tracking_state=terminal&result=target",
        headers=actor.headers,
    )
    assert filtered.status_code == 200, filtered.text
    filtered_ids = {item["signal_id"] for item in filtered.json()["items"]}
    assert filtered_ids == set(ids)

    first = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&tracking_state=terminal&limit=2",
        headers=actor.headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&tracking_state=terminal"
        f"&limit=2&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    seen = {item["signal_id"] for item in first_body["items"]} | {
        item["signal_id"] for item in second.json()["items"]
    }
    assert seen == set(ids)


async def test_signals_cursor_tie_breaks_by_id_when_decision_at_matches_across_markets(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Nice-to-have: three signals across two markets share the exact same
    ``decision_at``. The cursor's stability depends entirely on the secondary
    sort/compare on ``id`` (``repositories/lab_signals.py``); without it, a
    tie would let the second page skip or repeat a row.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_a = await fx.seed_lab_market(session_factory)
    market_b = await fx.seed_lab_market(session_factory)
    tied_decision_at = NOW - timedelta(hours=1)
    ids: list[str] = []
    for market_id in (market_a, market_b, market_a):
        signal_id = await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=tied_decision_at,
            tracking_state=ShadowTrackingState.PENDING_ENTRY,
            result=OutcomeResult.OPEN,
        )
        ids.append(str(signal_id))
    expected_order = sorted(ids, reverse=True)
    actor: Actor = make_actor("lab-signals-cursor-tie-break")

    first = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&limit=2",
        headers=actor.headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert [item["signal_id"] for item in first_body["items"]] == expected_order[:2]
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}"
        f"&limit=2&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert [item["signal_id"] for item in second_body["items"]] == expected_order[2:]


async def test_signals_garbage_cursor_returns_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("lab-signals-garbage-cursor")

    response = await client.get(
        "/api/v1/lab/shadow/signals?cursor=!!!not-a-valid-cursor!!!", headers=actor.headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cursor")


async def test_signals_envelope_is_null_unless_requested(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=1),
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("lab-signals-envelope")

    without = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}", headers=actor.headers
    )
    assert without.status_code == 200, without.text
    assert without.json()["items"][0]["supporting_features"] is None

    with_envelope = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&include=envelope",
        headers=actor.headers,
    )
    assert with_envelope.status_code == 200, with_envelope.text
    envelope = with_envelope.json()["items"][0]["supporting_features"]
    assert envelope is not None
    assert envelope["cohort"] == "prospective"


async def test_signals_returns_503_when_postgres_is_unreachable(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: object, **_kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(lab_signals_repo.LabSignalsRepository, "list_page", _boom)
    actor: Actor = make_actor("lab-signals-503")

    response = await client.get("/api/v1/lab/shadow/signals", headers=actor.headers)

    assert response.status_code == 503, response.text
    assert response.json()["type"].endswith("lab-unavailable")
