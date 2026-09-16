"""meme events scan cursor: an event may now name many coins, not one (T4.26b)

Revision ID: 0043_meme_events_scan_cursor
Revises: 0042_meme_executable_mcap

KB-0100 (16/09/2026, 8 plantão events against 18 335 pump.fun creations):
the per-minute job (0041) only scanned events with ``observed_at`` inside
the last 65 minutes against coins created in the 60 minutes *after* — a
plantão event is always registered after the fact (median latency 172,8 min
that day), so it never fell inside that window. ARC alone had 60 candidate
coins by the job's own rule and matched zero; 874 proposals, 0 with
``event_id``.

This revision replaces the singleton match with a ledger,
``meme_event_matches`` (``event_id``, ``mint``, ``match_kind``) — every coin
an event names, not just the earliest, inserted once and never overwritten
(``ddl/meme_event_matches.py``). The 72-hour lookback and the 30-minute
backward grace are the worker's own knobs
(``hunter_meme_worker.events_config``), not schema. ``last_scanned_created_at``
on ``meme_events`` is the per-event cursor that keeps the per-tick scan of
``meme_tokens`` bounded to what is new since the last tick.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_event_matches import (
    add_scan_cursor_column,
    create_meme_event_matches_table,
    drop_meme_event_matches_table,
    drop_scan_cursor_column,
    grant_meme_event_matches_privileges,
    refuse_a_downgrade_that_would_lose_a_match,
)

revision: str = "0043_meme_events_scan_cursor"
down_revision: str | None = "0042_meme_executable_mcap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_scan_cursor_column()
    create_meme_event_matches_table()
    grant_meme_event_matches_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_a_match()
    drop_meme_event_matches_table()
    drop_scan_cursor_column()
