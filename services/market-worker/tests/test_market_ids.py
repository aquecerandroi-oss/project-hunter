"""``load_market_ids`` discriminates by ``market_type`` (T3.0d).

``markets`` is unique on ``(exchange_id, symbol, market_type)``: the spot pair
and the perpetual of the same symbol are two rows. Before this test existed
the filter at ``market_ids.py:47`` had no dedicated coverage of the case that
matters -- two rows, same exchange, same symbol, different type -- only ever
exercised incidentally through callers that seeded a single listing.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_market_worker.market_ids import load_market_ids

from .db_helpers import seed_market
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_each_collector_gets_only_its_own_markets_market_id(
    db_session_factory: Any,
) -> None:
    """``binance`` perp and spot of the same symbol are two rows; a lookup
    that does not filter by type would hand either collector the other's
    ``market_id`` -- the exact bug T3.0b §5 found in the shared persist queue."""
    code = unique_code()
    perp_id = await seed_market(
        db_session_factory, code, "BTCUSDT", market_type=MarketType.PERPETUAL
    )
    spot_id = await seed_market(db_session_factory, code, "BTCUSDT", market_type=MarketType.SPOT)
    assert perp_id != spot_id

    async with _session(db_session_factory) as session:
        perp_ids = await load_market_ids(session, code, {"BTCUSDT"}, MarketType.PERPETUAL)
        spot_ids = await load_market_ids(session, code, {"BTCUSDT"}, MarketType.SPOT)

    assert perp_ids == {"BTCUSDT": perp_id}
    assert spot_ids == {"BTCUSDT": spot_id}


async def test_the_default_market_type_is_perpetual(db_session_factory: Any) -> None:
    """Every caller before T3.0b collected USDS-M perpetuals only; the default
    must keep answering exactly what it answered when spot rows did not exist."""
    code = unique_code()
    perp_id = await seed_market(
        db_session_factory, code, "ETHUSDT", market_type=MarketType.PERPETUAL
    )
    await seed_market(db_session_factory, code, "ETHUSDT", market_type=MarketType.SPOT)

    async with _session(db_session_factory) as session:
        ids = await load_market_ids(session, code, {"ETHUSDT"})

    assert ids == {"ETHUSDT": perp_id}


async def test_an_empty_symbol_set_short_circuits_without_a_query(
    db_session_factory: Any,
) -> None:
    async with _session(db_session_factory) as session:
        assert await load_market_ids(session, "binance", set()) == {}


def _session(session_factory: Any) -> Any:
    from hunter_core.db.session import role_session

    return role_session(session_factory, db_role="hunter_worker")
