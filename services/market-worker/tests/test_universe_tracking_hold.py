"""``tracking_hold``: a market leaves the top N but not the collection.

docs/plans/SHADOW-LAB.md §8. Losing a market's 1m candles while a shadow
tracking still needs them turns an outcome that was merely *out of the ranking*
into a *censored* one — an experiment silently losing evidence. So the hold is
derived from ``shadow_episodes`` (durable, so it survives a restart), it widens
collection without making the market eligible again, and ending one version's
tracking does not release what another version still needs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7
from hunter_core.settings import Settings
from hunter_market_worker.universe import with_tracking_holds
from hunter_market_worker.universe_repo import tracking_hold_symbols

from .db_helpers import seed_market
from .fakes import FakeAdapter

pytestmark = pytest.mark.integration

EXCHANGE = "hold-exchange"
HELD = "HELDUSDT"
TOP = "TOPUSDT"


async def _open_tracking(session: Any, market_id: uuid.UUID, key: str) -> uuid.UUID:
    """A version with one ``pending_entry`` outcome holding ``market_id``."""
    strategy_id, version_id, signal_id = uuid7(), uuid7(), uuid7()
    await session.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
        {"id": strategy_id, "key": key},
    )
    await session.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status) "
            "VALUES (:id, :strategy_id, 'v1', 'active')"
        ),
        {"id": version_id, "strategy_id": strategy_id},
    )
    await session.execute(
        text(
            "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, "
            "direction, confidence, emitted_at) "
            "VALUES (:id, :version_id, :market_id, 'hash', 'long', 0.5, now())"
        ),
        {"id": signal_id, "version_id": version_id, "market_id": market_id},
    )
    await session.execute(
        text(
            "INSERT INTO signal_outcomes (signal_id, tracking_state) VALUES (:id, 'pending_entry')"
        ),
        {"id": signal_id},
    )
    await session.execute(
        text(
            "INSERT INTO shadow_episodes (id, strategy_version_id, market_id, cohort, "
            "episode_id, last_bar_close, armed, open_outcome_signal_id) "
            "VALUES (:id, :version_id, :market_id, 'prospective', :episode_id, :bar, false, :sig)"
        ),
        {
            "id": uuid7(),
            "version_id": version_id,
            "market_id": market_id,
            "episode_id": uuid7(),
            "bar": datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
            "sig": signal_id,
        },
    )
    return signal_id


@pytest.fixture
async def held_market(db_session_factory: Any) -> dict[str, Any]:
    top_id = await seed_market(db_session_factory, EXCHANGE, TOP)
    held_id = await seed_market(db_session_factory, EXCHANGE, HELD, base="HLD")
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        # start from no holds: previous tests in this module leave frozen
        # versions behind (an activated version cannot be deleted, by design)
        await session.execute(text("UPDATE shadow_episodes SET open_outcome_signal_id = NULL"))
        exchange_id = await session.scalar(
            text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
        )
        # unique per test: ``strategies.key`` is globally unique and the
        # rows below outlive one test (a version cannot be deleted once frozen)
        run = uuid.uuid4().hex[:8]
        first = await _open_tracking(session, held_id, f"hold_v1_{run}")
        second = await _open_tracking(session, held_id, f"hold_v2_{run}")
    return {
        "factory": db_session_factory,
        "exchange_id": exchange_id,
        "held_id": held_id,
        "top_id": top_id,
        "first": first,
        "second": second,
    }


async def _release(factory: Any, signal_id: uuid.UUID) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE shadow_episodes SET open_outcome_signal_id = NULL "
                "WHERE open_outcome_signal_id = :sig"
            ),
            {"sig": signal_id},
        )


async def _holds(held_market: dict[str, Any]) -> set[str]:
    async with role_session(held_market["factory"], db_role="hunter_worker") as session:
        return await tracking_hold_symbols(session, held_market["exchange_id"])


class TestTrackingHold:
    async def test_a_market_out_of_the_ranking_is_still_collected(
        self, held_market: dict[str, Any]
    ) -> None:
        monitored = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP], Settings()
        )
        assert monitored == [HELD, TOP]

    async def test_ending_one_version_does_not_release_the_other(
        self, held_market: dict[str, Any]
    ) -> None:
        assert await _holds(held_market) == {HELD}
        await _release(held_market["factory"], held_market["first"])
        assert await _holds(held_market) == {HELD}, "v2 still needs these candles"
        await _release(held_market["factory"], held_market["second"])
        assert await _holds(held_market) == set()

    async def test_the_hold_is_rebuilt_from_the_database_after_a_restart(
        self, held_market: dict[str, Any]
    ) -> None:
        """No worker memory is involved: a brand-new call, as a restarted
        process would make, reads the same durable rows."""
        first = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP], Settings()
        )
        second = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP], Settings()
        )
        assert first == second == [HELD, TOP]

    async def test_the_hold_never_makes_the_market_eligible_again(
        self, held_market: dict[str, Any]
    ) -> None:
        """``markets.is_monitored`` is what the strategy-worker reads as
        eligibility, and a hold must not touch it."""
        async with role_session(held_market["factory"], db_role="hunter_worker") as session:
            monitored = await session.scalar(
                text("SELECT is_monitored FROM markets WHERE id = :id"),
                {"id": held_market["held_id"]},
            )
        await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP], Settings()
        )
        async with role_session(held_market["factory"], db_role="hunter_worker") as session:
            after = await session.scalar(
                text("SELECT is_monitored FROM markets WHERE id = :id"),
                {"id": held_market["held_id"]},
            )
        assert after == monitored

    async def test_an_explicit_blocklist_wins_over_the_hold(
        self, held_market: dict[str, Any]
    ) -> None:
        """An operator exclusion stops collection; the affected trackings are
        censored with that reason instead of being kept alive silently."""
        settings = Settings(market_universe_blocklist=[HELD])
        monitored = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP], settings
        )
        assert monitored == [TOP]

    async def test_the_blocklist_also_removes_a_symbol_that_came_in_monitored(
        self, held_market: dict[str, Any]
    ) -> None:
        """A follower restarted with a new blocklist may be handed a stale
        snapshot that still names the blocked symbol; filtering only the hold's
        additions would leave it collecting."""
        settings = Settings(market_universe_blocklist=[TOP])
        monitored = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code=EXCHANGE), [TOP, HELD], settings
        )
        assert monitored == [HELD]

    async def test_an_unknown_exchange_changes_nothing(self, held_market: dict[str, Any]) -> None:
        monitored = await with_tracking_holds(
            held_market["factory"], FakeAdapter(code="no-such-exchange"), [TOP], Settings()
        )
        assert monitored == [TOP]
