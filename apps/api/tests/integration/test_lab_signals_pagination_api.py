"""T3.37a — ``GET /api/v1/lab/shadow/signals`` real totals and cursor
pagination (brief ``.claude/state/brief-T3.37-lab-signals-real-totals-pagination.md``).

Separate file from ``test_lab_api.py`` on purpose: this is a new, focused
suite (state segments, totals-over-the-whole-dataset, page position, cursor
stability under concurrent inserts) rather than an extension of the existing
filter/pagination tests already covering the base contract.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


async def _seed_mixed_population(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    strategy_version_id,
    market_id,
    closed: int,
    open_: int,
    pending_entry: int,
    no_entry: int,
    censored: int,
) -> dict[str, list[str]]:
    """One population with a known count in every ``ShadowTrackingState`` —
    the fixture-per-state the brief asks for. Returns ids grouped by the
    *segment* (``closed``/``open``/``pending``) they belong to.
    """
    specs: list[dict[str, object]] = []
    for i in range(closed):
        decision_at = NOW - timedelta(hours=i + 1)
        entry_bar_open = decision_at + timedelta(minutes=1)
        specs.append(
            {
                "strategy_version_id": strategy_version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "entry_bar_open": entry_bar_open,
                "entry_ts": entry_bar_open,
                "exit_ts": decision_at + timedelta(hours=1),
                "exit_price": Decimal("103"),
                "result": OutcomeResult.TARGET,
                "r_multiple": Decimal("1.5"),
                "tracking_state": ShadowTrackingState.TERMINAL,
            }
        )
    for i in range(open_):
        decision_at = NOW - timedelta(hours=100 + i)
        entry_bar_open = decision_at + timedelta(minutes=1)
        specs.append(
            {
                "strategy_version_id": strategy_version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "entry_bar_open": entry_bar_open,
                "entry_ts": entry_bar_open,
                "tracking_state": ShadowTrackingState.ACTIVE,
                "result": OutcomeResult.OPEN,
            }
        )
    for i in range(pending_entry):
        decision_at = NOW - timedelta(hours=200 + i)
        specs.append(
            {
                "strategy_version_id": strategy_version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "tracking_state": ShadowTrackingState.PENDING_ENTRY,
                "result": OutcomeResult.OPEN,
            }
        )
    for i in range(no_entry):
        decision_at = NOW - timedelta(hours=300 + i)
        specs.append(
            {
                "strategy_version_id": strategy_version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "tracking_state": ShadowTrackingState.NO_ENTRY,
                "result": OutcomeResult.OPEN,
                "no_entry_reason": "geometry",
            }
        )
    for i in range(censored):
        decision_at = NOW - timedelta(hours=400 + i)
        entry_bar_open = decision_at + timedelta(minutes=1)
        specs.append(
            {
                "strategy_version_id": strategy_version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "entry_bar_open": entry_bar_open,
                "entry_ts": entry_bar_open,
                "tracking_state": ShadowTrackingState.CENSORED,
                "result": OutcomeResult.OPEN,
                "censored_reason": f"gap:{decision_at.isoformat()}",
            }
        )
    ids = await fx.seed_shadow_population(session_factory, specs)
    cursor = 0
    grouped = {"closed": [], "open": [], "pending": []}
    for _ in range(closed):
        grouped["closed"].append(str(ids[cursor]))
        cursor += 1
    for _ in range(open_):
        grouped["open"].append(str(ids[cursor]))
        cursor += 1
    for _ in range(pending_entry + no_entry + censored):
        grouped["pending"].append(str(ids[cursor]))
        cursor += 1
    return grouped


async def test_totals_reflect_the_whole_dataset_not_the_loaded_page(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Everton's report (measured 2026-09-08): tabs must show real totals, not
    counts within the 200 (here, 50) rows a page happens to load.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await _seed_mixed_population(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        closed=60,
        open_=3,
        pending_entry=2,
        no_entry=1,
        censored=1,
    )
    actor: Actor = make_actor("lab-signals-totals-whole-dataset")

    response = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&page_size=50",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 50  # the loaded page is a strict subset
    assert body["totals"] == {"closed": 60, "open": 3, "pending": 4, "all": 67}


async def test_totals_are_identical_across_every_page_of_the_same_query(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await _seed_mixed_population(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        closed=55,
        open_=0,
        pending_entry=0,
        no_entry=0,
        censored=0,
    )
    actor: Actor = make_actor("lab-signals-totals-stable-across-pages")

    first = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&page_size=50",
        headers=actor.headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}"
        f"&page_size=50&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()

    assert (
        first_body["totals"]
        == second_body["totals"]
        == {
            "closed": 55,
            "open": 0,
            "pending": 0,
            "all": 55,
        }
    )
    assert first_body["page"] == {"from": 1, "to": 50}
    assert second_body["page"] == {"from": 51, "to": 55}


@pytest.mark.parametrize(
    ("state", "expect_key"),
    [("closed", "closed"), ("open", "open"), ("pending", "pending"), ("all", "all")],
)
async def test_state_filter_matches_the_segment_definition_one_fixture_per_state(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    state: str,
    expect_key: str,
) -> None:
    """Mirrors ``apps/web/components/lab/lab-signal-segments.ts``'s
    ``matchesSegment``: one fixture per state (T3.37 brief).
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    grouped = await _seed_mixed_population(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        closed=2,
        open_=2,
        pending_entry=1,
        no_entry=1,
        censored=1,
    )
    actor: Actor = make_actor(f"lab-signals-state-{state}")

    response = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&state={state}&page_size=50",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    ids = {item["signal_id"] for item in response.json()["items"]}
    if state == "all":
        assert ids == set(grouped["closed"]) | set(grouped["open"]) | set(grouped["pending"])
    else:
        assert ids == set(grouped[expect_key])


