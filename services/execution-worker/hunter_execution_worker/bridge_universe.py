"""What the wallet and the market say about a candidate — the eligibility reads.

Split from :mod:`hunter_execution_worker.bridge_repo` by responsibility, not by
size: that module answers "what has the Lab decided that this wallet has not
answered yet", and this one answers the four questions asked *about* one of those
decisions before it may become a proposal.

- **the SPOT pair** the perpetual maps to (D1: same venue, same ``base/quote``),
  with the 24h volume T3.0c measured on spot itself;
- **the beta revision in force**, under RISK_ENGINE.md §6's three conditions
  together;
- **whether the coin is already committed** — an open or ``closing`` position, or
  a reservation still ``held``, on any market with the same base asset;
- **what the Radar scored the perpetual** at the source bar (D3's first key).

Every one of them is point-in-time: a score is only read at or before
``source_bar_close`` and a beta only when its window closed before the cut.
Reading "the latest" would be the look-ahead the Lab spent a whole plan avoiding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_execution_worker.bridge_repo import ShadowSignal, decimal_or_none
from hunter_risk.inputs import BetaEstimate

if TYPE_CHECKING:
    from collections.abc import Collection

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "SPOT_VOLUME_FLOOR_USDT",
    "CoinCommitment",
    "SpotPair",
    "beta_map",
    "coin_commitment",
    "current_beta",
    "radar_score",
    "spot_pair_for",
]

logger = get_logger(__name__)

SPOT_VOLUME_FLOOR_USDT = Decimal("50000000")
"""D1: 50M USDT of 24h quote volume, **measured on spot**.

Everton's number, and deliberately a constant rather than an environment knob.
It is the same number as ``hunter_market_worker.spot_universe``'s
``SPOT_VOLUME_FLOOR_USDT``; the two are duplicated because the execution-worker
does not depend on the market-worker's package, and unifying them means moving
the constant into ``packages/core`` — filed in ``notes-T3.14.md``.
"""


@dataclass(frozen=True, slots=True)
class SpotPair:
    """The SPOT market a perpetual maps to, with what decides admissibility."""

    market_id: uuid.UUID
    symbol: str
    base_asset_id: uuid.UUID | None
    is_monitored: bool
    volume_24h_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class CoinCommitment:
    """Why the coin is already taken: a position, or a reservation still held."""

    kind: str
    market_id: uuid.UUID


async def spot_pair_for(session: AsyncSession, signal: ShadowSignal) -> SpotPair | None:
    """The tradable SPOT pair of the same venue and ``base/quote`` (D1).

    ``None`` when there is none — the asset then stays in shadow, which is
    exactly what the decision says happens.
    """
    if signal.base_asset_id is None or signal.quote_asset_id is None:
        return None
    row = (
        await session.execute(
            text(
                "SELECT id AS market_id, symbol, base_asset_id, is_monitored, volume_24h_usd "
                "FROM markets WHERE market_type = 'spot' AND exchange_id = :ex "
                "AND base_asset_id = :base AND quote_asset_id = :quote "
                "AND status = 'active' AND delisted_at IS NULL LIMIT 1"
            ),
            {
                "ex": signal.exchange_id,
                "base": signal.base_asset_id,
                "quote": signal.quote_asset_id,
            },
        )
    ).one_or_none()
    if row is None:
        return None
    return SpotPair(
        market_id=row.market_id,
        symbol=row.symbol,
        base_asset_id=row.base_asset_id,
        is_monitored=bool(row.is_monitored),
        volume_24h_usd=decimal_or_none(row.volume_24h_usd),
    )


_BETA_SELECT = (
    "SELECT market_id, beta, as_of, n FROM market_betas WHERE market_id = ANY(:ids) "
    "AND superseded_at IS NULL AND valid AND beta IS NOT NULL AND available_at <= :now "
    "AND window_end <= :now AND valid_until > :now ORDER BY market_id, as_of DESC"
)
"""RISK_ENGINE.md §6: available, window closed by the cut, deadline still open —
the three conditions together, never two of them."""


async def current_beta(
    session: AsyncSession, *, market_id: uuid.UUID, now: datetime
) -> BetaEstimate | None:
    """The beta revision in force for one market, or ``None``."""
    found = await beta_map(session, market_ids=(market_id,), now=now)
    return found.get(market_id)


async def beta_map(
    session: AsyncSession, *, market_ids: Collection[uuid.UUID], now: datetime
) -> dict[uuid.UUID, BetaEstimate]:
    """Every market's in-force beta in one round trip, newest revision per market."""
    ids = list(dict.fromkeys(market_ids))
    if not ids:
        return {}
    rows = await session.execute(text(_BETA_SELECT), {"ids": ids, "now": now})
    found: dict[uuid.UUID, BetaEstimate] = {}
    for row in rows:
        if row.market_id in found:
            continue  # ordered by as_of DESC: the first one is the newest
        value = decimal_or_none(row.beta)
        if value is None:
            continue
        found[row.market_id] = BetaEstimate(
            value=value, as_of=ensure_utc(row.as_of), validated=True, bars=int(row.n)
        )
    return found


