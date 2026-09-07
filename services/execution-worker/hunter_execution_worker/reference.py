"""Market reference: the identity, the filters and the fee schedule of a market.

The filters a simulated fill is judged by are the exchange's real ones, read
back from ``markets`` — the columns the universe refresh writes (``tick_size``,
``step_size``, ``min_notional``) plus the labelled ``metadata.spot_market_filters``
block that ``hunter_exchanges.binance_spot.normalize`` puts there
(EXCHANGE_INTEGRATION.md §2: raw venue detail travels only inside a named key).

Nothing is defaulted into existence. A market row without the metadata block
yields filters that carry only what the columns really say, and
``check_market_order`` then refuses what it cannot judge — a filter invented from
a plausible number is how a paper wallet books an order the exchange would have
rejected.

The fee schedule is ``SPOT_VIP0`` (0,10 % taker, no BNB deduction): the wallet
holds no BNB, and assuming a discount we do not have makes every simulated
result better than reality (``binance_spot.fees``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.enums import MarketType
from hunter_exchanges.binance_spot.fees import SPOT_VIP0, SpotFeeSchedule
from hunter_exchanges.binance_spot.filters import SpotMarketFilters
from hunter_risk.inputs import MarketIdentity, MarketSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["MarketReference", "load_market", "load_markets"]

_METADATA_KEY = "spot_market_filters"
_ZERO = Decimal(0)


def _dec(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value.is_finite() else None


@dataclass(frozen=True, slots=True)
class MarketReference:
    """One market, as everything downstream needs to name and judge it."""

    market_id: uuid.UUID
    identity: MarketIdentity
    filters: SpotMarketFilters
    fees: SpotFeeSchedule = SPOT_VIP0

    @property
    def key(self) -> tuple[str, str]:
        return (self.identity.exchange, self.identity.symbol)

    @property
    def spec(self) -> MarketSpec:
        """The engine's view of the same market — step, floor and tick."""
        return MarketSpec(
            market=self.identity,
            step_size=self.filters.effective_step_size,
            min_notional=self.filters.min_notional or _ZERO,
            tick_size=self.filters.tick_size,
        )


_SELECT = (
    "SELECT m.id AS market_id, x.code AS exchange, m.symbol, m.market_type::text AS market_type, "
    "ba.symbol AS base_asset, qa.symbol AS quote_asset, m.tick_size, m.step_size, "
    "m.min_notional, m.metadata FROM markets m JOIN exchanges x ON x.id = m.exchange_id "
    "LEFT JOIN assets ba ON ba.id = m.base_asset_id "
    "LEFT JOIN assets qa ON qa.id = m.quote_asset_id "
)


def _reference(row: Any) -> MarketReference:
    raw: dict[str, Any] = dict(row.metadata or {}).get(_METADATA_KEY) or {}
    step = _dec(row.step_size) or _ZERO
    filters = SpotMarketFilters(
        symbol=row.symbol,
        tick_size=_dec(row.tick_size) or _ZERO,
        min_price=None,
        max_price=None,
        step_size=step,
        min_qty=step,
        # ``markets`` keeps no maximum; the engine's own ceilings bind long
        # before an exchange maximum would, and a made-up cap would silently
        # truncate an order the exchange would have taken.
        max_qty=Decimal("1e18"),
        market_step_size=_dec(raw.get("market_step_size")),
        market_min_qty=_dec(raw.get("market_min_qty")),
        market_max_qty=_dec(raw.get("market_max_qty")),
        min_notional=_dec(row.min_notional),
        apply_min_to_market=bool(raw.get("apply_min_to_market", False)),
        max_notional=_dec(raw.get("max_notional")),
        apply_max_to_market=bool(raw.get("apply_max_to_market", False)),
        avg_price_mins=None if raw.get("avg_price_mins") is None else int(raw["avg_price_mins"]),
        bid_multiplier_up=_dec(raw.get("bid_multiplier_up")),
        bid_multiplier_down=_dec(raw.get("bid_multiplier_down")),
        ask_multiplier_up=_dec(raw.get("ask_multiplier_up")),
        ask_multiplier_down=_dec(raw.get("ask_multiplier_down")),
    )
    return MarketReference(
        market_id=row.market_id,
        identity=MarketIdentity(
            exchange=row.exchange,
            symbol=row.symbol,
            market_type=MarketType(row.market_type),
            base_asset=row.base_asset,
            quote_asset=row.quote_asset,
        ),
        filters=filters,
    )


async def load_market(session: AsyncSession, market_id: uuid.UUID) -> MarketReference | None:
    """One market by id, or ``None`` — never a placeholder identity."""
    row = (
        await session.execute(text(f"{_SELECT} WHERE m.id = :id"), {"id": market_id})
    ).one_or_none()
    return None if row is None else _reference(row)


async def load_markets(
    session: AsyncSession, market_ids: set[uuid.UUID]
) -> dict[uuid.UUID, MarketReference]:
    """Every market of a cycle in one round trip, keyed by id."""
    if not market_ids:
        return {}
    rows = await session.execute(
        text(f"{_SELECT} WHERE m.id = ANY(:ids)"),
        {"ids": list(market_ids)},
    )
    return {row.market_id: _reference(row) for row in rows}
