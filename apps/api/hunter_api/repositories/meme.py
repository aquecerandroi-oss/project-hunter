"""Reads for the Meme Radar (T4.3) — global, no-RLS tables, same category as
``repositories/markets.py`` (ARCHITECTURE.md §9: "Repositorios globais
(``MarketRepository``) so leitura para tenants").

Schema and the ``meme_radar_features_v1`` view are the frozen contract from
``.claude/state/notes-T4.2.md`` §"contrato" (T4.2, migration
``0021_meme_radar``) — table metadata lives in ``repositories/meme_tables.py``;
row shapes and mapping helpers live in ``repositories/meme_rows.py`` (split
out to keep this file under the line budget); the keyset cursor for
``list_tokens`` lives in ``repositories/meme_cursor.py``.

**The radar list is "the latest closed minute", per the contract's own
guidance** (§6: "o 'último minuto' é parâmetro da API, não mágica da
visão"): :meth:`MemeRepository.list_tokens` first reads
``max(meme_features_1m.end_time)`` and then filters the view to exactly that
``end_time`` — a mint the collector has not polled *in that specific minute*
(rate-limited, deprioritized) simply does not appear in that page, which is
the intended behavior, not a bug to paper over with a stale row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, and_, func, literal, or_, select

from hunter_api.repositories.meme_cursor import SORT_COLUMNS
from hunter_api.repositories.meme_rows import (
    MemeFeatureRow,
    MemeGapRow,
    MemeGraduationMatrixRow,
    MemeSnapshotRow,
    MemeTokenRow,
    matrix_row_from,
    row_from_token_only,
    row_from_view,
)
from hunter_api.repositories.meme_tables import (
    meme_curve_snapshots,
    meme_features_1m,
    meme_graduation_matrix_v1,
    meme_ingest_gaps,
    meme_radar_features_v1,
    meme_tokens,
)
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

__all__ = [
    "MemeFeatureRow",
    "MemeGapRow",
    "MemeGraduationMatrixRow",
    "MemeRepository",
    "MemeSnapshotRow",
    "MemeTokenRow",
]


def _state_predicate(state: str, view: Any) -> ColumnElement[bool]:
    if state == "migrated":
        return view.c.migrated_at.is_not(None)
    if state == "completed":
        return and_(view.c.migrated_at.is_(None), view.c.completed_at.is_not(None))
    return and_(view.c.migrated_at.is_(None), view.c.completed_at.is_(None))


def _optional(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


class MemeRepository:
    """No ``org_id`` constructor argument: meme reference data carries no
    ``organization_id`` (same reasoning as ``MarketRepository``), even though
    every route in ``routers/meme.py`` sits under ``/orgs/{org_id}`` per
    brief T4.3 (a product/RBAC visibility choice, not a tenancy scope on the
    query itself)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def token_coverage_count(self) -> int:
        """How many mints this radar has ever recorded — the denominator that
        tells ``services/meme.py`` whether ``meme_tokens`` has *any* coverage
        yet, before it trusts an aggregate computed from it."""
        return int(await self.session.scalar(select(func.count()).select_from(meme_tokens)) or 0)

    async def created_counts_by_window(self, now: datetime) -> tuple[int, int]:
        """``created_at`` is nullable (contract: a migration can arrive
        before the creation event) -- the ``>=`` comparison already excludes
        ``NULL`` rows on its own, so a token with unknown creation time is
        silently not counted in either window, never miscounted as "just
        created"."""
        since_24h = now - timedelta(hours=24)
        since_7d = now - timedelta(days=7)
        result = (
            await self.session.execute(
                select(
                    func.count().filter(meme_tokens.c.created_at >= since_24h),
                    func.count().filter(meme_tokens.c.created_at >= since_7d),
                )
            )
        ).one()
        return int(result[0] or 0), int(result[1] or 0)

    async def mayhem_active_count(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(meme_tokens)
                .where(meme_tokens.c.mayhem_state == "active")
            )
            or 0
        )

    async def graduations_last_24h(self, now: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(meme_tokens)
                .where(meme_tokens.c.migrated_at >= now - timedelta(hours=24))
            )
            or 0
        )

    async def latest_end_time(self) -> datetime | None:
        value = await self.session.scalar(select(func.max(meme_features_1m.c.end_time)))
        return _optional(value)

    async def graduation_matrix_for(self, now: datetime) -> MemeGraduationMatrixRow | None:
        """The matrix row of the Brasília day that contains ``now`` (``0024``),
        or ``None`` when no mint carried a completion signal that day. The day
        is computed by the database (its own tz data), never by subtracting
        three hours here."""
        matrix = meme_graduation_matrix_v1
        day = func.date(func.timezone("America/Sao_Paulo", literal(now, DateTime(timezone=True))))
        row = (
            (await self.session.execute(select(matrix).where(matrix.c.day_brt == day)))
            .mappings()
            .first()
        )
        return None if row is None else matrix_row_from(row)

    async def list_tokens(
        self,
        *,
        state: str | None,
        sort: str,
        limit: int,
        cursor: tuple[Decimal | datetime | None, str] | None,
    ) -> list[MemeTokenRow]:
        """The radar list: the view, filtered to the latest closed minute
        (module docstring), the derived ``state``, and keyset-paginated on
        the requested ``sort`` column."""
        last_minute = await self.latest_end_time()
        if last_minute is None:
            return []
        view = meme_radar_features_v1
        sort_col = view.c[SORT_COLUMNS[sort]]
        stmt = select(view).where(view.c.end_time == last_minute)
        if state:
            stmt = stmt.where(_state_predicate(state, view))
        if cursor is not None:
            value, mint = cursor
            if value is None:
                stmt = stmt.where(and_(sort_col.is_(None), view.c.mint > mint))
            else:
                stmt = stmt.where(
                    or_(
                        sort_col < value,
                        and_(sort_col == value, view.c.mint > mint),
                        sort_col.is_(None),
                    )
                )
        stmt = stmt.order_by(sort_col.desc().nulls_last(), view.c.mint.asc()).limit(limit)
        rows = (await self.session.execute(stmt)).mappings().all()
        return [row_from_view(r) for r in rows]

    async def get_token(self, mint: str) -> MemeTokenRow | None:
        """The mint's own latest feature row (not necessarily "the latest
        closed minute" globally — a detail page still shows a mint's most
        recent known progress even if the very last minute skipped it), or a
        bare identity read from ``meme_tokens`` when no feature row exists
        yet at all."""
        view = meme_radar_features_v1
        view_row = (
            (
                await self.session.execute(
                    select(view)
                    .where(view.c.mint == mint)
                    .order_by(view.c.end_time.desc())
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        if view_row is not None:
            return row_from_view(view_row)
        token_row = (
            (await self.session.execute(select(meme_tokens).where(meme_tokens.c.mint == mint)))
            .mappings()
            .first()
        )
        return None if token_row is None else row_from_token_only(token_row)

    async def list_snapshots(self, mint: str, *, limit: int) -> list[MemeSnapshotRow]:
        stmt = (
            select(meme_curve_snapshots)
            .where(meme_curve_snapshots.c.mint == mint)
            .order_by(meme_curve_snapshots.c.observed_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            MemeSnapshotRow(
                observed_at=ensure_utc(r.observed_at),
                source=r.source,
                virtual_sol_reserves=r.virtual_sol_reserves,
                virtual_token_reserves=r.virtual_token_reserves,
                real_sol_reserves=r.real_sol_reserves,
                real_token_reserves=r.real_token_reserves,
                complete=r.complete,
                mcap_sol=r.mcap_sol,
            )
            for r in rows
        ]

    async def list_features(self, mint: str, *, limit: int) -> list[MemeFeatureRow]:
        stmt = (
            select(meme_features_1m)
            .where(meme_features_1m.c.mint == mint)
            .order_by(meme_features_1m.c.end_time.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            MemeFeatureRow(
                end_time=ensure_utc(r.end_time),
                age_minutes=r.age_minutes,
                curve_progress_pct=r.curve_progress_pct,
                progress_reason=r.progress_reason,
                mcap_sol=r.mcap_sol,
                curve_reason=r.curve_reason,
                unique_buyers=r.unique_buyers,
                unique_buyers_reason=r.unique_buyers_reason,
                buy_sell_ratio=r.buy_sell_ratio,
                buy_sell_ratio_reason=r.buy_sell_ratio_reason,
                top10_share=r.top10_share,
                top10_share_reason=r.top10_share_reason,
                creator_sold=r.creator_sold,
                creator_sold_reason=r.creator_sold_reason,
                coverage=r.coverage,
                features_version=r.features_version,
            )
            for r in rows
        ]

    async def list_gaps(
        self, *, limit: int, cursor: tuple[datetime, uuid.UUID] | None
    ) -> list[MemeGapRow]:
        stmt = select(meme_ingest_gaps).order_by(
            meme_ingest_gaps.c.detected_at.desc(), meme_ingest_gaps.c.id.desc()
        )
        if cursor is not None:
            detected_at, gap_id = cursor
            stmt = stmt.where(
                (meme_ingest_gaps.c.detected_at < detected_at)
                | (
                    (meme_ingest_gaps.c.detected_at == detected_at)
                    & (meme_ingest_gaps.c.id < gap_id)
                )
            )
        rows = (await self.session.execute(stmt.limit(limit))).all()
        return [
            MemeGapRow(
                id=r.id,
                stream=r.stream,
                mint=r.mint,
                gap_start=ensure_utc(r.gap_start),
                gap_end=ensure_utc(r.gap_end),
                detected_at=ensure_utc(r.detected_at),
                reason=r.reason,
                generation=r.generation,
                detail=r.detail,
            )
            for r in rows
        ]
