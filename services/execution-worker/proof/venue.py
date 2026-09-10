"""The labelled venue the T3.5 proof runs against.

Seeding an organization, a spot market with the real filter shape, an FX
observation and the wallet is *setup*, not the proof; it lives here so
``run_proof`` reads as the timeline it is.

The exchange code is ``proof`` on purpose: nothing this module writes can ever
be read as Binance (CLAUDE.md, "mocks/fixtures live only in tests and are
labelled").
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MarketType
from hunter_core.domain.types import utcnow, uuid7
from hunter_risk.inputs import MarketIdentity

if TYPE_CHECKING:
    from datetime import datetime

EXCHANGE = "proof"
"""Labelled, on purpose: nothing written by this script can be read as Binance."""

SYMBOL = "PRFUSDT"
BASE = "PRF"
ENTRY = Decimal("100")
STOP = Decimal("97.5")
CRASH = Decimal("95")
STEP = Decimal("0.001")
TICK = Decimal("0.01")
MIN_NOTIONAL = Decimal(5)
WORKER_ROLE = "hunter_worker"

FILTERS = {
    "market_step_size": "0",
    "market_min_qty": "0",
    "market_max_qty": "0",
    "apply_min_to_market": True,
    "max_notional": None,
    "apply_max_to_market": False,
    # 0 is Binance's own "judge the NOTIONAL filter against the last price"
    # case (T3.0a §5). Declared here because nobody collects ``avgPrice`` yet,
    # and a market that needs one is deferred by the worker instead of guessed.
    "avg_price_mins": 0,
    "bid_multiplier_up": "5",
    "bid_multiplier_down": "0.2",
    "ask_multiplier_up": "5",
    "ask_multiplier_down": "0.2",
}

__all__ = [
    "BASE",
    "CRASH",
    "ENTRY",
    "EXCHANGE",
    "FILTERS",
    "MIN_NOTIONAL",
    "STEP",
    "STOP",
    "SYMBOL",
    "TICK",
    "WORKER_ROLE",
    "identity",
    "open_wallet",
    "seed",
]


def identity() -> MarketIdentity:
    return MarketIdentity(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        market_type=MarketType.SPOT,
        base_asset=BASE,
        quote_asset="USDT",
    )


async def seed(engine: Any, slug: str, *, as_of: datetime | None = None) -> dict[str, uuid.UUID]:
    """Organization, workspace, market, assets and one FX observation.

    ``as_of`` is the instant the FX observation is stamped with, and it exists
    because a **caller with a fixed clock** has to be able to say so: a test that
    decides at a hard-coded ``NOW`` and opens the wallet against an observation
    stamped ``utcnow()`` anchors the trading day (America/Sao_Paulo) on today
    and the decision on that ``NOW``, and the two stop matching the moment the
    day turns — ``daily_reference`` goes unavailable and every check of a
    perfectly good proposal reports ``unavailable`` (spec §12, trap 2: no wall
    clock). ``None`` keeps the live behaviour ``run_proof.py`` wants.
    """
    ids = {name: uuid7() for name in ("org", "ws", "exchange", "market", "base", "fx")}
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"id": ids["org"], "slug": slug},
        )
        found = await connection.scalar(
            text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": slug}
        )
        ids["org"] = found
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, :name, 'paper_trading')"
            ),
            {"id": ids["ws"], "org": ids["org"], "name": f"{slug}-proof"},
        )
        await connection.execute(
            text(
                "INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'T3.5 proof venue') "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": ids["exchange"], "code": EXCHANGE},
        )
        ids["exchange"] = await connection.scalar(
            text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
        )
        await connection.execute(
            text(
                "INSERT INTO assets (id, symbol) VALUES (:id, :symbol) "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            {"id": ids["base"], "symbol": BASE},
        )
        ids["base"] = await connection.scalar(
            text("SELECT id FROM assets WHERE symbol = :symbol"), {"symbol": BASE}
        )
        quote = await connection.scalar(text("SELECT id FROM assets WHERE symbol = 'USDT'"))
        if quote is None:
            quote = uuid7()
            await connection.execute(
                text("INSERT INTO assets (id, symbol) VALUES (:id, 'USDT')"), {"id": quote}
            )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                "VALUES (:id, :ex, :symbol, 'spot', :base, :quote, :tick, :step, :notional, true, "
                "CAST(:meta AS jsonb)) ON CONFLICT (exchange_id, symbol, market_type) "
                "DO UPDATE SET metadata = EXCLUDED.metadata, step_size = EXCLUDED.step_size"
            ),
            {
                "id": ids["market"],
                "ex": ids["exchange"],
                "symbol": SYMBOL,
                "base": ids["base"],
                "quote": quote,
                "tick": TICK,
                "step": STEP,
                "notional": MIN_NOTIONAL,
                "meta": json.dumps({"spot_market_filters": FILTERS}),
            },
        )
        ids["market"] = await connection.scalar(
            text(
                "SELECT id FROM markets WHERE exchange_id = :ex AND symbol = :symbol "
                "AND market_type = 'spot'"
            ),
            {"ex": ids["exchange"], "symbol": SYMBOL},
        )
        now = as_of or utcnow()
        await connection.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
                "VALUES (:id, 'USDTBRL', 5.0, 'binance.spot.ticker', :now, :now)"
            ),
            {"id": ids["fx"], "now": now},
        )
    return ids


async def open_wallet(
    factory: Any, ids: dict[str, uuid.UUID], *, as_of: datetime | None = None
) -> uuid.UUID:
    from hunter_core.db.repositories.fx import FxObservationRepository
    from hunter_core.portfolio.opening import WalletAlreadyOpen, open_paper_wallet

    async with tenant_session(factory, ids["org"], db_role=WORKER_ROLE) as session:
        existing = await session.scalar(
            text(
                "SELECT id FROM portfolios WHERE organization_id = :org AND type = 'paper' "
                "AND NOT is_arena AND deleted_at IS NULL"
            ),
            {"org": ids["org"]},
        )
        if existing is not None:
            return existing
        observation = await FxObservationRepository(session).get(ids["fx"])
        assert observation is not None
        try:
            result = await open_paper_wallet(
                session,
                organization_id=ids["org"],
                workspace_id=ids["ws"],
                fx=observation,
                as_of=as_of or utcnow(),
            )
        except WalletAlreadyOpen:
            raise
    await link_paper_profile(factory, ids["org"], result.portfolio_id)
    return result.portfolio_id


async def link_paper_profile(factory: Any, org_id: uuid.UUID, portfolio_id: uuid.UUID) -> uuid.UUID:
    """``docs/ACTIVATION.md`` §8b for a proof wallet: the row, and the link.

    Since T3.69b the execution-worker reads the wallet's limits from its linked
    ``risk_profiles`` row and admits **nothing** without one, so a wallet opened
    for a proof run has to carry the operator's act as well. The row is
    ``PAPER_V1.model_dump(mode="json")`` — the same bytes the seed writes, no
    number of Everton's changed. Written as ``hunter_app``: both tables are its
    own (``ddl/tables.py``), and the worker may only read them.
    """
    from hunter_risk.limits import PAPER_V1

    profile_id = uuid7()
    async with tenant_session(factory, org_id, db_role="hunter_app") as session:
        await session.execute(
            text(
                "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) VALUES "
                "(:id, :org, 'Paper v1', 'paper_v1', CAST(:limits AS jsonb))"
            ),
            {
                "id": profile_id,
                "org": org_id,
                "limits": json.dumps(PAPER_V1.model_dump(mode="json")),
            },
        )
        await session.execute(
            text("UPDATE portfolios SET risk_profile_id = :profile WHERE id = :id"),
            {"profile": profile_id, "id": portfolio_id},
        )
    return profile_id
