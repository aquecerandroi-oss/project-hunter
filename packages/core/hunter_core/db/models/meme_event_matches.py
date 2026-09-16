"""``meme_event_matches`` — every coin an event named, buy or avoid (T4.26b,
revision ``0043_meme_events_scan_cursor``).

KB-0100 (16/09/2026): ``meme_events.mint``/``matched_at`` (0041) can only ever
name **one** coin per event, and the job that wrote them only looked forward
60 minutes from an event usually registered hours after the fact — the
plantão's own median latency that day was 172,8 min. ARC alone had 60
candidate coins by the job's own rule and matched zero. This table is the
complete, append-only ledger: one row per ``(event_id, mint)`` pair, inserted
once and never overwritten (``ON CONFLICT DO NOTHING`` in
``hunter_meme_worker.events_repo``) — a re-run never flips ``match_kind``
after the fact, the same "history, not overwrite" rule ``meme_events`` itself
follows for ``mint``/``matched_at``.

``match_kind`` is the event's own ``notes->>'action'`` at the instant of the
match (``avoid`` when the event itself is a warning — a clone viveiro, KB-0100
event 8 — ``buy`` otherwise); the event gate (``hunter_indicators.meme.
event_gate``) reads it to refuse ``event_avoid`` regardless of kind/confidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base

MATCH_KINDS = ("buy", "avoid")


class MemeEventMatch(Base):
    """One coin an event named — global, like ``meme_events``/``meme_tokens``
    (§1.1): no ``organization_id``, no RLS."""

    __tablename__ = "meme_event_matches"
    __table_args__ = (
        Index("ix_meme_event_matches_mint", "mint"),
        CheckConstraint(f"match_kind IN {MATCH_KINDS!r}", name="match_kind_is_a_known_label"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_events.id"), primary_key=True)
    mint: Mapped[str] = mapped_column(ForeignKey("meme_tokens.mint"), primary_key=True)
    match_kind: Mapped[str] = mapped_column(Text)
    matched_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


__all__ = ["MATCH_KINDS", "MemeEventMatch"]
