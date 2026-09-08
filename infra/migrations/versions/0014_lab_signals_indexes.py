"""agent_signals: the cohort stops being invisible to the planner

Fourteenth revision. Two indexes on ``agent_signals``, no column, no
constraint, no enum, no grant, no partition. It answers the request T3.37a
wrote instead of a migration (``.claude/state/notes-T3.37.md`` §T3.37a, "Pedido
para database-architect").

**The cohort is a JSONB expression, and an expression nobody indexed has no
statistics at all.** ``supporting_features->>'cohort'`` is what
``replay/simulate.count_population``, ``replay/stress.cohort_cases``,
``replication_stats._EVALUABLE_SQL`` and the Lab's ``/signals`` listing all
filter on. Measured on the VPS (2026-09-08, ``EXPLAIN`` only, 5 571 rows in
``agent_signals``): the planner estimates **28 rows** for ``= 'prospective'``
-- the 0.5 % default guess for an opaque expression -- when in truth almost
every row matches. The two consequences are separate and both real:

1. the scan is a ``Seq Scan`` that grows with the table, and
2. the 200x under-estimate is fed to every node above it, which is why the
   totals query picks a ``Nested Loop`` of 5 571 index probes into
   ``signal_outcomes`` while planning for 28.

An expression index fixes the second one for free: ``ANALYZE`` collects
statistics for index expressions, so after this revision the planner knows the
real selectivity of the cohort whether or not it chooses to scan the index.

**Why ``emitted_at`` is the sort key and not the envelope's ``decision_at``.**
They are the same instant -- ``persist.persist_decision`` writes
``emitted_at=record.decision_at`` and ``record.py`` stamps
``supporting_features['decision_at']`` from that same variable -- and
``replication_stats`` already orders the scoreboard by ``s.emitted_at, s.id``.
The column is indexable; the envelope's copy is **not**: ``text -> timestamptz``
runs ``timestamptz_in``, which is ``STABLE`` (it accepts ``'now'`` and depends
on ``TimeZone``), so Postgres refuses

    CREATE INDEX ... ON agent_signals (((supporting_features->>'decision_at')::timestamptz));
    ERROR:  functions in index expression must be marked IMMUTABLE

exactly as it refuses the same expression in a ``GENERATED`` column. The two
indexes T3.37a asked for cannot be written the way T3.37a wrote them, and no
migration can make ``/lab/shadow/signals`` use an index while its ``ORDER BY``
is that cast -- ``apps/api/.../lab_common.py`` has to name the column
(``DECISION_AT = AgentSignal.emitted_at``, one line, out of this revision's
scope). Proven both ways in
``apps/api/tests/integration/test_lab_signals_explain.py``; the trade is
written down in ``docs/DATABASE.md`` §26.

**Plain ``CREATE INDEX``, inside the migration's transaction, and the lock is
stated.** It takes a ``SHARE`` lock on ``agent_signals``, which blocks the
strategy-worker's ``INSERT``s for the length of the build and lets every reader
through; measured on **50 000 rows** in the testcontainer, the two builds cost
**131/162 ms** and **148/192 ms** in two runs — under half a second together,
and a few tens of milliseconds at the 5 571 rows the VPS holds today. ``0004`` had to go through
``CREATE INDEX CONCURRENTLY`` in an ``autocommit_block`` because
``outbox_events`` takes ~700 000 rows/day; ``agent_signals`` takes ~1 600, so
buying a non-atomic migration -- one that can leave an ``indisvalid = false``
index behind and needs its own recovery story -- would be paying that price for
nothing. If this table ever reaches the volume where the build is a visible
outage, the rebuild has ``0004`` as its recipe.

**No partial ``WHERE cohort = 'prospective'`` index**, deliberately: cohort is
the *leading* column of both indexes here, so the prospective slice is already
one contiguous range inside each of them and a partial copy would only be a
second thing to keep and to write to. And ``prospective`` is not privileged
data -- ``count_population`` and ``cohort_cases`` are asked about a
``replay:<run>`` cohort, which the same indexes serve.

**No index on ``signal_outcomes.tracking_state``** (T3.37a's third item),
because it is never the driving table: every one of these queries reaches an
outcome by its primary key from the signal, so a low-cardinality index on five
labels would be written on every outcome update and read by nobody. Measured,
not assumed -- the ``EXPLAIN`` test creates it, shows the plan does not move,
and drops it again.

**Nothing here depends on session state**: two ``CREATE INDEX`` statements. No
session prepared statement, no ``LISTEN``/``NOTIFY``, no session advisory lock.
``downgrade`` drops both; nothing is lost, since an index holds no fact the
table does not.

**Named ``0014_lab_signals_indexes`` (25 characters)** --
``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6).

Revision ID: 0014_lab_signals_indexes
Revises: 0013_replay_runs
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_lab_signals_indexes"
down_revision: str | None = "0013_replay_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COHORT_EXPRESSION_0014 = "(supporting_features ->> 'cohort')"
"""The cohort, exactly as every caller spells it.

Frozen per revision, the rule ``ddl/enums.py``/``ddl/outbox_index.py`` follow
(DATABASE.md §16.5): the index is only used by a query whose expression matches
this text, so a later revision that changed the envelope's key would have to say
so in its own SQL rather than retroactively re-render this one.
"""

LAB_SIGNAL_INDEXES_0014: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ix_agent_signals_cohort_emitted",
        (COHORT_EXPRESSION_0014, "emitted_at", "id"),
    ),
    (
        "ix_agent_signals_version_cohort_emitted",
        ("strategy_version_id", COHORT_EXPRESSION_0014, "emitted_at", "id"),
    ),
)
"""``(name, key)`` of the two indexes this revision installs.

Ascending, though every caller reads them ``DESC``: a btree is scanned
backwards at the same cost and an ascending declaration compares without noise
in ``alembic check`` (§15.3). ``id`` is in the key because it is the tiebreak
both the keyset cursor (``emitted_at DESC, id DESC``) and the scoreboard
(``ORDER BY s.emitted_at, s.id``, where replay produces ties by construction)
order by -- without it the last column of the sort is still a sort.
"""


def upgrade() -> None:
    for name, key in LAB_SIGNAL_INDEXES_0014:
        op.execute(f"CREATE INDEX {name} ON agent_signals USING btree ({', '.join(key)})")


def downgrade() -> None:
    for name, _key in reversed(LAB_SIGNAL_INDEXES_0014):
        op.execute(f"DROP INDEX {name}")
