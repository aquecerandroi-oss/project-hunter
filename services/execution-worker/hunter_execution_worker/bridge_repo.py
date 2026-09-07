"""The bridge's durable queue: which shadow decisions are still candidates.

One question, answered from Postgres on every pass and never from a cache — the
frozen signal, its envelope and its entry plan, minus the ones this wallet has
already filed a proposal for (``trade_proposals.signal_id``, which is what makes
a redelivery and a restart the same no-op).

What is asked *about* a candidate — the spot pair, the beta, the coin, the Radar
score — lives in :mod:`hunter_execution_worker.bridge_universe`. The split is by
responsibility: this module knows what the Lab decided, that one knows what the
wallet and the market say about it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.enums import TradeDirection
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.strategies.envelope import AssumedCosts

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef

__all__ = ["ENTRY_WINDOW", "ShadowSignal", "decimal_or_none", "pending_signals"]

logger = get_logger(__name__)

ENTRY_WINDOW = timedelta(seconds=120)
"""SHADOW-LAB.md §3: an entry may only happen within 120 s of
``source_bar_close``. Past it the Lab itself records ``no_entry: late``, and a
proposal built from a level that old would be an entry at a price nobody
observed."""

_LOOKBACK = ENTRY_WINDOW * 2
"""How far back the candidate query reaches.

Wider than the window on purpose: a signal whose window *just* closed has to
reach the screening so the refusal is named and counted, instead of vanishing
from a ``WHERE`` clause.
"""


def decimal_or_none(raw: object) -> Decimal | None:
    """A ``NUMERIC`` or a JSON string as a ``Decimal``, or ``None`` — never a float.

    Shared with :mod:`hunter_execution_worker.bridge_universe`: both read money
    out of columns and JSON envelopes, and two copies of "how a price is parsed"
    is one copy too many.
    """
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value.is_finite() else None


@dataclass(frozen=True, slots=True)
class ShadowSignal:
    """One frozen shadow decision, as the bridge needs to read it."""

    signal_id: uuid.UUID
    strategy_version_id: uuid.UUID
    perp_market_id: uuid.UUID
    exchange_id: uuid.UUID
    base_asset_id: uuid.UUID | None
    quote_asset_id: uuid.UUID | None
    direction: TradeDirection
    entry_ref: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    assumed_costs: AssumedCosts | None
    source_bar_close: datetime | None
    emitted_at: datetime
    purpose: str
    version_active: bool

    def window_closes_at(self) -> datetime | None:
        return None if self.source_bar_close is None else self.source_bar_close + ENTRY_WINDOW


_SIGNAL_SELECT = (
    "SELECT s.id AS signal_id, s.strategy_version_id, s.market_id, s.direction::text AS direction, "
    "s.stop, s.targets, s.supporting_features, s.emitted_at, o.meta AS outcome_meta, "
    "v.status::text AS version_status, v.activated_at, m.exchange_id, m.base_asset_id, "
    "m.quote_asset_id FROM agent_signals s "
    "JOIN strategy_versions v ON v.id = s.strategy_version_id "
    "JOIN markets m ON m.id = s.market_id "
    "LEFT JOIN signal_outcomes o ON o.signal_id = s.id "
    "WHERE s.emitted_at >= :cut AND s.emitted_at <= :now AND NOT EXISTS ("
    "SELECT 1 FROM trade_proposals p WHERE p.signal_id = s.id "
    "AND p.organization_id = :org AND p.portfolio_id = :pf) AND EXISTS ("
    "SELECT 1 FROM agents a WHERE a.organization_id = :org AND a.portfolio_id = :pf "
    "AND a.strategy_version_id = s.strategy_version_id AND a.deleted_at IS NULL) "
    "ORDER BY s.emitted_at, s.id LIMIT :limit"
)
"""``agent_signals`` is global, so the scope of "candidate **for this wallet**"
has to be stated: a signal is one only when the wallet actually runs that
strategy version (an ``agents`` row of its own). Without that clause every
wallet would screen — and log a refusal for — every version's signals, at one
cycle per second.

The clause deliberately does **not** filter on ``status = 'enabled'``: a wallet
whose agent is paused is a wallet whose operator should see
``agent_unavailable`` counted, and a wallet that never had the agent is simply
not the audience."""


def _costs(raw: object) -> AssumedCosts | None:
    if not isinstance(raw, dict):
        return None
    try:
        return AssumedCosts.model_validate(raw)
    except Exception:
        return None


def _signal(row: Any) -> ShadowSignal:
    envelope: dict[str, Any] = dict(row.supporting_features or {})
    meta: dict[str, Any] = dict(row.outcome_meta or {})
    targets: list[Any] = list(row.targets or [])
    observed = envelope.get("observation_ts")
    return ShadowSignal(
        signal_id=row.signal_id,
        strategy_version_id=row.strategy_version_id,
        perp_market_id=row.market_id,
        exchange_id=row.exchange_id,
        base_asset_id=row.base_asset_id,
        quote_asset_id=row.quote_asset_id,
        direction=TradeDirection(row.direction),
        entry_ref=decimal_or_none(meta.get("reference_price")),
        stop=decimal_or_none(row.stop),
        target=decimal_or_none(targets[0]) if targets else None,
        assumed_costs=_costs(envelope.get("assumed_costs") or meta.get("assumed_costs")),
        source_bar_close=(
            ensure_utc(datetime.fromisoformat(str(observed).replace("Z", "+00:00")))
            if observed
            else None
        ),
        emitted_at=ensure_utc(row.emitted_at),
        purpose=str(envelope.get("purpose") or meta.get("purpose") or ""),
        version_active=row.version_status == "active" and row.activated_at is not None,
    )


async def pending_signals(
    session: AsyncSession, *, wallet: WalletRef, now: datetime, limit: int = 50
) -> tuple[ShadowSignal, ...]:
    """Shadow decisions this wallet has not filed a proposal for yet, oldest first.

    The durable queue **is** this query: nothing is held in memory between
    cycles, so a signal that lost one cycle is simply still here in the next
    one, and a restart changes nothing (T3.14 item 4).
    """
    rows = await session.execute(
        text(_SIGNAL_SELECT),
        {
            "cut": now - _LOOKBACK,
            "now": now,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "limit": limit,
        },
    )
    return tuple(_signal(row) for row in rows)
