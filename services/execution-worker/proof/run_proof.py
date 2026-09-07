"""The T3.5 proof driver: 30 minutes of a real worker against a real stack.

Runs **beside** the ``execution-worker`` container, never inside it. It does the
three things an operator and a market would do, and nothing the worker itself is
supposed to do:

1. **seeds the venue** — an organization, a spot market with the real filter
   shape, an FX observation and the wallet, opened as ``hunter_worker``
   (``0007_paper_roles`` §19.6);
2. **feeds the SPOT hot state** — a book and a tape on the real keys
   (``mkt:{exchange}:spot:{symbol}:book`` / ``:trades``), in exactly the msgpack
   shape the market-worker writes. This is the "adaptador spot em modo teste"
   the brief allows while T3.0b is in flight, and it is **labelled**: the
   exchange code is ``proof``, so no row of it can ever be mistaken for Binance;
3. **files one manual order** through the shared admission service, as the
   operator, and later prints one synthetic trade **through the stop**.

Everything else — the fill, the position, the protection, the exit, the equity
curve, the kill switch — is done by the worker, from the database, with nothing
handed to it.

``--minutes`` is the wall-clock duration. The script writes a JSON report to
stdout at the end, and the milestones as they happen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import msgpack
from sqlalchemy import text

from hunter_core.admission.service import admit
from hunter_core.admission.sources import ProposalRequest
from hunter_core.db.session import create_engine, create_session_factory, tenant_session
from hunter_core.domain.enums import MarketType, OrderSide, TradeDirection
from hunter_core.domain.types import utcnow
from hunter_core.redis import create_redis, keys
from hunter_core.settings import get_settings
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import BetaEstimate, BookLevel, MarketLiquidity, MarketSpec

from .venue import (
    CRASH,
    ENTRY,
    EXCHANGE,
    MIN_NOTIONAL,
    STEP,
    STOP,
    SYMBOL,
    TICK,
    WORKER_ROLE,
    identity,
    open_wallet,
    seed,
)

_codec: Any = msgpack
"""Typed boundary for msgpack's untyped extension functions — the same idiom
``hunter_market_worker.wire`` uses, for the same reason."""

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)


def _book_payload(price: Decimal, ts: datetime) -> bytes:
    return cast(
        "bytes",
        _codec.packb(
            {
                "ts": ts.isoformat(),
                "depth": 20,
                "kind": "snapshot",
                "bids": [[str(price), "1000"]],
                "asks": [[str(price + Decimal("0.01")), "1000"]],
            },
            use_bin_type=True,
        ),
    )


def _trade_payload(price: Decimal, ts: datetime, trade_id: int) -> bytes:
    return cast(
        "bytes",
        _codec.packb(
            {
                "ts": ts.isoformat(),
                "price": str(price),
                "qty": "1",
                "side": OrderSide.BUY.value,
                "trade_id": str(trade_id),
            },
            use_bin_type=True,
        ),
    )


async def feed(redis: Any, price: Decimal, trade_id: int) -> None:
    """One book snapshot and one print on the real spot keys."""
    now = utcnow()
    await redis.set(keys.book(EXCHANGE, SYMBOL, MarketType.SPOT), _book_payload(price, now), ex=10)
    trades_key = keys.trades(EXCHANGE, SYMBOL, MarketType.SPOT)
    await redis.lpush(trades_key, _trade_payload(price, now, trade_id))
    await redis.ltrim(trades_key, 0, 199)


async def file_order(factory: Any, ids: dict[str, uuid.UUID], portfolio_id: uuid.UUID) -> Any:
    """One manual order through the shared admission service, as the operator."""
    market = identity()
    liquidity = MarketLiquidity(
        market=market,
        last_price=ENTRY,
        mid_price=ENTRY,
        best_bid=ENTRY,
        best_ask=ENTRY + Decimal("0.01"),
        price_ts=utcnow(),
        asks=(BookLevel(price=ENTRY + Decimal("0.01"), qty=Decimal(1000)),),
        book_ts=utcnow(),
        quote_volume_24h=Decimal(100_000_000),
        last_minute_quote_volume=Decimal(50_000_000),
        median_30m_quote_volume=Decimal(50_000_000),
        volume_window_complete=True,
        volume_ts=utcnow(),
        gap_state="ok",
        in_universe=True,
    )
    request = ProposalRequest(
        client_key=f"t35-proof-{uuid.uuid4().hex[:8]}",
        organization_id=ids["org"],
        portfolio_id=portfolio_id,
        market_id=ids["market"],
        market=market,
        direction=TradeDirection.LONG,
        entry_ref=ENTRY,
        stop=STOP,
        assumed_costs=COSTS,
        actor_id="t35-proof-operator",
        actor_type="user",
    )
    async with tenant_session(factory, ids["org"], db_role=WORKER_ROLE) as session:
        return await admit(
            session,
            request,
            source="manual",
            liquidity=liquidity,
            spec=MarketSpec(
                market=market, step_size=STEP, min_notional=MIN_NOTIONAL, tick_size=TICK
            ),
            beta=BetaEstimate(value=Decimal(1), as_of=utcnow(), validated=True, bars=120),
            prices={ids["market"]: ENTRY},
            betas={ids["market"]: Decimal(1)},
            exit_cost_rate=Decimal("0.001"),
            now=utcnow(),
        )


async def snapshot_state(engine: Any, portfolio_id: uuid.UUID) -> dict[str, Any]:
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM orders WHERE portfolio_id = :pf) AS orders, "
                    "(SELECT count(*) FROM fills WHERE portfolio_id = :pf) AS fills, "
                    "(SELECT count(*) FROM positions WHERE portfolio_id = :pf) AS positions, "
                    "(SELECT count(*) FROM portfolio_exit_intents WHERE portfolio_id = :pf) "
                    "AS intents, (SELECT count(*) FROM portfolio_equity_snapshots "
                    "WHERE portfolio_id = :pf AND resolution = '1m') AS curve, "
                    "(SELECT count(*) FROM trades WHERE portfolio_id = :pf) AS trades, "
                    "(SELECT kill_switch_state::text FROM portfolios WHERE id = :pf) AS latch"
                ),
                {"pf": portfolio_id},
            )
        ).one()
    return dict(row._mapping)


async def main() -> int:
    parser = argparse.ArgumentParser(description="T3.5 proof driver")
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--slug", default="ever-t35-proof")
    parser.add_argument("--order-after-s", type=float, default=45.0)
    parser.add_argument("--stop-after-s", type=float, default=300.0)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    redis = create_redis(settings)
    report: dict[str, Any] = {"started_at": utcnow().isoformat(), "milestones": []}

    def milestone(name: str, **fields: Any) -> None:
        entry = {"at": utcnow().isoformat(), "event": name, **fields}
        report["milestones"].append(entry)
        # The operator reads this stream and `.claude/state/t35-proof.md`
        # quotes it: the output *is* the artefact, the same reason
        # `infra/scripts/**` is exempt from this rule in ruff.toml.
        print(json.dumps(entry), flush=True)  # noqa: T201

    ids = await seed(engine, args.slug)
    portfolio_id = await open_wallet(factory, ids)
    report["organization_id"] = str(ids["org"])
    report["portfolio_id"] = str(portfolio_id)
    report["market_id"] = str(ids["market"])
    milestone("wallet_open", portfolio_id=str(portfolio_id))

    deadline = utcnow() + timedelta(minutes=args.minutes)
    started = utcnow()
    trade_id = 1
    ordered = False
    crashed = False
    while utcnow() < deadline:
        elapsed = (utcnow() - started).total_seconds()
        price = CRASH if crashed else ENTRY
        await feed(redis, price, trade_id)
        trade_id += 1
        if not ordered and elapsed >= args.order_after_s:
            result = await file_order(factory, ids, portfolio_id)
            ordered = True
            milestone(
                "order_admitted",
                proposal_id=str(result.proposal_id),
                approved=result.approved,
                qty=str(result.decision.sizing.qty) if result.decision.sizing else None,
                binding=result.decision.sizing.binding_constraint
                if result.decision.sizing
                else None,
            )
        if ordered and not crashed and elapsed >= args.stop_after_s:
            crashed = True
            milestone("synthetic_gap", price=str(CRASH))
        await asyncio.sleep(1)

    report["final"] = {k: str(v) for k, v in (await snapshot_state(engine, portfolio_id)).items()}
    report["ended_at"] = utcnow().isoformat()
    print(json.dumps(report, indent=2), flush=True)  # noqa: T201
    await redis.aclose()
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
