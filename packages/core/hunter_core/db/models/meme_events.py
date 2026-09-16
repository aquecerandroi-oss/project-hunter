"""``meme_events`` — the "may pump" event, ahead of the mint that may not exist
yet (DATABASE.md §52, revision ``0041_meme_social``, T4.26).

The $TRUMP case (17/01/2025) decided nothing on chart or flow: a public
figure's own account announced a coin, and it went from zero to billions in
hours. This table is where "who announced, where, and how verifiable" lands
**before** the funnel ever sees a curve — an event can arrive with no
``mint`` at all, because the announcement usually precedes the launch.

Global, like ``meme_tokens`` (§1.1): an announcement belongs to the world, not
to an organization — no ``organization_id``, therefore no RLS.

``mint`` and ``confidence`` are the two axes an operator (or the per-minute
matching job, ``hunter_meme_worker.events``) fills in *after* the row is
born: a ``rumor`` heard on the plantão's lane 2 becomes ``confirmed`` only
when the announcer's own account is read directly, never guessed from reach
or engagement. Matching writes ``mint`` once (``ddl/meme_events.py``'s
guard); ``confidence``/``notes`` may still move, because a second look at the
same announcement is a correction, not a rewrite of history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY

EVENT_SOURCES = ("plantao", "baha", "indexer_boost", "dexscreener_profile", "manual")
EVENT_KINDS = (
    "public_figure_launch",
    "exchange_listing",
    "viral_post",
    "brand_launch",
    "narrative",
    "incident",
)
EVENT_CONFIDENCES = ("confirmed", "reported", "rumor")
"""``confirmed``: the announcer's own account, read directly. ``reported``: a
credible mirror (CoinDesk/The Block/Decrypt, a public Telegram) named it.
``rumor``: everything else worth a line in the plantão's lane 2."""


class MemeEvent(Base, UUIDPrimaryKeyMixin):
    """One "may pump" announcement — a public figure, a brand or an exchange
    naming a coin or a handle, with or without a mint yet."""

    __tablename__ = "meme_events"
    __table_args__ = (
        Index("ix_meme_events_observed_at", "observed_at"),
        Index(
            "ix_meme_events_unmatched",
            "observed_at",
            postgresql_where=text("mint IS NULL"),
        ),
        # The matching job's own scan (T4.26): unresolved events, oldest first,
        # bounded by the same window it reads meme_tokens.created_at through.
        Index("ix_meme_events_mint", "mint", postgresql_where=text("mint IS NOT NULL")),
        CheckConstraint(f"source IN {EVENT_SOURCES!r}", name="source_is_a_known_label"),
        CheckConstraint(f"kind IN {EVENT_KINDS!r}", name="kind_is_a_known_label"),
        CheckConstraint(f"confidence IN {EVENT_CONFIDENCES!r}", name="confidence_is_a_known_label"),
        CheckConstraint("char_length(title) > 0", name="title_is_not_empty"),
        CheckConstraint(
            "mint IS NULL OR char_length(mint) > 0", name="a_matched_mint_is_not_empty"
        ),
        CheckConstraint(
            "handle_hint IS NULL OR char_length(handle_hint) > 0",
            name="a_handle_hint_is_not_empty",
        ),
        CheckConstraint(
            "symbol_hint IS NULL OR char_length(symbol_hint) > 0",
            name="a_symbol_hint_is_not_empty",
        ),
        CheckConstraint("char_length(recorded_by) > 0", name="recorded_by_is_not_empty"),
        CheckConstraint("(mint IS NULL) = (matched_at IS NULL)", name="a_match_says_when"),
    )

    observed_at: Mapped[datetime]
    """When the announcement happened (or was first read) — never ``now()``
    for a backfilled row; the script and the worker both pass it explicitly."""

    source: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    mint: Mapped[str | None] = mapped_column(ForeignKey("meme_tokens.mint"))
    """``NULL`` until the matching job (or a human) names the mint — an event
    can, and usually does, arrive before the coin exists."""

    symbol_hint: Mapped[str | None] = mapped_column(Text)
    handle_hint: Mapped[str | None] = mapped_column(Text)
    """The announcer's own ``@handle``, without the ``@`` — what the matching
    job compares against ``meme_tokens.twitter``."""

    confidence: Mapped[str] = mapped_column(Text)
    notes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    recorded_by: Mapped[str] = mapped_column(Text)
    """``hunter_worker`` (the matching job wrote nothing here — it only fills
    ``mint``) or the operator's name/handle, from ``infra/scripts/meme_event.py``."""

    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    matched_at: Mapped[datetime | None]
    """When the per-minute job (or a human) set ``mint`` — biconditional with it.
    Legacy (0041): the job no longer writes this pair (T4.26b, ``meme_event_matches``
    is now the complete ledger); kept for any row a human already matched by hand."""

    last_scanned_created_at: Mapped[datetime | None]
    """T4.26b (``0043``): the per-event cursor — the matching job reads only
    ``meme_tokens`` created after this instant, then advances it to ``now()``
    whether or not the tick found a match, so a re-run never rescans the same
    coins. ``NULL`` means "never scanned"; the job then starts at
    ``observed_at`` minus its own backward grace."""


__all__ = ["EVENT_CONFIDENCES", "EVENT_KINDS", "EVENT_SOURCES", "MemeEvent"]
