"""The receipt of one replay slice — ``0013_replay_runs``, DATABASE.md §25.

One row per **slice** of a historical replay: what was replayed, over which
window and markets, under which assumption, how much it cost and what the cohort
held when the slice ended. Global (no ``organization_id``, no RLS), exactly like
``agent_signals``, ``signal_outcomes`` and ``shadow_episodes`` — replay is
research, not a tenant's money (§1.1).

**Nothing here decides anything.** A replay never writes ``shadow_outbox``, its
cohort is refused by name at the execution bridge (``cohort_not_live``) and its
versions are ``research_only``. A ``replay_runs`` row is a receipt, and the
reason it is a table instead of only a ``system_events`` line is retention: that
channel is pruned at 30 days (§1.3) while the replication protocol counts 15 and
30 days of results *after* a marker.

**A slice, not a run** — the decision recorded in §25.1. The proof run of T3.19b
replayed 31 days in eleven commands under one cohort, so the unit that actually
happens is the slice. Summing slices reconstructs a run; splitting a run back
into slices is impossible, and the alternative (one row per run, accumulated by
``UPDATE``) would have required giving the writer ``UPDATE`` on its own receipt.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY
from hunter_core.domain.digests import MARKETS_DIGEST_PATTERN
from hunter_core.domain.enums import REPLAY_COHORT_PATTERN

SECONDS = Numeric(12, 3)
"""``NUMERIC(12,3)`` — wall-clock seconds of one slice.

