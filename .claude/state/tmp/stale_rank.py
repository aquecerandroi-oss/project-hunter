"""Are the stale tickers the illiquid tail, or is the worker failing them?"""

import asyncio
import json
import uuid

from hunter_api.repositories.markets import MarketRepository
from hunter_api.services.markets import build_market_list_page
from hunter_core.db.session import create_engine, create_session_factory, user_session
from hunter_core.redis import create_redis
from hunter_core.settings import get_settings


async def main() -> None:
    settings = get_settings()
    redis = create_redis(settings)
    maker = create_session_factory(create_engine(settings))
    async with user_session(maker, uuid.uuid4()) as session:
        rows = await MarketRepository(session).list_markets(monitored=True)
        page = await build_market_list_page(
            session, rows, redis, limit=len(rows), cursor=None,
            stale_after_s=settings.market_stale_after_s,
        )
    stale = [(i.monitor_rank, i.symbol, i.components.ticker.age_ms) for i in page.items
             if i.components.ticker.quality.value != "ok"]
    ok = [i.monitor_rank for i in page.items if i.components.ticker.quality.value == "ok"]
    stale.sort(key=lambda r: r[0] or 999)
    print(json.dumps({
        "stale_count": len(stale),
        "stale_ranks": [r for r, _, _ in stale],
        "stale_examples": [[r, s, a] for r, s, a in stale[:6]],
        "ok_rank_max": max(ok) if ok else None,
        "monitor_rank_median_stale": stale[len(stale) // 2][0] if stale else None,
    }, ensure_ascii=False))


asyncio.run(main())