async def test_page_position_is_scoped_to_the_selected_state_not_the_whole_dataset(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``page: {from, to}`` counts within the *current state's* ordering
    (brief) -- filtering to ``state=closed`` must not carry over positions
    computed against the unfiltered set.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await _seed_mixed_population(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        closed=3,
        open_=10,
        pending_entry=0,
        no_entry=0,
        censored=0,
    )
    actor: Actor = make_actor("lab-signals-page-position-scoped")

    response = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&state=closed&page_size=50",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 3
    assert body["page"] == {"from": 1, "to": 3}
    assert body["totals"]["all"] == 13  # totals ignore the state filter


async def test_cursor_is_stable_when_a_newer_row_is_inserted_between_pages(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A keyset cursor is a value, not a position: inserting a signal newer
    than every row already paged must not shift, duplicate or drop anything
    already seen (the whole reason this brief forbids OFFSET).
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    grouped = await _seed_mixed_population(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        closed=55,
        open_=0,
        pending_entry=0,
        no_entry=0,
        censored=0,
    )
    actor: Actor = make_actor("lab-signals-cursor-stability-under-insert")

    first = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}&page_size=50",
        headers=actor.headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()

    # a brand-new decision, newer than everything already paged
    newer_id = await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW + timedelta(hours=1),
        entry_bar_open=NOW + timedelta(hours=1, minutes=1),
        entry_ts=NOW + timedelta(hours=1, minutes=1),
        exit_ts=NOW + timedelta(hours=2),
        exit_price=Decimal("103"),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
    )

    second = await client.get(
        f"/api/v1/lab/shadow/signals?strategy_version_id={version_id}"
        f"&page_size=50&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    second_ids = {item["signal_id"] for item in second_body["items"]}

    # the new row sorts before the cursor -> never appears on this "next" page
    assert str(newer_id) not in second_ids
    # every row already seen on page 1 is still absent from page 2 (no repeat)
    assert second_ids.isdisjoint({item["signal_id"] for item in first_body["items"]})
    # and nothing already-paged is silently dropped either
    assert second_ids == set(grouped["closed"][50:])
