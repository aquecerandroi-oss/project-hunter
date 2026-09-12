"""Every write and read the collector makes — as ``hunter_worker``, never as owner.

Each function takes an ``AsyncSession`` already opened by
``hunter_core.db.session.role_session(..., db_role="hunter_worker")``, which is what
issues the ``SET LOCAL ROLE`` and the ``statement_timeout`` (§1.2a) **before** any
statement of ours. That is deliberate and it is the §27.5 finding not repeated: the
scanner has four ``engine.begin()`` transactions with no ``SET LOCAL ROLE`` that
only work because the login happens to be the owner, and under ``hunter_runtime``
they are *permission denied*. Nothing in this module opens its own transaction.

Three idempotence rules, each enforced by the schema rather than by a prior read:

- a token is **upserted with ``COALESCE(existing, new)``** on every identity and
  stamp column, so a later, poorer observation fills a hole and never blanks a
  value — which is also why the write-once trigger never fires on the happy path;
- a snapshot is ``ON CONFLICT (observed_at, mint, source) DO NOTHING``: re-reading
  the same instant from the same source writes one row, not two;
- a feature row is ``ON CONFLICT (end_time, mint, features_version) DO NOTHING``:
  a restart that re-folds a minute produces the same row, and a *different* fold
  of the same minute is a new ``features_version``, never an edit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_meme_worker.features import FeatureRow
from hunter_meme_worker.tracker import TrackedMint

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

RETENTION_MARKER = "app.meme_retention"
"""The declared marker ``meme_tokens_retention_is_declared`` demands. Transaction
scoped, therefore safe behind the pooler; it is isolation, not authorization
(§18.8), and what it buys is that pruning discovery history is an act."""


@dataclass(frozen=True, slots=True)
class TokenRow:
    """What one observation knows about a mint. Unknown stays ``None``."""

    mint: str
    first_seen_source: str
    first_seen_at: datetime
    last_seen_at: datetime
    name: str | None = None
    symbol: str | None = None
    uri: str | None = None
    creator: str | None = None
    created_at: datetime | None = None
    bonding_curve: str | None = None
    initial_virtual_sol_reserves: Decimal | None = None
    initial_virtual_token_reserves: Decimal | None = None
    initial_real_token_reserves: Decimal | None = None
    total_supply: Decimal | None = None
    pool: str | None = None
    mayhem_enabled: bool | None = None
    mayhem_mode: str | None = None
    mayhem_state: str | None = None
    completed_at: datetime | None = None
    migrated_at: datetime | None = None
    migrated_pool: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    """One curve observation. ``mcap_sol`` is absent on purpose: the database
    generates it, so no producer can write a market cap that disagrees with the
    reserves beside it."""

    observed_at: datetime
    mint: str
    source: str
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_sol_reserves: Decimal
    real_token_reserves: Decimal
    total_supply: Decimal
    complete: bool
    slot: int | None = None
    commitment: str | None = None
    mayhem_enabled: bool | None = None
    mayhem_state: str | None = None
    mayhem_mode: str | None = None


@dataclass(frozen=True, slots=True)
class GapRow:
    """A window the radar was not watching. ``mint`` is ``None`` for a whole-stream
    hole, because naming one mint would understate it."""

    stream: str
    gap_start: datetime
    gap_end: datetime
    reason: str
    mint: str | None = None
    generation: int | None = None
    detail: dict[str, Any] | None = None


_IDENTITY_COLUMNS = (
    "name",
    "symbol",
    "uri",
    "creator",
    "created_at",
    "bonding_curve",
    "initial_virtual_sol_reserves",
    "initial_virtual_token_reserves",
    "initial_real_token_reserves",
    "total_supply",
    "pool",
    "mayhem_enabled",
    "completed_at",
    "migrated_at",
    "migrated_pool",
)
"""Filled once; ``COALESCE(meme_tokens.<c>, excluded.<c>)`` keeps the first answer.
The same list the database freezes in ``ddl/meme_radar_guards.py`` — copied, never
imported, because ``infra/migrations`` is not importable from a service and because
the contract of the database must not follow a later edit of a Python constant."""

_ALL_TOKEN_COLUMNS = (
    "mint",
    "first_seen_source",
    "first_seen_at",
    "last_seen_at",
    *_IDENTITY_COLUMNS,
)

_UPSERT_TOKEN = text(
    f"INSERT INTO meme_tokens ({', '.join(_ALL_TOKEN_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _ALL_TOKEN_COLUMNS)}) "
    "ON CONFLICT (mint) DO UPDATE SET "
    + ", ".join(
        f"{column} = COALESCE(meme_tokens.{column}, excluded.{column})"
        for column in _IDENTITY_COLUMNS
    )
    # Mutable state: the newest observation wins, because that is what state means.
    + ", mayhem_mode = COALESCE(excluded.mayhem_mode, meme_tokens.mayhem_mode)"
    # And a token measured as *not* Mayhem carries no agent state: the CHECK
    # ``a_disabled_token_has_no_agent_state`` refuses that pair, and letting the
    # upsert build it would abort a whole collector cycle over a disagreement
    # between two sources. The conflict is reported by the caller, not written.
    + ", mayhem_state = CASE WHEN COALESCE(meme_tokens.mayhem_enabled, excluded.mayhem_enabled)"
    " IS FALSE THEN NULL ELSE COALESCE(excluded.mayhem_state, meme_tokens.mayhem_state) END"
    + ", last_seen_at = GREATEST(meme_tokens.last_seen_at, excluded.last_seen_at)"
    + ", updated_at = now()"
)

_SNAPSHOT_COLUMNS = (
    "observed_at",
    "mint",
    "source",
    "virtual_sol_reserves",
    "virtual_token_reserves",
    "real_sol_reserves",
    "real_token_reserves",
    "total_supply",
    "complete",
    "slot",
    "commitment",
    "mayhem_enabled",
    "mayhem_state",
    "mayhem_mode",
)

_INSERT_SNAPSHOT = text(
    f"INSERT INTO meme_curve_snapshots ({', '.join(_SNAPSHOT_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _SNAPSHOT_COLUMNS)}) "
    "ON CONFLICT (observed_at, mint, source) DO NOTHING"
)

_FEATURE_COLUMNS = (
    "end_time",
    "mint",
    "features_version",
    "curve_progress_pct",
    "progress_reason",
    "mcap_sol",
    "curve_reason",
    "unique_buyers",
    "unique_buyers_reason",
    "buy_sell_ratio",
    "buy_sell_ratio_reason",
    "top10_share",
    "top10_share_reason",
    "creator_sold",
    "creator_sold_reason",
    "age_minutes",
    "coverage",
    "snapshot_observed_at",
    "snapshot_source",
)

_INSERT_FEATURES = text(
    f"INSERT INTO meme_features_1m ({', '.join(_FEATURE_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _FEATURE_COLUMNS)}) "
    "ON CONFLICT (end_time, mint, features_version) DO NOTHING"
)

_INSERT_GAP = text(
    "INSERT INTO meme_ingest_gaps (id, stream, mint, gap_start, gap_end, reason, generation, detail) "
    "VALUES (:id, :stream, :mint, :gap_start, :gap_end, :reason, :generation, "
    "COALESCE(CAST(:detail AS jsonb), '{}'::jsonb))"
)

_LOAD_TRACKED = text(
    "SELECT mint, first_seen_at, created_at, bonding_curve, mayhem_state, "
    "       initial_real_token_reserves, completed_at, migrated_at "
    "FROM meme_tokens "
    "WHERE completed_at IS NULL AND migrated_at IS NULL "
    "  AND (COALESCE(created_at, first_seen_at) >= :cutoff "
    "       OR mayhem_state IN ('active', 'paused')) "
    "ORDER BY COALESCE(created_at, first_seen_at) DESC LIMIT :cap"
)
"""The tracked set is **rebuilt from the database on start**, which is the durable
checkpoint Astra's MUST-FIX 3 asks for: a restart resumes the same universe instead
of watching only what the WS happens to push next. A completed or migrated curve is
excluded — its reserves are static, so every request spent on it is a request not
spent on a curve that still moves."""

_PRUNE_TOKENS = text(
    "WITH doomed AS ("
    "  SELECT mint FROM meme_tokens "
    "  WHERE first_seen_at < :cutoff AND (created_at IS NULL OR created_at < :cutoff) "
    "  ORDER BY first_seen_at LIMIT :batch"
    ") DELETE FROM meme_tokens t USING doomed d WHERE t.mint = d.mint RETURNING t.mint"
)
"""Batched, in ``first_seen_at`` order (its own index), for the reason §1.3 gives
the outbox pruner: one ``DELETE`` of a day of discovery would hold a lock and write
a day of WAL in a single transaction while the collector is inserting."""


async def upsert_token(session: AsyncSession, row: TokenRow) -> None:
    """Insert or fill in one mint. Never blanks a value it already knew."""
    await session.execute(_UPSERT_TOKEN, asdict(row))


async def insert_snapshot(session: AsyncSession, row: SnapshotRow) -> None:
    await session.execute(_INSERT_SNAPSHOT, asdict(row))


async def insert_features(session: AsyncSession, rows: list[FeatureRow]) -> int:
    """One statement per minute's worth of rows; returns how many were offered."""
    if not rows:
        return 0
    await session.execute(_INSERT_FEATURES, [asdict(row) for row in rows])
    return len(rows)


