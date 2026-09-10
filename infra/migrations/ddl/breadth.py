"""``0019_market_breadth`` — the amplitude of the universe as a persisted series.

T3.77 / H-P8. ``.claude/state/notes-D-P9.md`` §4 measured the minute the family's
worst hour died in: 2026-09-09 22:08Z, **194 of 200 monitored perpetuals falling
together** while the BTC moved -0,20 %. The hypothesis is that this fraction,
read *before* a decision, separates expectancy — and the only door a state like
that may enter a decision through is the eligibility policy (T3.52, T3.59).

A gate needs a value at the exact instant a bar closed. Two shapes were possible
and one of them is not honest:

- computing it inside the gate would put a fold over ~200 markets × 6 minutes on
  the decision path, per version, per bar — and, decisively, the **replay** would
  recompute it from *today's* candle table while the live decision read *that*
  minute's. Two populations that cannot be compared;
- persisting one row per minute makes "the live bar and the replay read the same
  number" a property of the schema rather than a promise in a docstring.

So: a table, on the same doctrine as ``market_regimes`` (``0001``/T3.43) and
``market_betas`` (``0006``/T3.7b).

**Global, RLS-free** (DATABASE.md §1.1): the universe belongs to the exchange,
not to an organization. No ``organization_id``, therefore no policy — the shape
``market_regimes``, ``market_betas``, ``fx_observations`` and ``replay_runs``
already have.

**No partition, with the count written down.** One row per minute per exchange is
``60 × 24 × 365 = 525 600`` rows/year. The threshold the brief sets is 1 M
rows/year; one venue is at 53 % of it and two venues (Binance + Bybit, the second still
``planned`` as of ``0016``) would be at 105 %. Declared, not hidden: the day the
second venue produces, this table is the next partitioning candidate, and
:data:`UNIQUE_READING`'s own index is already keyed so a ``RANGE (end_time)``
partitioning would not change a single query.

**One btree, not three.** The unique key's index is the only index this table
carries, and it serves every read: the gate probes
``(exchange_id, breadth_version, window_minutes, end_time)`` by equality on all
four columns, and the foreign key's ``RESTRICT`` check probes ``exchange_id``,
which is that index's leading column. A separate ``ix_market_breadth_lookup``
repeating the unique's columns and a separate ``ix_market_breadth_exchange_id``
on its prefix were written first and dropped before this revision ever left a
test container: three btrees maintained on a one-row-per-minute write path where
one answers everything (DATABASE.md §31). ``index=True`` on the model's FK column
went with them — DATABASE.md §1 asks that every FK be indexed, and a composite
that *leads* with the FK column is that index, the same rule the tenant tables'
``organization_id``-leading composites already state.

**Constraint names are the model's, not the server's.** ``pk_market_breadth``,
``fk_market_breadth_exchange_id_exchanges`` and ``uq_market_breadth_reading`` are
spelled out because this revision writes literal SQL: without them Postgres would
mint ``market_breadth_pkey``/``market_breadth_exchange_id_fkey`` while
``hunter_core.db.base.NAMING_CONVENTION`` says otherwise, ``alembic check`` would
not notice (it does not diff constraint names), and the revision that eventually
partitions this table — which must ``DROP CONSTRAINT`` by name to put ``end_time``
into the primary key (§15.2) — would be written against a name that is not there.

**Grants: ``SELECT`` for ``hunter_app``, ``SELECT``/``INSERT`` for
``hunter_worker``, and nothing else for either.** The scanner writes, the
strategy-worker and the API read, and nobody edits — the exact shape ``0013``
gave ``replay_runs`` and for the same reason: a reading its own writer may
rewrite is not evidence. Immutability is therefore a *privilege*, not a trigger:
``market_betas`` needed a trigger because it also needed one legal ``UPDATE``
(``superseded_at``); this table has none, so withholding ``UPDATE``/``DELETE``
from both roles is the whole of it.

Described in ``docs/PIPELINE.md`` §4b item 14. A ``docs/DATABASE.md`` chapter
(§31) is **owed** and is named as such in ``.claude/state/notes-T3.77.md``: this
task writes the revision, not that chapter.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "market_breadth"

BREADTH_VERSION_0019 = "breadth_v1"
"""A **copy** of :data:`hunter_indicators.breadth.BREADTH_VERSION`, never an
import — the same rule ``ddl/replay_runs.py`` states for the cohort pattern: the
database's contract must not silently follow a later edit to a Python constant.
Nothing in the DDL compares against it; it is here so that a reviewer reading
this revision can see which protocol the first rows carried."""

UNIQUE_READING = "uq_market_breadth_reading"
"""The unique key **and** the only index: every read this table serves is an
equality probe on it or on its leading column."""

PRIMARY_KEY = "pk_market_breadth"
FOREIGN_KEY = "fk_market_breadth_exchange_id_exchanges"
"""The names ``hunter_core.db.base.NAMING_CONVENTION`` gives the model, written
out here so the database and the model agree on what a future ``DROP CONSTRAINT``
has to say."""

BREADTH_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT`` for ``hunter_app``: a dashboard may show what the universe was
doing; it never produces a reading."""

