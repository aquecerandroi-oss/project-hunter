"""What a manual order needs that the operator did not send — T3.68.

Split out of ``services/orders.py`` to keep that module under CLAUDE.md's
350-line budget (the same reason ``markets_codec``/``markets_quality`` were
split out of ``services/markets.py``): this is the *derivation* half —
whether a wallet is open, whether a market is an executable SPOT one, and the
live entry reference plus cost hypothesis off Redis hot state — and
``services/orders.py`` is the *orchestration* (file, read, list) that calls it.

Every refusal here is ``hunter_api.services.admission.OrderRefusedError`` (422)
or ``WalletNotOpenError`` (409) — the same problem+json vocabulary the write
path already returns, never a new exception type for callers to learn.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.orm import aliased

from hunter_api.services import admission
from hunter_api.services.market_status import CLOCK_SKEW_TOLERANCE_S
from hunter_api.services.markets_codec import decode_hash, to_decimal, to_timestamp
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.repositories.portfolio import PortfolioRepository
from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.redis import keys
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import MarketIdentity
from hunter_risk.limits import PAPER_V1

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "MANUAL_ORDER_SLIPPAGE_BPS",
    "MAX_ENTRY_DELAY_S",
    "costs_from_ticker",
    "ensure_wallet_open",
    "market_identity",
    "reference_and_costs",
    "spot_eligibility_reason",
]

_BPS = Decimal(10_000)

MANUAL_ORDER_SLIPPAGE_BPS = Decimal("5")
"""The manual route's assumed slippage per side — T3.68b, finding 1.

**Was** ``ExecutionPolicy().extra_slippage_bps`` (0 by default): that field is
the simulator's *extra* adjustment beyond the book's own walk, not a slippage
hypothesis on its own, and reading it as one meant a manual order was costed
at zero assumed slippage while every strategy that can propose the same
geometry (``breakout_v1``, ``momentum_v1``, ``mean_reversion_v1``,
``mean_reversion_h1_v1``, ``sweep_reclaim_v1``, ``session_orb_v1``,
``volume_anomaly_v1`` — ``hunter_core.strategies.*``) declares
``slippage_bps=Decimal("5")``. Costing an entry at 0 assumed slippage plans a
*smaller* loss at the stop than the true one, which sizes it *larger* for the
same 0,25 % ``risk_per_trade_pct`` label than the strategy path would for the
identical geometry (RISK_ENGINE.md §9, row 1) — the operator's own order must
not be the one path that gets a size the label does not honour.

5 bps is not invented for this route: it is every strategy's own convention,
read via the same helper they use, ``hunter_core.strategies.base.assumed_costs``
(``apps/api/tests/unit/test_orders_service.py`` asserts the two agree). The
``assert`` below ties it to the engine's own declared ceiling
(``hunter_risk.limits.PAPER_V1.max_slippage_pct``) so the two frozen numbers
cannot silently drift apart."""

assert MANUAL_ORDER_SLIPPAGE_BPS <= PAPER_V1.max_slippage_pct * _BPS, (
    "the manual order's assumed slippage must stay inside the engine's own max_slippage_pct ceiling"
)

MAX_ENTRY_DELAY_S = 60
"""``AssumedCosts.max_entry_delay_s`` for a manual order.

