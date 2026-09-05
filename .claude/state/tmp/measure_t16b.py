"""T1.6b proof probe -- runs inside the api container, on the same service code
path the authenticated handlers use, against the real Postgres and Redis.

Reports two axes separately, because they fail for different reasons:
  * hot state health (ticker/book/mark component quality)  -- what T1.6b targets
  * open ingestion gaps (forces data_quality=degraded)     -- recovery backlog
"""

import asyncio
import collections
import json
import uuid
from datetime import UTC, datetime

from hunter_api.repositories.markets import MarketRepository
from hunter_api.services.markets import build_market_list_page
from hunter_api.services.system_status import build_market_status, scan_heartbeats
from hunter_core.db.session import create_engine, create_session_factory, user_session
from hunter_core.redis import create_redis
from hunter_core.settings import get_settings


async def main() -> None:
    settings = get_settings()
    redis = create_redis(settings)
    maker = create_session_factory(create_engine(settings))
    out: dict[str, object] = {"at": datetime.now(UTC).isoformat()}
    async with user_session(maker, uuid.uuid4()) as session:
        status = await build_market_status(session, redis)
        out["market_status"] = json.loads(status.model_dump_json())
        repo = MarketRepository(session)
        rows = await repo.list_markets(monitored=True)
        page = await build_market_list_page(
            session, rows, redis, limit=len(rows), cursor=None,
            stale_after_s=settings.market_stale_after_s,
        )
        out["summary"] = json.loads(page.summary.model_dump_json())
        comp: dict[str, collections.Counter[str]] = {
            "ticker": collections.Counter(),
            "book": collections.Counter(),
            "mark": collections.Counter(),
        }
        ages: dict[str, list[int]] = {"ticker": [], "book": [], "mark": []}
        gapless_ok = 0
        for item in page.items:
            c = item.components
            for name, st in (("ticker", c.ticker), ("book", c.book), ("mark", c.mark)):
                comp[name][st.quality.value] += 1
                if st.age_ms is not None:
                    ages[name].append(st.age_ms)
            if (
                c.ticker.quality.value == "ok"
                and c.book.quality.value == "ok"
                and c.mark.quality.value == "ok"
            ):
                gapless_ok += 1
        out["components"] = {k: dict(v) for k, v in comp.items()}
        out["component_age_ms_p50_p95_max"] = {
            k: (
                sorted(v)[len(v) // 2],
                sorted(v)[int(len(v) * 0.95)] if len(v) > 1 else sorted(v)[0],
                max(v),
            )
            if v
            else None
            for k, v in ages.items()
        }
        out["hot_state_ok_all_three_components"] = gapless_ok
        out["hot_state_ok_pct"] = round(100 * gapless_ok / max(len(page.items), 1), 2)
        out["heartbeats"] = [
            json.loads(h.model_dump_json()) for h in await scan_heartbeats(redis)
        ]
    print(json.dumps(out, ensure_ascii=False))


asyncio.run(main())
