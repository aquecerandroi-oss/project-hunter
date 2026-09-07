"""What the wallet and the market say about a candidate — the eligibility reads.

Split from :mod:`hunter_execution_worker.bridge_repo` by responsibility, not by
size: that module answers "what has the Lab decided that this wallet has not
answered yet", and this one answers the four questions asked *about* one of those
decisions before it may become a proposal.

- **the SPOT pair** the perpetual maps to (D1: same venue, same ``base/quote``),
  with the 24h volume T3.0c measured on spot itself — including the **scaled**
  perpetuals (``1000SHIBUSDT`` quotes 1.000x the spot ``SHIBUSDT``) that Binance
  names by prefixing the base asset's own symbol, never by guessing a factor
  from the market symbol (review-T3.14.md item 4);
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

import re
import uuid
from dataclasses import dataclass, replace
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
    "spot_pair_of",
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
    scale: Decimal = Decimal(1)
    """How many spot units one perpetual unit's price is quoted at — ``1000`` for
    ``1000SHIBUSDT`` against spot ``SHIBUSDT``, ``1`` for every ordinary pair.
    ``Screened`` divides the frozen ``entry_ref``/``stop``/``target`` by this
    before they reach admission, so the numbers the engine sizes and checks for
    ``signal_validity`` are the spot market's own scale, never the perpetual's."""


@dataclass(frozen=True, slots=True)
class CoinCommitment:
    """Why the coin is already taken: a position, or a reservation still held."""

    kind: str
    market_id: uuid.UUID


_SCALED_ASSET = re.compile(r"^1(0{3,6})([A-Z][A-Z0-9]*)$")
"""Binance's own convention for a scaled perpetual: the base asset's symbol is
the literal decimal multiplier (``1000``, ``10000``, ``1000000``, ...) followed
by the unscaled asset's own symbol (``1000SHIB`` -> ``1000`` x ``SHIB``). The
factor is **read off this name**, never guessed from a price ratio: a market
whose symbol does not fit the pattern has no scale to recover, and is refused
exactly like a pair with no spot listing at all (item 4)."""


async def _spot_market(
    session: AsyncSession,
    *,
    exchange_id: uuid.UUID,
    base_asset_id: uuid.UUID,
    quote_asset_id: uuid.UUID,
) -> SpotPair | None:
    """The tradable SPOT market of one exact ``(exchange, base, quote)``, or ``None``."""
    row = (
        await session.execute(
            text(
                "SELECT id AS market_id, symbol, base_asset_id, is_monitored, volume_24h_usd "
                "FROM markets WHERE market_type = 'spot' AND exchange_id = :ex "
                "AND base_asset_id = :base AND quote_asset_id = :quote "
                "AND status = 'active' AND delisted_at IS NULL LIMIT 1"
            ),
            {"ex": exchange_id, "base": base_asset_id, "quote": quote_asset_id},
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


async def _scaled_spot_pair(session: AsyncSession, signal: ShadowSignal) -> SpotPair | None:
    """The unscaled spot twin of a perpetual named like ``1000SHIBUSDT``.

    Reads the perpetual's own base asset symbol, matches it against
    :data:`_SCALED_ASSET`, and looks the *remainder* up as its own asset. A
    remainder that names no asset, or a symbol that does not fit the pattern
    at all, means there is no mapping to recover — ``None``, the same refusal
    (``spot_pair_unavailable``) an unlisted pair already gets, per item 4:
    "se o mapeamento de escala não existir, recuse (não invente fator)".
    """
    if signal.base_asset_id is None or signal.quote_asset_id is None:
        return None
    symbol = await session.scalar(
        text("SELECT symbol FROM assets WHERE id = :id"), {"id": signal.base_asset_id}
    )
    if symbol is None:
        return None
    match = _SCALED_ASSET.match(symbol.upper())
    if match is None:
        return None
    scale = Decimal("1" + match.group(1))  # the zeros captured, with the leading "1" put back
    base_id = await session.scalar(
        text("SELECT id FROM assets WHERE symbol = :symbol"), {"symbol": match.group(2)}
    )
    if base_id is None:
        return None
    pair = await _spot_market(
        session,
        exchange_id=signal.exchange_id,
        base_asset_id=base_id,
        quote_asset_id=signal.quote_asset_id,
    )
    return None if pair is None else replace(pair, scale=scale)


async def spot_pair_for(session: AsyncSession, signal: ShadowSignal) -> SpotPair | None:
    """The tradable SPOT pair of the same venue and ``base/quote`` (D1).

    Tries the exact ``base_asset_id`` first — the ordinary case, ``scale=1`` —
    and only then the scaled mapping of :func:`_scaled_spot_pair`. ``None`` when
    neither exists: the asset then stays in shadow, which is exactly what the
    decision says happens.
    """
    if signal.base_asset_id is None or signal.quote_asset_id is None:
        return None
    exact = await _spot_market(
        session,
        exchange_id=signal.exchange_id,
        base_asset_id=signal.base_asset_id,
        quote_asset_id=signal.quote_asset_id,
    )
    return exact if exact is not None else await _scaled_spot_pair(session, signal)


async def spot_pair_of(session: AsyncSession, market_id: uuid.UUID) -> SpotPair | None:
    """One SPOT market's own commitment picture, read by its own id.

    Unlike :func:`spot_pair_for` — which maps a *perpetual* to the spot market
    it trades — a manual request already names the spot market directly (D1),
    so there is no perpetual to map from. Shared with it only through the
    :class:`SpotPair` shape, which is what
    :func:`hunter_execution_worker.bridge_inputs.liquidity_for` reads.
    """
    row = (
        await session.execute(
            text(
                "SELECT id AS market_id, symbol, base_asset_id, is_monitored, volume_24h_usd "
                "FROM markets WHERE id = :market AND market_type = 'spot'"
            ),
            {"market": market_id},
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
    residual — ``positions.is_residual`` (``0009_paper_geometry``, DATABASE.md
    §21.1) — does **not** count: it is owned and valued but is not a position
    (review-T3.5.md item 3, "não conta vaga, nem exposição, nem duplicidade"),
    the same rule ``entry.py``'s manual duplicate guard applies
    (``hunter_execution_worker.positions.load_open_position``). A held
    reservation still counts, because a pending entry reserves the slot (§4).
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
                "AND NOT p.is_residual AND m.base_asset_id = :base "
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
