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

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from hunter_api.repositories.lab_signals import (
    _IDENTITY_KEY_TEXT,  # pyright: ignore[reportPrivateUsage]
)
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
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


async def test_python_identity_key_matches_the_sql_side_text_for_a_seeded_row(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """T3.38c finding 4: the SQL-side ``_IDENTITY_KEY_TEXT`` expression
    (``repositories/lab_signals.py``, backing ``distinct_operations``) and the
    Python-side ``compute_identity_key`` (backing the API's ``identity_key``
    field) must build the exact same bytes for the same row -- same field
    order (finding 2's ``stop`` included on both sides), same separator
    (``chr(31)``, finding 4), same decimal normalization (finding 3). Every
    field on this row's identity path is non-null, so Postgres's ``concat()``
    NULL-dropping (documented on ``_IDENTITY_KEY_TEXT``) is not on the path --
    this reads back the *actual* SQL text Postgres produced for the row
    rather than re-deriving it in the test, so a future edit that drifts one
    side from the other fails here.
    """
    market_id = await fx.seed_lab_market(session_factory)
    _, version_id = await fx.seed_strategy_version(session_factory, activated_at=DECISION_AT)
    signal_id = await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=DECISION_AT,
        entry_bar_open=ENTRY_BAR_OPEN,
        entry_ts=ENTRY_BAR_OPEN,
        exit_ts=DECISION_AT.replace(hour=16),
        reference_price=ENTRY_PRICE,
        stop=Decimal("1.10000000"),
        exit_price=EXIT_PRICE,
        result=OutcomeResult.TARGET,
        tracking_state=ShadowTrackingState.TERMINAL,
        r_multiple=Decimal("1.5"),
    )
    actor: Actor = make_actor("lab-signals-identity-sql-parity")
    market_symbol = await _market_symbol(session_factory, market_id)

    response = await client.get(
        "/api/v1/lab/shadow/signals",
        params={"market": market_symbol, "page_size": 50},
        headers=actor.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    api_identity_key = body["items"][0]["identity_key"]

    async with session_factory() as session:
        stmt = (
            select(_IDENTITY_KEY_TEXT)
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(AgentSignal.id == signal_id)
        )
        sql_identity_text = (await session.execute(stmt)).scalar_one()

    assert hashlib.sha256(sql_identity_text.encode("utf-8")).hexdigest() == api_identity_key