Not ``double precision``: this number becomes a *rate* in a report
(``bars_evaluated / seconds``), and the only reason the project would ever store
a float is that nobody looked. Three decimals is the resolution
``time.perf_counter()`` deserves over a run of minutes; twelve digits is eleven
years of them.
"""


class ReplayRunRow(Base, UUIDPrimaryKeyMixin):
    """One slice of one replay run, as the ledger wrote it.

    Named ``...Row`` rather than ``ReplayRun`` for the reason §15.9 gives for
    ``MarketRegimeRow``: ``hunter_strategy_worker.replay.ledger.ReplayRun`` is
    the in-memory shape of the same receipt, and two different things with one
    name in one import list is how a test ends up asserting about the wrong one.
    """

    __tablename__ = "replay_runs"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "window_from",
            "window_to",
            "markets_digest",
            name="uq_replay_runs_slice",
        ),
        Index("ix_replay_runs_version_window", "strategy_version_id", "window_from"),
        CheckConstraint(f"cohort ~ '{REPLAY_COHORT_PATTERN}'", name="cohort_is_a_replay_cohort"),
        CheckConstraint("cohort = 'replay:' || run_id::text", name="cohort_names_the_run"),
        CheckConstraint("window_to > window_from", name="window_is_half_open"),
        CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        CheckConstraint(
            "bars_evaluated >= 0 AND signals >= 0 AND outcomes_resolved >= 0 "
            "AND outcomes_open >= 0 AND errors >= 0 AND seconds >= 0 "
            "AND decision_lag_s >= 0",
            name="counts_are_not_negative",
        ),
        CheckConstraint("outcomes_resolved <= signals", name="resolved_within_the_population"),
        CheckConstraint("workers >= 1", name="a_slice_had_at_least_one_worker"),
        CheckConstraint("cardinality(markets) > 0", name="a_slice_visited_a_market"),
        CheckConstraint(
            "array_position(markets, NULL::text) IS NULL", name="markets_has_no_unnamed_member"
        ),
        CheckConstraint(
            f"markets_digest ~ '{MARKETS_DIGEST_PATTERN}'", name="markets_digest_is_a_sha256"
        ),
        CheckConstraint(
            "jsonb_typeof(evaluations_by_state) = 'object'", name="evaluations_is_an_object"
        ),
    )

    run_id: Mapped[uuid.UUID]
    """The run every slice of it shares — the ``<uuid>`` of ``replay:<uuid>``.

    Not the primary key: ``id`` is a fresh UUID v7 per slice (§1), and the run is
    what ``uq_replay_runs_slice`` groups. Indexed as the leading column of that
    UNIQUE, which is also what makes re-writing a slice idempotent — the same
    property ``uuid5`` signal identity gives on the other side.
    """

    cohort: Mapped[str] = mapped_column(Text)
    """``replay:<run_id>`` — the same string ``agent_signals.supporting_features``
    and ``shadow_episodes.cohort`` carry, so "the episodes of this run" is a join
    and not string surgery.

    Two CHECKs, and they say different things: one is the grammar (the replay
    branch of ``SHADOW_COHORT_PATTERN``, since a run is never ``prospective`` and
    never a replication arm), the other is that the label and ``run_id`` cannot
    disagree. The redundancy is deliberate and, unlike prose, unable to drift.
    """

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE")
    )
    """The version whose frozen code and parameters produced every decision.

    ``CASCADE`` like ``shadow_episodes``: a version that can be deleted at all is
    a never-activated draft (the freeze trigger refuses the rest), and a receipt
    for an experiment whose instrument no longer exists explains nothing.
    """

    window_from: Mapped[datetime]
    window_to: Mapped[datetime]
    """``[window_from, window_to)`` — half-open, so two adjacent slices never
    visit the same bar and the throughput number is not double-counted."""

    markets: Mapped[list[str]] = mapped_column(ARRAY(Text))
    """``<exchange>:<symbol>`` of every market this slice dispatched.

    The exchange is inside the key because the same ``BTCUSDT`` on two exchanges
    is a different market (REPLICATION.md §3.3). Not a UUID array and not a join
    table: this is a receipt, read by a human and by a report, and a market later
    delisted must not make the receipt unreadable.
    """

    markets_digest: Mapped[str] = mapped_column(Text)
    """SHA-256 (hex) of the sorted ``markets`` — the fourth column of the slice
    key since ``0018_replay_runs_slice_markets`` (§30).

    Until ``0018`` the key was the window alone, so four market slices of one
    window under one cohort wrote **one** receipt and discarded three under
    ``ON CONFLICT DO NOTHING``: T3.62 measured 8 rows for 32 runs. A slice is a
    window *and* a market set, and this column is what makes the key say so.

    Derived, never chosen. ``hunter_core.domain.digests.markets_digest`` is the
    writer's half and ``replay_runs_digest_names_the_markets`` is the database's:
    the trigger fills the column in when it arrives ``NULL`` and **refuses** a
    value that is not the digest of this row's own ``markets`` — a copy that can
    disagree with its source is worse than no copy (§18.2). The digest is over
    the *sorted* list so the order the markets were dispatched in cannot
    fabricate a second slice of work that already has a receipt.
    """

    started_at: Mapped[datetime]
    finished_at: Mapped[datetime]

    bars_evaluated: Mapped[int] = mapped_column(Integer)
    """Bars this **slice** evaluated — the number that sums across slices."""

    signals: Mapped[int] = mapped_column(Integer)
    outcomes_resolved: Mapped[int] = mapped_column(Integer)
    """``terminal + no_entry + censored`` of the **cohort**, not of this slice.

    Counted from the rows rather than remembered by a process (a number a worker
    holds in memory is not evidence about what was written), and the query has no
    window filter — so these two are a *running total for the whole run as of
    this slice*, while ``bars_evaluated``, ``seconds`` and ``errors`` are the
    slice's own. Summing them across slices multiplies the population; a run's
    figure is the value on its last slice. Declared here and in §25.2 rather than
    discovered by whoever writes the first ``SUM``.
    """

    outcomes_open: Mapped[int] = mapped_column(Integer)
    """Trackings whose horizon had not closed by the wall clock. Not a failure —
    the honest count of what the run could not resolve yet."""

    seconds: Mapped[Decimal] = mapped_column(SECONDS)
    decision_lag_s: Mapped[int] = mapped_column(Integer)
    """The assumed distance between a bar close and its decision
    (``REPLAY_DECISION_LAG_S``). It is the only source of a replayed
    ``no_entry: late``, so two runs with different lags are two populations and
    the receipt has to say which one this was."""

    workers: Mapped[int] = mapped_column(SmallInteger)
    evaluations_by_state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """``{triggered, not_triggered, unavailable, ineligible, rejected}``.

    JSONB and not five columns because the set of evaluation states belongs to
    the engine and a new one must not need a migration to be counted; nothing
    filters on it (§1).
    """

    errors: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    """No ``updated_at``: the row is never updated. Both application roles are
    denied ``UPDATE`` and ``DELETE`` outright (§25.4)."""