async def coin_commitment(
    session: AsyncSession, *, wallet: WalletRef, base_asset_id: uuid.UUID | None
) -> CoinCommitment | None:
    """Whether this coin is already committed — position or held reservation.

    "Never two positions in the same coin" (D3) is about the **coin**, not the
    market row, so the join is on ``base_asset_id``: a second listing of the
    same asset would otherwise be a second position by a different name. A
    ``closing`` position counts — it still holds the dust and still counts in
    the wallet (notes-T3.5.md §2.3) — and so does a reservation that has not
    become an order yet, because a pending entry reserves the slot (§4).
    """
    if base_asset_id is None:
        return None
    row = (
        await session.execute(
            text(
                "SELECT kind, market_id FROM ("
                "SELECT 'position' AS kind, p.market_id AS market_id FROM positions p "
                "JOIN markets m ON m.id = p.market_id WHERE p.organization_id = :org "
                "AND p.portfolio_id = :pf AND p.status <> 'closed' AND p.qty > 0 "
                "AND m.base_asset_id = :base "
                "UNION ALL "
                "SELECT 'reservation' AS kind, t.market_id AS market_id FROM trade_proposals t "
                "JOIN markets m ON m.id = t.market_id WHERE t.organization_id = :org "
                "AND t.portfolio_id = :pf AND t.reservation_state = 'held' "
                "AND m.base_asset_id = :base) AS committed LIMIT 1"
            ),
            {"org": wallet.organization_id, "pf": wallet.portfolio_id, "base": base_asset_id},
        )
    ).one_or_none()
    return None if row is None else CoinCommitment(kind=row.kind, market_id=row.market_id)


async def radar_score(
    session: AsyncSession, *, market_id: uuid.UUID, at: datetime
) -> Decimal | None:
    """The Radar's score for the **perpetual**, as of the source bar (D3, key 1).

    Read from the durable trajectory first (``opportunity_history``, which is
    timestamped) and from the open episode only while its own
    ``last_updated_at`` is at or before the cut. ``radar:scores`` is deliberately
    not consulted: the ZSET holds *now*, and ranking a decision taken at 12:00
    by a score published at 12:03 is look-ahead with extra steps.

    ``None`` is a legitimate answer and never a refusal: D3 puts signals without
    a score **after** the ones with it, because the classifier is in warm-up.
    """
    row = (
        await session.execute(
            text(
                "SELECT score, ts FROM ("
                "SELECT h.score AS score, h.ts AS ts FROM opportunity_history h "
                "JOIN opportunities o ON o.id = h.opportunity_id "
                "WHERE o.market_id = :market AND h.ts <= :at "
                "UNION ALL "
                "SELECT o.score AS score, o.last_updated_at AS ts FROM opportunities o "
                "WHERE o.market_id = :market AND o.last_updated_at <= :at) AS samples "
                "ORDER BY ts DESC LIMIT 1"
            ),
            {"market": market_id, "at": at},
        )
    ).one_or_none()
    return None if row is None else decimal_or_none(row.score)