No check in ``hunter_core.admission``/``hunter_risk`` reads this field for a
manual request — it exists to answer "how long is a *signal* allowed to age
before it is untradeable" (``docs/RISK_ENGINE.md`` never names it as an
admissibility input; the field was written for the Shadow Lab envelope,
``packages/core/hunter_core/strategies/envelope.py``). It is carried only
because ``AssumedCosts`` requires a positive int. 60 s matches the convention
every existing manual-order fixture already uses
(``services/execution-worker/tests/test_manual_request_decided.py``,
``apps/api/tests/unit/test_admission_adapter.py``)."""


async def ensure_wallet_open(
    session: AsyncSession, org_id: uuid.UUID, portfolio_id: uuid.UUID
) -> None:
    """409 ``wallet_not_open`` for a wallet that has never been opened.

    An opened wallet always has a ``portfolio_currency_anchor`` row (T3.3,
    ``open_paper_wallet``'s first write) — its absence is the honest signal, not
    ``Portfolio.status`` (a *paused* wallet was opened once and stays anchored).
    """
    anchor = await PortfolioRepository(session, org_id).get_anchor(portfolio_id)
    if anchor is None:
        raise admission.WalletNotOpenError(
            f"portfolio {portfolio_id} has never been opened (reason: wallet_not_open)"
        )


def spot_eligibility_reason(
    *,
    market_type: MarketType,
    status: MarketStatus,
    is_monitored: bool,
    delisted_at: datetime | None,
    base_asset: str | None,
    quote_asset: str | None,
) -> str | None:
    """``None`` when the market is an executable SPOT one; else the 422 reason.

    Pure and DB-free on purpose (``apps/api/tests/unit/test_orders_service.py``
    exercises it directly): the brief's bar is four columns of one row, all
    true together — ``market_type='spot'``, ``status='active'``,
    ``is_monitored`` and never delisted — plus the identity actually being
    nameable (a market with no asset on record cannot build a
    :class:`~hunter_risk.inputs.MarketIdentity`).
    """
    if (
        market_type is not MarketType.SPOT
        or status is not MarketStatus.ACTIVE
        or not is_monitored
        or delisted_at is not None
    ):
        return "market_not_executable_spot"
    if base_asset is None or quote_asset is None:
        return "market_not_executable_spot"
    return None


async def market_identity(session: AsyncSession, market_id: uuid.UUID) -> MarketIdentity:
    """422, named, for anything short of an executable SPOT market.

    ``market_unknown`` (no such row) or whatever
    :func:`spot_eligibility_reason` names for one that exists.
    """
    base, quote = aliased(Asset), aliased(Asset)
    statement = (
        select(
            Exchange.code,
            Market.symbol,
            base.symbol,
            quote.symbol,
            Market.market_type,
            Market.status,
            Market.is_monitored,
            Market.delisted_at,
        )
        .select_from(Market)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .outerjoin(base, base.id == Market.base_asset_id)
        .outerjoin(quote, quote.id == Market.quote_asset_id)
        .where(Market.id == market_id)
    )
    row = (await session.execute(statement)).first()
    if row is None:
        raise admission.OrderRefusedError(
            f"market {market_id} does not exist (reason: market_unknown)"
        )
    exchange, symbol, base_asset, quote_asset, market_type, status, is_monitored, delisted_at = row
    reason = spot_eligibility_reason(
        market_type=market_type,
        status=status,
        is_monitored=is_monitored,
        delisted_at=delisted_at,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    if reason is not None:
        raise admission.OrderRefusedError(
            f"market {market_id} is not an executable SPOT market (reason: {reason}): "
            f"market_type={market_type.value}, status={status.value}, is_monitored={is_monitored}, "
            f"delisted={delisted_at is not None}"
        )
    return MarketIdentity(
        exchange=exchange,
        symbol=symbol,
        market_type=market_type,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )


def costs_from_ticker(
    ticker: Mapping[str, str], *, now: datetime
) -> tuple[Decimal, AssumedCosts] | str:
    """``(entry_ref, assumed_costs)`` from a decoded ticker hash, or the 422 reason.

    Pure: takes the already-decoded ``dict[str, str]``
    ``hunter_api.services.markets_codec.decode_hash`` produces, never touches
    Redis itself, so the reason mapping is testable without a fake client.
    ``entry_ref`` is the ticker's own ``last`` (ARCHITECTURE.md §5.3,
    ``mkt:{ex}:{sym}:ticker``) — the same field ``services/markets.py`` reads
    for the Markets page, never invented here. ``spread_bps`` is measured off
    the same ticker's ``bid``/``ask``; ``fee_bps`` is the wallet's declared,
    real schedule (``hunter_exchanges.binance_spot.fees.SPOT_VIP0`` — T3.0a, no
    BNB discount the wallet does not hold, imported lazily below so importing
    this module never pulls the whole exchange-adapters package into the API
    process for a single constant, T3.68b finding 9); ``slippage_bps`` is
    :data:`MANUAL_ORDER_SLIPPAGE_BPS`.

    ``now`` is the caller's own clock (T3.68b finding 4) — never read here —
    because the freshness of the ticker's own ``ts`` has to be measured
    against the same instant the request is being filed at, not against
    whatever the wall clock reads when this function happens to run.
    ``ts`` missing is ``spot_ticker_missing``; older than
    ``hunter_risk.limits.PAPER_V1.max_price_age_s`` (or, degenerately, from the
    future — a clock that has not been reset) is ``spot_ticker_stale``. Both
    are checked after price/spread are already known good, so a ticker this
    API has never been taught to read a timestamp from (every existing
    fixture that only sets ``last``/``bid``/``ask``) still reports the reason
    it always did.
    """
    last = to_decimal(ticker.get("last"))
    if last is None or last <= 0:
        return "spot_price_unavailable"
    bid = to_decimal(ticker.get("bid"))
    ask = to_decimal(ticker.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return "spot_spread_unavailable"
    ts = to_timestamp(ticker.get("ts"))
    if ts is None:
        return "spot_ticker_missing"
    age_s = (now - ts).total_seconds()
    if age_s < -CLOCK_SKEW_TOLERANCE_S:
        # The producer's clock (Binance ``closeTime`` or the market-worker) may
        # run a little ahead of this host; RISK_ENGINE §7.1 tolerates 2 s and
        # names it apart from staleness, so the operator looks at NTP, not Redis.
        return "spot_ticker_clock_skew"
    if age_s > PAPER_V1.max_price_age_s:
        return "spot_ticker_stale"
    from hunter_exchanges.binance_spot.fees import SPOT_VIP0

    mid = (bid + ask) / 2
    spread_bps = (ask - bid) / mid * _BPS
    costs = AssumedCosts(
        spread_bps=spread_bps,
        slippage_bps=MANUAL_ORDER_SLIPPAGE_BPS,
        fee_bps=SPOT_VIP0.taker_bps,
        max_entry_delay_s=MAX_ENTRY_DELAY_S,
    )
    return last, costs


async def reference_and_costs(
    redis: redis_asyncio.Redis, identity: MarketIdentity, *, now: datetime
) -> tuple[Decimal, AssumedCosts]:
    raw = await redis.hgetall(keys.ticker(identity.exchange, identity.symbol, identity.market_type))
    ticker = decode_hash(cast("dict[bytes, bytes]", raw))
    result = costs_from_ticker(ticker, now=now)
    if isinstance(result, str):
        raise admission.OrderRefusedError(
            f"{identity.exchange}:{identity.symbol} has no usable SPOT ticker (reason: {result})"
        )
    return result
