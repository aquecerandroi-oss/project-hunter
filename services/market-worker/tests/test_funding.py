"""Only an explicit realized REST source may create funding history."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, select

from hunter_core.db.models.market_data import FundingRate
from hunter_core.db.session import role_session
from hunter_core.redis import keys
from hunter_market_worker.funding import poll_realized
from hunter_market_worker.hot_state import write_funding
from hunter_market_worker.persist import flush_batch
from hunter_market_worker.queues import PersistQueues, RealizedFunding
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_realized_rest_history_persists_without_touching_mark_time(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    current = builders.funding("BTCUSDT", exchange=code)
    settled = current.model_copy(update={"ts": current.ts - timedelta(hours=1)})

    class Adapter(FakeAdapter):
        async def fetch_realized_funding(self, symbol: str, start: Any, end: Any) -> list[Any]:
            return [settled]

    await write_funding(redis_client, current)
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    queues = PersistQueues()
    await poll_realized(db_session_factory, Adapter(code), redis_client, universe, queues, "test")
    item = queues.events.get_nowait()
    assert isinstance(item, RealizedFunding)
    await flush_batch(db_session_factory, code, [item, item])
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(select(FundingRate).where(FundingRate.market_id == market_id))
        )
    assert len(rows) == 1 and rows[0].funding_time == settled.ts
    assert (
        await redis_client.hget(keys.derivatives(code, "BTCUSDT"), "mark_ts")
        == current.ts.isoformat().encode()
    )


async def test_estimated_funding_cannot_be_inserted_as_realized(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await flush_batch(db_session_factory, code, [builders.funding("BTCUSDT", exchange=code)])
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (
            await session.scalar(select(FundingRate).where(FundingRate.market_id == market_id))
            is None
        )


# ---- MEDIUM-6: one GROUP BY, not one query per market ----------------------


async def test_poll_realized_watermark_statement_count_does_not_grow_with_market_count(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()

    async def _run(n: int) -> int:
        symbols = [f"SYM{i}USDT" for i in range(n)]
        for symbol in symbols:
            await seed_market(db_session_factory, code, symbol)

        class Adapter(FakeAdapter):
            async def fetch_realized_funding(self, symbol: str, start: Any, end: Any) -> list[Any]:
                return []

        universe = MonitoredUniverse()
        universe.set(symbols)
        queues = PersistQueues()

        statements: list[str] = []
        engine = db_session_factory.kw["bind"].sync_engine

        def _listener(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            await poll_realized(
                db_session_factory, Adapter(code), redis_client, universe, queues, "t"
            )
        finally:
            event.remove(engine, "before_cursor_execute", _listener)
        return len(statements)

    small = await _run(3)
    large = await _run(20)
    assert small == large