BREADTH_WORKER_APPEND_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT``/``INSERT`` for ``hunter_worker`` — never ``UPDATE``, never
``DELETE``. The scanner's producer inserts, the strategy-worker's gate reads, and
a minute that was already folded is finished. A second fold that disagrees is a
new ``breadth_version``, which is a different row by the unique key, not an
edit."""

_CREATE_TABLE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL,
    exchange_id uuid NOT NULL,
    end_time timestamptz NOT NULL,
    window_minutes smallint NOT NULL,
    breadth_version text NOT NULL,
    universe_size integer NOT NULL,
    covered integer NOT NULL,
    falling integer NOT NULL,
    value numeric(9, 6),
    coverage numeric(9, 6) NOT NULL,
    usable boolean NOT NULL,
    reason text,
    computed_at timestamptz NOT NULL DEFAULT now(),
    inputs jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    CONSTRAINT {PRIMARY_KEY} PRIMARY KEY (id),
    CONSTRAINT {FOREIGN_KEY} FOREIGN KEY (exchange_id)
        REFERENCES exchanges (id) ON DELETE RESTRICT,
    CONSTRAINT {UNIQUE_READING}
        UNIQUE (exchange_id, breadth_version, window_minutes, end_time),
    CONSTRAINT ck_{TABLE}_reason_states_unusability
        CHECK (usable = (reason IS NULL)),
    CONSTRAINT ck_{TABLE}_a_usable_reading_has_a_value
        CHECK (NOT usable OR value IS NOT NULL),
    CONSTRAINT ck_{TABLE}_counts_not_negative
        CHECK (falling >= 0 AND covered >= 0 AND universe_size >= 0),
    CONSTRAINT ck_{TABLE}_falling_within_covered CHECK (falling <= covered),
    CONSTRAINT ck_{TABLE}_covered_within_universe CHECK (covered <= universe_size),
    CONSTRAINT ck_{TABLE}_window_is_positive CHECK (window_minutes > 0),
    CONSTRAINT ck_{TABLE}_value_is_a_fraction
        CHECK (value IS NULL OR (value >= 0 AND value <= 1)),
    CONSTRAINT ck_{TABLE}_coverage_is_a_fraction
        CHECK (coverage >= 0 AND coverage <= 1),
    CONSTRAINT ck_{TABLE}_breadth_version_not_empty
        CHECK (char_length(breadth_version) > 0)
)
"""
"""Written out rather than assembled from the model: this revision installs
*this* shape, and a later edit to ``hunter_core.db.models.breadth`` must not
change what ``0019`` put in the database (the rule every module in this package
states). ``test_db_integration.py`` is what keeps the two in step."""

_DOWNGRADE_GUARD_MESSAGE = (
    "market_breadth readings exist - dropping the table destroys the only record of what "
    "the universe was doing at each minute, and it is not recomputable after the fact with "
    "the universe that was monitored then (markets.is_monitored is overwritten in place)"
)
_DOWNGRADE_GUARD_HINT = (
    "export market_breadth before reversing, and understand what it costs: every cohort "
    "cut by breadth becomes uncuttable, and a version gated on breadth would decide with "
    "no series to gate it"
)


def create_breadth_table() -> None:
    """The table and its unique reading key — which is also its only index."""
    op.execute(_CREATE_TABLE)


def drop_breadth_table() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")


def grant_breadth_privileges() -> None:
    """Read for the API, append for the worker, and nothing else for either."""
    for table in BREADTH_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in BREADTH_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def refuse_a_downgrade_that_would_lose_a_reading() -> None:
    """§17.7: reversing is allowed, losing evidence is not."""
    safe_message = _DOWNGRADE_GUARD_MESSAGE.replace("'", "''")
    safe_hint = _DOWNGRADE_GUARD_HINT.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
        f"HINT = '{safe_hint}'; END IF; END $$;"
    )