async def record_gap(session: AsyncSession, gap: GapRow) -> None:
    import json

    payload = asdict(gap)
    detail = payload.pop("detail")
    payload["detail"] = None if detail is None else json.dumps(detail)
    payload["id"] = uuid7()
    await session.execute(_INSERT_GAP, payload)


async def load_tracked(session: AsyncSession, *, cutoff: datetime, cap: int) -> list[TrackedMint]:
    """Rebuild the tracked set from the durable rows (a restart is not a reset)."""
    result = await session.execute(_LOAD_TRACKED, {"cutoff": cutoff, "cap": cap})
    tracked: list[TrackedMint] = []
    for row in result.mappings():
        tracked.append(
            TrackedMint(
                mint=str(row["mint"]),
                first_seen_at=row["first_seen_at"],
                created_at=row["created_at"],
                bonding_curve=row["bonding_curve"],
                mayhem_state=row["mayhem_state"],
                initial_real_token_reserves=row["initial_real_token_reserves"],
                complete=row["completed_at"] is not None,
                migrated=row["migrated_at"] is not None,
            )
        )
    return tracked


async def prune_tokens(session: AsyncSession, *, cutoff: datetime, batch: int) -> int:
    """Delete one batch of aged-out mints, declaring retention first."""
    await session.execute(text(f"SET LOCAL {RETENTION_MARKER} = 'on'"))
    result = await session.execute(_PRUNE_TOKENS, {"cutoff": cutoff, "batch": batch})
    return len(result.scalars().all())
