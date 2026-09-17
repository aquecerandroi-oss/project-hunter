"""The one statement that writes a ``/in-memory-coin`` reading into
``meme_risk_snapshots`` — shared, so two processes cannot persist the same
reading two different ways.

It lived in ``hunter_meme_worker.repo_boards`` until T4.45 gave the **executor**
a reason to write one too: when a proposal is being admitted and the radar's read
has not landed yet, the executor reads the endpoint itself rather than refusing a
coin for a datum that is one HTTP call away (``docs/RISK_ENGINE_MEME.md`` §3.5).
Two services, one row shape: a second INSERT with its own column list is how a
column silently stops being written on one of the two paths.

The reading is typed **structurally** on purpose. ``hunter_core`` may not import
``hunter_exchanges`` (``hunter_core.execution.adapter``'s rule — the distribution
dependency points the other way), and the honest way to say "anything shaped like
the adapter's ``NormalizedRiskSnapshot``" is a Protocol that lists the columns
this statement writes. When a column is added to the table, this Protocol is
where the compiler notices.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RISK_COLUMNS", "RiskSnapshotReading", "insert_risk_snapshot"]


class RiskSnapshotReading(Protocol):
    """One ``GET /in-memory-coin/{mint}`` reading, as the adapter normalizes it.

    ``source`` is part of the row, not of the statement: the radar writes
    ``indexer_rest:/in-memory-coin`` and the executor's own read writes
    ``indexer_rest:/in-memory-coin:executor_on_demand`` — same endpoint, same
    numbers, different reader, and a query that wants to know which is which can
    ask. No consumer filters on it (checked across the repo, T4.45), so a new
    value cannot silently hide a row from the admission.
    """

    observed_at: datetime
    mint: str
    received_at: datetime
    source: str
    program: str | None
    platform: str | None
    quote_mint: str | None
    quote_asset: str | None
    holders: int | None
    top10_share: Decimal | None
    dev_share: Decimal | None
    snipers: int | None
    sniper_share: Decimal | None
    bundled_share: Decimal | None
    progress_pct: Decimal | None
    graduated_at: datetime | None
    is_mayhem: bool | None
    mayhem_state: str | None
    raw: dict[str, Any]


RISK_COLUMNS: tuple[str, ...] = (
    "observed_at",
    "mint",
    "received_at",
    "source",
    "program",
    "platform",
    "quote_mint",
    "quote_asset",
    "holders",
    "top10_share",
    "dev_share",
    "snipers",
    "sniper_share",
    "bundled_share",
    "progress_pct",
    "graduated_at",
    "is_mayhem",
    "mayhem_state",
)

_INSERT_RISK = text(
    f"INSERT INTO meme_risk_snapshots ({', '.join(RISK_COLUMNS)}, raw) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in RISK_COLUMNS)}, CAST(:raw AS jsonb)) "
    "ON CONFLICT (observed_at, mint) DO NOTHING"
)
"""``DO NOTHING`` on ``(observed_at, mint)``: two readers landing on the same
instant for the same mint is a duplicate, not a correction — the first write
stands and neither reader loses its cycle to an IntegrityError."""


async def insert_risk_snapshot(session: AsyncSession, snapshot: RiskSnapshotReading) -> None:
    values: dict[str, Any] = {column: getattr(snapshot, column) for column in RISK_COLUMNS}
    values["raw"] = json.dumps(snapshot.raw, default=str)
    await session.execute(_INSERT_RISK, values)
