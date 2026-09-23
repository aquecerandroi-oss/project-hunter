"""``meme_decision_tapes`` (``0062``, T4.89): the insert and the retention
sweep — SQL only; the buffer that calls them is
:mod:`hunter_meme_worker.decision_tape_writer`.

One ``INSERT … SELECT FROM jsonb_to_recordset`` per batch: one round trip and
one parameter whatever the batch size, and ``RETURNING`` counts the rows that
really landed (a replay of the same ``(mint, as_of)`` is ``ON CONFLICT DO
NOTHING`` — the first capture of an instant is the one kept).

Retention (``docs/DATABASE.md`` §64): a tape that explains only a
refusal-trail row lives as long as that row (7 d, ``config_trail``); a tape
tied to a proposal lives :data:`PROPOSAL_TAPE_RETENTION_DAYS` — the derived
fields of a proposal are durable anyway in ``meme_proposals.reasons``, the raw
slice is the complement. Deleted row by row in batches, like the trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from hunter_meme_worker.config_trail import TRAIL_RETENTION_DAYS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.decision_tape_writer import TapeRow

__all__ = [
    "PROPOSAL_TAPE_RETENTION_DAYS",
    "TABLE",
    "insert_decision_tapes",
    "prune_cutoffs",
    "prune_decision_tapes",
]

TABLE: Final = "meme_decision_tapes"
PROPOSAL_TAPE_RETENTION_DAYS: Final = 90

_INSERT = text(
    "INSERT INTO meme_decision_tapes "
    "  (mint, as_of, series, proposal_ids, trades, trades_in_window, derived) "
    "SELECT r.mint, r.as_of, r.series, r.proposal_ids, r.trades, r.trades_in_window, r.derived "
    "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r("
    "  mint text, as_of timestamptz, series text, proposal_ids uuid[], trades jsonb, "
    "  trades_in_window integer, derived jsonb) "
    "ON CONFLICT (mint, as_of) DO NOTHING RETURNING 1"
)
_PRUNE = text(
    "WITH doomed AS ("
    "  SELECT id FROM meme_decision_tapes "
    "  WHERE as_of < :trail_cutoff "
    "    AND (cardinality(proposal_ids) = 0 OR as_of < :proposal_cutoff) "
    "  LIMIT :batch"
    ") DELETE FROM meme_decision_tapes t USING doomed d WHERE t.id = d.id RETURNING t.id"
)


def _row(row: TapeRow) -> dict[str, object]:
    tape = row.tape
    return {
        "mint": tape.mint,
        "as_of": tape.as_of.isoformat(),
        "series": tape.series,
        "proposal_ids": list(row.proposal_ids),
        "trades": tape.trades_json(),
        "trades_in_window": tape.trades_in_window,
        "derived": tape.derived,
    }


async def insert_decision_tapes(session: AsyncSession, rows: Sequence[TapeRow]) -> int:
    """Rows actually inserted (a duplicate instant counts zero)."""
    if not rows:
        return 0
    payload = json.dumps([_row(row) for row in rows])
    return len((await session.execute(_INSERT, {"rows": payload})).all())


def prune_cutoffs(now: datetime) -> tuple[datetime, datetime]:
    """``(trail_cutoff, proposal_cutoff)`` — the proposal cutoff is the older
    one, so ``as_of < trail_cutoff`` bounds every doomed row (an ``as_of``
    index range, never a scan of the whole table)."""
    return (
        now - timedelta(days=TRAIL_RETENTION_DAYS),
        now - timedelta(days=PROPOSAL_TAPE_RETENTION_DAYS),
    )


async def prune_decision_tapes(session: AsyncSession, *, now: datetime, batch: int) -> int:
    """One batch of expired tapes; the caller loops while a batch is full."""
    trail_cutoff, proposal_cutoff = prune_cutoffs(now)
    result = await session.execute(
        _PRUNE,
        {"trail_cutoff": trail_cutoff, "proposal_cutoff": proposal_cutoff, "batch": batch},
    )
    return len(result.all())
