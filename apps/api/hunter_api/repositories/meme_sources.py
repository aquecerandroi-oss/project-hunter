"""Reads for ``GET /meme/sources`` (T4.2c): the newest row each source left in
its table, as ``hunter_app`` — global, no-RLS tables, ``SELECT`` only.

One ``max()`` per table, each on the leading column of the table's primary
key (``observed_at`` / ``block_time`` / the ``last_seen_at`` index), so a read
of "when did this source last write" costs one index descent per partition,
not a scan. ``None`` means the table has no rows, which the service renders
as ``no_rows`` — the database's own witness beside the worker's heartbeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SOURCE_TABLES", "LatestRow", "MemeSourcesRepository"]

SOURCE_TABLES: dict[str, tuple[str, str]] = {
    "pumpportal_ws": ("meme_tokens", "last_seen_at"),
    "pumpfun_rest": ("meme_curve_snapshots", "observed_at"),
    "solana_rpc": ("meme_curve_snapshots", "observed_at"),
    "trenches_ws": ("meme_board_observations", "observed_at"),
    "swap_api": ("meme_trades", "block_time"),
    "indexer_risk": ("meme_risk_snapshots", "observed_at"),
    "swap_api_activity": ("meme_market_activity_1m", "end_time"),
}
"""Source -> (table, instant column). The two curve readers share a table and
are told apart by ``source`` in the query below."""

_SOURCE_FILTER: dict[str, str] = {
    "pumpfun_rest": "WHERE source = 'pumpfun_rest'",
    "solana_rpc": "WHERE source = 'solana_rpc'",
    "swap_api": "WHERE source = 'swap_api'",
    "pumpportal_ws": "WHERE first_seen_source = 'pumpportal_ws'",
}


@dataclass(frozen=True, slots=True)
class LatestRow:
    table: str
    observed_at: datetime | None


class MemeSourcesRepository:
    """No ``org_id``: the radar's tables carry no ``organization_id`` (§1.1)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_rows(self) -> dict[str, LatestRow]:
        out: dict[str, LatestRow] = {}
        for source, (table, column) in SOURCE_TABLES.items():
            predicate = _SOURCE_FILTER.get(source, "")
            value = await self.session.scalar(
                text(f"SELECT max({column}) FROM {table} {predicate}")  # noqa: S608 — constants above
            )
            out[source] = LatestRow(
                table=table, observed_at=None if value is None else ensure_utc(value)
            )
        return out
