"""Shadow Lab state — ``0002_shadow_lab``, docs/plans/SHADOW-LAB.md §4/§6.

Two system tables (no ``organization_id``: shadow research is global, exactly
like ``agent_signals`` and ``signal_outcomes``, DATABASE.md §1.1):

- :class:`ShadowEpisode` — the durable tracking slot. One row per
  ``(strategy_version_id, market_id, cohort)``, holding the current episode, the
  last evaluated bar close, whether the slot is armed for a new entry and which
  outcome is open. It is also where the market-worker's ``tracking_hold`` comes
  from: a market may leave the monitored universe, but not while a shadow
  tracking still needs its candles.
- :class:`ShadowOutbox` — the transactional outbox the strategy-worker writes in
  the *same* transaction as the signal, the outcome and the episode, so a
  published event and a persisted decision can never disagree. T2.9 absorbs it
  later, preserving pending rows and their identities.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, SQL_TRUE
from hunter_core.domain.enums import SHADOW_COHORT_PATTERN

_OPEN_TRACKING = text("open_outcome_signal_id IS NOT NULL")
"""The partial-index predicate for a slot that is currently tracking."""


class ShadowEpisode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One tracking slot of one strategy version on one market, per cohort."""

    __tablename__ = "shadow_episodes"
    __table_args__ = (
        UniqueConstraint(
            "strategy_version_id",
            "market_id",
            "cohort",
            name="uq_shadow_episodes_slot",
        ),
        # the open outcome must belong to *this* slot: same version, same market
        ForeignKeyConstraint(
            ["open_outcome_signal_id", "strategy_version_id", "market_id"],
            ["agent_signals.id", "agent_signals.strategy_version_id", "agent_signals.market_id"],
            ondelete="SET NULL (open_outcome_signal_id)",
        ),
        Index(
            "uq_shadow_episodes_open_outcome",
            "open_outcome_signal_id",
            unique=True,
            postgresql_where=_OPEN_TRACKING,
        ),
        Index("ix_shadow_episodes_hold", "market_id", postgresql_where=_OPEN_TRACKING),
        CheckConstraint(f"cohort ~ '{SHADOW_COHORT_PATTERN}'", name="cohort_format"),
    )

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE")
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"))
    cohort: Mapped[str] = mapped_column(Text)
    """``prospective`` or ``replay:<run_id>``.

    Not an ``ENUM`` because a replay carries its run id; the CHECK above and
    ``hunter_core.domain.enums.ShadowCohort`` share one pattern. Separate
    cohorts mean a replay never occupies the prospective slot, and the data used
    to build a version is never its reserved forward evaluation.
    """

    episode_id: Mapped[uuid.UUID]
    """Identity of the *current* episode; a rearm starts a new one."""

    last_bar_close: Mapped[datetime]
    """The strategy-timeframe bar close this slot has been evaluated through.

    Evaluation only ever happens on distinct closed bars, so this is what makes
    a redelivery or a restart a no-op instead of a second decision.
    """

    armed: Mapped[bool] = mapped_column(server_default=SQL_TRUE)
    """Whether a new entry may be taken.

    Cleared while a tracking runs; set again only after an eligible bar where
    the condition was false *after* the previous tracking ended (SHADOW-LAB.md
    §4). Missing data never rearms — which is why this is durable state and not
    something the worker recomputes from memory after a restart.
    """

    open_outcome_signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signal_outcomes.signal_id", ondelete="SET NULL")
    )
    """The signal whose outcome is ``pending_entry`` or ``active`` here.

    ``NULL`` when the slot is idle. Three constraints, and each closes a
    different way of pointing at the wrong thing:

    - this FK targets ``signal_outcomes``, not ``agent_signals``, so the outcome
      row has to exist — a slot cannot hold a decision nobody is tracking;
    - the composite FK above ties the signal to *this* slot's strategy version
      and market. With a single-column FK, an episode of ETH could hold a BTC
      signal: the FK was satisfied, ``tracking_hold`` then held ETH's candles
      while BTC — the market the outcome actually needs — went uncollected;
    - the partial unique index makes one outcome reachable from at most one
      episode, and the partial index on ``market_id`` is the ``tracking_hold``
      lookup.

    What DDL still cannot state is that the outcome is *open*
    (``pending_entry``/``active``) and that its cohort is this slot's cohort —
    the cohort lives in the decision envelope, not in a column. Both stay S2's
    single-transaction invariant plus its reconciliation query.
    """


class ShadowOutbox(Base):
    """Events the strategy-worker owes the stream, written inside its transaction.

    ``BIGSERIAL`` rather than the UUID v7 of DATABASE.md §1 on purpose: it gives
    the dispatcher a stable, cheap order to drain the queue in. It is **not** a
    watermark — a sequence has gaps (rollbacks) and its order is not commit
    order, so "everything below id N is published" is false: transaction A can
    take 10, B take 11 and commit first, and a cursor at 11 would step over A.
    The pending predicate is ``dispatched_at IS NULL``, which is exactly what
    the partial index serves. Nothing here is a tenant's data, and nothing here
    is money.
    """

    __tablename__ = "shadow_outbox"
    __table_args__ = (
        Index(
            "ix_shadow_outbox_pending",
            "id",
            postgresql_where=text("dispatched_at IS NULL"),
        ),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        CheckConstraint("char_length(stream) > 0", name="stream_not_empty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    """The event's identity, deterministic upstream (``event_id = signal_id`` for
    ``shadow.signals.emitted``). Unique, so a retried transaction queues the
    event once and a redelivery is a no-op rather than a second publication."""

    stream: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    dispatched_at: Mapped[datetime | None]
    """``NULL`` until the event is on the stream — the reconciliation predicate."""

    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
