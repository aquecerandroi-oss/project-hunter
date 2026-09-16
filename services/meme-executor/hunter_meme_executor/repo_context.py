"""The coin's context for the admission — the four reads behind :class:`MemeContext`.

Split out of ``repo.py`` for the 350-line budget when T4.28h added the dev share.
Every value here is either measured **and dated inside its window** or ``None``:
the engine turns ``None`` into a named refusal, never into a zero (§8).

| value | table | window |
|---|---|---|
| age, creator, denominator, migration | ``meme_tokens`` | — (facts of the launch) |
| 1 m volume, ``creator_sold``, ``top10_share`` | newest ``meme_features_1m`` row | the caller's (``admission.context_from``) |
| ``bundled_share`` | ``meme_risk_snapshots`` | :data:`RISK_SNAPSHOT_MAX_AGE_S` |
| ``dev_share`` | the freshest of both | :data:`DEV_SHARE_MAX_AGE_S` |
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from sqlalchemy import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    Reading = RowMapping | Mapping[str, Any] | None
    """One row of a read, or nothing: the repo hands a ``RowMapping``, a test a dict."""

__all__ = ["DEV_SHARE_MAX_AGE_S", "RISK_SNAPSHOT_MAX_AGE_S", "TokenContext", "token_context"]


@dataclass(frozen=True, slots=True)
class TokenContext:
    created_at: datetime | None
    creator: str | None
    initial_real_token_reserves: int | None
    completed_at: datetime | None
    migrated_at: datetime | None
    curve_volume_1m_sol: Decimal | None
    features_end_time: datetime | None
    creator_sold: bool | None
    top10_share: Decimal | None
    bundled_share: Decimal | None
    dev_share: Decimal | None = None
    """T4.28h — the freshest **measured** dev share of either table, or ``None``."""
    dev_share_source: str | None = None
    dev_share_observed_at: datetime | None = None
    """The instant that share was read; the admission drops a share without one."""


RISK_SNAPSHOT_MAX_AGE_S = 600
"""Two of the reader's ``risk_min_interval_s`` (300 s, one read per mint per five
minutes): a value older than the reader could have refreshed twice is not an input."""
DEV_SHARE_MAX_AGE_S = RISK_SNAPSHOT_MAX_AGE_S
"""T4.28h — the dev share comes from the same readers as ``bundled_share`` and ages
the same way, so it is deliberately the *same* number, not a second dial."""

_TOKEN = text(
    "SELECT created_at, creator, initial_real_token_reserves, completed_at, migrated_at "
    "FROM meme_tokens WHERE mint = :mint"
)
_FEATURES = text(
    "SELECT end_time, curve_volume_1m_sol, creator_sold, top10_share, dev_share, "
    "  holders_observed_at, holders_source "
    "FROM meme_features_1m WHERE mint = :mint ORDER BY end_time DESC LIMIT 1"
)
"""``holders_observed_at``/``holders_source`` are the instant and the origin of the
holders reading, **which is also the dev share's** (``0023``: one reading fills
``holders``, ``top10_share`` and ``dev_share``). ``end_time`` is the minute's close,
not the reading's instant, so it never dates the share."""
_RISK = text(
    "SELECT bundled_share, observed_at FROM meme_risk_snapshots "
    "WHERE mint = :mint AND bundled_share IS NOT NULL AND observed_at >= :since "
    "ORDER BY observed_at DESC LIMIT 1"
)
"""``bundled_share`` lives on ``meme_risk_snapshots`` (the ``/in-memory-coin`` read,
``0023``), never on ``meme_features_1m`` — the T4.14 query named the wrong table and
the first live candidate would have raised ``UndefinedColumn`` (T4.28 finding). The
newest measured value inside :data:`RISK_SNAPSHOT_MAX_AGE_S`; older or absent is
``None`` and the engine refuses ``bundled_share_unmeasurable`` (§8: stale is absent)."""
_DEV_SHARE = text(
    "SELECT dev_share, observed_at FROM meme_risk_snapshots "
    "WHERE mint = :mint AND dev_share IS NOT NULL AND observed_at >= :since "
    "ORDER BY observed_at DESC LIMIT 1"
)
"""Its own query, not a column of :data:`_RISK`: a snapshot may measure the dev
share and not the bundle, and asking for both at once would lose one of them."""


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def freshest_dev_share(
    features: Reading, risk: Reading, since: datetime
) -> tuple[Decimal | None, str | None, datetime | None]:
    """The newest **dated** dev share of the two tables inside the window, with its
    origin. A share whose reading instant is missing is skipped: ``0023`` stamps
    ``holders_observed_at`` only when ``holders`` itself was read, and dating the
    share by the minute's close would call a five-minute-old reading thirty
    seconds old — which is exactly the mistake that lets a stale number vouch for
    an unknown creator (T4.28h)."""
    dated: list[tuple[datetime, Decimal | None, str]] = []
    if risk is not None:
        dated.append((risk["observed_at"], _decimal(risk["dev_share"]), "meme_risk_snapshots"))
    if features is not None and features["dev_share"] is not None:
        stamp = features["holders_observed_at"]
        if stamp is not None and stamp >= since:
            source = features["holders_source"] or "unknown"
            dated.append((stamp, _decimal(features["dev_share"]), f"meme_features_1m:{source}"))
    newest = max(dated, key=lambda row: row[0], default=None)
    return (None, None, None) if newest is None else (newest[1], newest[2], newest[0])


async def token_context(
    session: AsyncSession, mint: str, *, now: datetime | None = None
) -> TokenContext:
    token = (await session.execute(_TOKEN, {"mint": mint})).mappings().first()
    features = (await session.execute(_FEATURES, {"mint": mint})).mappings().first()
    since = (now or utcnow()) - timedelta(seconds=RISK_SNAPSHOT_MAX_AGE_S)
    risk = (await session.execute(_RISK, {"mint": mint, "since": since})).mappings().first()
    dev = (await session.execute(_DEV_SHARE, {"mint": mint, "since": since})).mappings().first()
    dev_share, dev_source, dev_at = freshest_dev_share(features, dev, since)
    initial = None if token is None else token["initial_real_token_reserves"]
    return TokenContext(
        created_at=None if token is None else token["created_at"],
        creator=None if token is None else token["creator"],
        initial_real_token_reserves=None if initial is None else int(Decimal(str(initial))),
        completed_at=None if token is None else token["completed_at"],
        migrated_at=None if token is None else token["migrated_at"],
        curve_volume_1m_sol=None if features is None else _decimal(features["curve_volume_1m_sol"]),
        features_end_time=None if features is None else features["end_time"],
        creator_sold=None if features is None else features["creator_sold"],
        top10_share=None if features is None else _decimal(features["top10_share"]),
        bundled_share=None if risk is None else _decimal(risk["bundled_share"]),
        dev_share=dev_share,
        dev_share_source=dev_source,
        dev_share_observed_at=dev_at,
    )
