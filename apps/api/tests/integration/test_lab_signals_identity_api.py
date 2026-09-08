"""``GET /api/v1/lab/shadow/signals`` -- ``identity_key`` and
``totals.distinct_operations`` (T3.38a,
``.claude/state/brief-T3.38-lab-identical-signals-grouped.md``).

Everton's report, measured on the VPS: three sibling strategy versions
decided on the exact same ``RAYSOLUSDT`` operation (same bar, same entry,
same exit, same result) and each persisted its own row -- the table showed
three rows, and the scoreboard card counted the operation three times. This
suite proves the server-computed field the web needs to fix both: identical
signals share ``identity_key``, a near-miss (different exit) does not, and
``totals.distinct_operations`` is the row count deduplicated by it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import uuid

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

DECISION_AT = datetime(2026, 9, 8, 15, 16, tzinfo=UTC)
ENTRY_BAR_OPEN = datetime(2026, 9, 8, 15, 17, tzinfo=UTC)
ENTRY_PRICE = Decimal("1.16930116")
EXIT_PRICE = Decimal("1.1865126569")


async def _market_symbol(
    session_factory: async_sessionmaker[AsyncSession], market_id: uuid.UUID
) -> str:
    """Every assertion below scopes its query to one freshly-seeded synthetic
    market (``?market=``) rather than relying on ``state=all``/default-cohort
    ordering across the whole shared test database -- other suites in this
    same run seed thousands of ``prospective`` rows too."""
    async with session_factory() as session:
        market = await session.get(Market, market_id)
        assert market is not None
        return market.symbol


async def test_sibling_versions_deciding_the_same_operation_share_identity_key(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    market_id = await fx.seed_lab_market(session_factory)
    version_ids: list[uuid.UUID] = []
    for _ in range(3):
        _, version_id = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)
        version_ids.append(version_id)

    for version_id in version_ids:
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=DECISION_AT,
            entry_bar_open=ENTRY_BAR_OPEN,
            entry_ts=ENTRY_BAR_OPEN,
            exit_ts=DECISION_AT.replace(hour=16),
            reference_price=ENTRY_PRICE,
            exit_price=EXIT_PRICE,
            result=OutcomeResult.TARGET,
            tracking_state=ShadowTrackingState.TERMINAL,
            r_multiple=Decimal("1.5"),
        )
    actor: Actor = make_actor("lab-signals-identity-siblings")
    market_symbol = await _market_symbol(session_factory, market_id)

    response = await client.get(
        "/api/v1/lab/shadow/signals",
        params={"market": market_symbol, "page_size": 50},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 3
    identity_keys = {item["identity_key"] for item in body["items"]}
    assert len(identity_keys) == 1, body["items"]
    # a stable sha256 hex digest, not a random per-request id
    assert len(next(iter(identity_keys))) == 64


async def test_a_different_exit_price_on_the_same_bar_is_a_different_operation(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    market_id = await fx.seed_lab_market(session_factory)
    _, version_a = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)
    _, version_b = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)

    common = {
        "market_id": market_id,
        "decision_at": DECISION_AT,
        "entry_bar_open": ENTRY_BAR_OPEN,
        "entry_ts": ENTRY_BAR_OPEN,
        "exit_ts": DECISION_AT.replace(hour=16),
        "reference_price": ENTRY_PRICE,
        "result": OutcomeResult.TARGET,
        "tracking_state": ShadowTrackingState.TERMINAL,
        "r_multiple": Decimal("1.5"),
    }
    await fx.seed_shadow_signal(
        session_factory, strategy_version_id=version_a, exit_price=EXIT_PRICE, **common
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_b,
        exit_price=EXIT_PRICE + Decimal("0.0000000001"),
        **common,
    )
    actor: Actor = make_actor("lab-signals-identity-near-miss")
    market_symbol = await _market_symbol(session_factory, market_id)

    response = await client.get(
        "/api/v1/lab/shadow/signals",
        params={"market": market_symbol, "page_size": 50},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2
    identity_keys = {item["identity_key"] for item in body["items"]}
    assert len(identity_keys) == 2, body["items"]


async def test_totals_distinct_operations_counts_the_deduplicated_operations_per_state(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Isolated by a fresh synthetic market -- ``totals`` is over the whole
    filtered dataset, so this must not see any other test's rows.
    """
    market_id = await fx.seed_lab_market(session_factory)
    version_ids: list[uuid.UUID] = []
    for _ in range(3):
        _, version_id = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)
        version_ids.append(version_id)

    # three siblings, one real operation
    for version_id in version_ids:
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=DECISION_AT,
            entry_bar_open=ENTRY_BAR_OPEN,
            entry_ts=ENTRY_BAR_OPEN,
            exit_ts=DECISION_AT.replace(hour=16),
            reference_price=ENTRY_PRICE,
            exit_price=EXIT_PRICE,
            result=OutcomeResult.TARGET,
            tracking_state=ShadowTrackingState.TERMINAL,
            r_multiple=Decimal("1.5"),
        )
    # a second, genuinely different closed operation (different exit)
    _, other_version_id = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=other_version_id,
        market_id=market_id,
        decision_at=DECISION_AT,
        entry_bar_open=ENTRY_BAR_OPEN,
        entry_ts=ENTRY_BAR_OPEN,
        exit_ts=DECISION_AT.replace(hour=16),
        reference_price=ENTRY_PRICE,
        exit_price=Decimal("1.10"),
        result=OutcomeResult.STOP,
        tracking_state=ShadowTrackingState.TERMINAL,
        r_multiple=Decimal("-1"),
    )
    actor: Actor = make_actor("lab-signals-identity-totals")
    market_symbol = await _market_symbol(session_factory, market_id)

    response = await client.get(
        "/api/v1/lab/shadow/signals",
        params={"market": market_symbol, "page_size": 50},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 4
    assert body["totals"]["closed"] == 4
    assert body["totals"]["distinct_operations"]["closed"] == 2
    assert body["totals"]["all"] == 4
    assert body["totals"]["distinct_operations"]["all"] == 2
