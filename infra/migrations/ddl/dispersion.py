"""``0020_market_dispersion`` — BTC × alts as a persisted series.

T3.90 / H-P18. The plantão runs of 10/09 and 11/09 measured the same shape twice:
the **median 24 h return of the sixteen markets** at -4,80 % and -3,85 % while the
**BTC** was at -1,50 % and -1,30 %. The hypothesis is that this *discordância*,
read before a decision, separates expectancy — and the only door a state like that
may enter a decision through is the eligibility policy (``0017``, T3.52/T3.59).

A gate needs a value at the exact instant a bar closed, and the two possible
shapes are the ones ``0019`` already argued between:

- computing it inside the gate would put a fold over the universe × two 24 h-apart
  candles on the decision path, per version, per bar — and, decisively, the
  **replay** would recompute it from *today's* candle table while the live decision
  read *that* minute's. Two populations that cannot be compared;
- persisting one row per minute makes "the live bar and the replay read the same
  number" a property of the schema rather than a promise in a docstring.

So: a table, on the doctrine of ``market_regimes`` (``0001``/T3.43),
``market_betas`` (``0006``/T3.7b) and ``market_breadth`` (``0019``/T3.77).

**Why not a column on ``market_breadth``.** Asked first, and answered by reading
that table's constraints rather than its name. ``market_breadth`` has no generic
``series``/``value`` pair: ``value`` is constrained to ``[0, 1]``, ``falling <=
covered`` ties two counts this series does not have, and ``window_minutes`` sits
in its unique key. A dispersion is signed by construction (negative **is** the
hypothesis), is four numbers rather than one, and needs no window column because
its horizon belongs to its version string. Reusing the table meant dropping two
CHECKs that protect every row already in it — constraints would stop describing
the rows they were written for. A sibling table with the same conventions keeps
both series as strict as each can afford.

**Global, RLS-free** (DATABASE.md §1.1): the universe belongs to the exchange, not
to an organization. No ``organization_id``, therefore no policy.

**No partition, with the count written down.** One row per minute per exchange per
version is ``60 × 24 × 365 = 525 600`` rows/year, against the 1 M/year threshold
the brief sets: one venue is at 53 %, two venues cross it. Declared, not hidden —
and :data:`UNIQUE_READING` is already keyed so a ``RANGE (end_time)`` partitioning
would not change a single query, though (as in ``0019``) the change would
**rebuild** the table, because the PK is ``id`` alone and §15.2 requires the
partition column in the PK.

**One btree, not three.** The unique key's index is the only index this table
carries and it serves every read: the gate probes ``(exchange_id,
dispersion_version, end_time)`` by equality on all three columns, and the foreign
key's ``RESTRICT`` check probes ``exchange_id``, which is that index's leading
column. ``index=True`` on the model's FK column is therefore absent — DATABASE.md
§1 asks that every FK be indexed, and a composite that *leads* with the FK column
is that index (``0019``'s own words, and the rule the tenant tables'
``organization_id``-leading composites state).

**Grants: ``SELECT`` for ``hunter_app``, ``SELECT``/``INSERT`` for
``hunter_worker``, and nothing else for either.** The scanner writes, the
strategy-worker and the API read, and nobody edits — the ``replay_runs`` /
``market_breadth`` shape, for the same reason: a reading its own writer may rewrite
is not evidence. Immutability is a *privilege*, not a trigger: there is no legal
``UPDATE`` on this table, so withholding ``UPDATE``/``DELETE`` from both roles is
the whole of it.

**Constraint names are the model's, not the server's.**
``pk_market_dispersion``, ``fk_market_dispersion_exchange_id_exchanges`` and
``uq_market_dispersion_reading`` are spelled out because this revision writes
literal SQL: without them Postgres would mint ``market_dispersion_pkey`` /
``market_dispersion_exchange_id_fkey`` while
``hunter_core.db.base.NAMING_CONVENTION`` says otherwise, ``alembic check`` would
not notice (it does not diff constraint names), and a future revision that
partitions this table — which must ``DROP CONSTRAINT`` by name to put ``end_time``
into the primary key (§15.2) — would be written against a name that is not there.

**No upgrade guard, and that is an assertion**: the revision creates a table that
did not exist, so there is no stored row it can make unrepresentable. **The
downgrade refuses** while any reading exists (§17.7): the series is not
recomputable after the fact — ``markets.is_monitored`` is overwritten in place, so
the universe a historical minute was measured against is gone the moment the rows
are.

Described in ``docs/PIPELINE.md`` §4b item 16. The ``docs/DATABASE.md`` §32 that
should describe it is **owed** and said so here rather than discovered later — the
same debt ``0019`` declared for §31, and for the same reason: this task writes the
revision, not that chapter (``.claude/state/notes-T3.90.md``).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "market_dispersion"

DISPERSION_VERSION_0020 = "dispersion_24h_v1"
"""A **copy** of the version string the first rows carry
(``hunter_indicators.dispersion.DISPERSION_V1``), never an import — the rule
``ddl/breadth.py`` and ``ddl/replay_runs.py`` both state: the database's contract
must not silently follow a later edit to a Python constant. Nothing in the DDL
compares against it; it is here so a reviewer reading this revision can see which
protocol the first rows carried."""

UNIQUE_READING = "uq_market_dispersion_reading"
"""The unique key **and** the only index: every read this table serves is an
equality probe on it or on its leading column."""

PRIMARY_KEY = "pk_market_dispersion"
FOREIGN_KEY = "fk_market_dispersion_exchange_id_exchanges"

DISPERSION_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT`` for ``hunter_app``: a dashboard may show what the alts were doing;
it never produces a reading."""

DISPERSION_WORKER_APPEND_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT``/``INSERT`` for ``hunter_worker`` — never ``UPDATE``, never
``DELETE``. The scanner's producer inserts, the strategy-worker's gate reads, and
a minute that was already folded is finished. A second fold that disagrees is a
new ``dispersion_version``, which is a different row by the unique key, not an
edit."""

_CREATE_TABLE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL,
    exchange_id uuid NOT NULL,
    end_time timestamptz NOT NULL,
    dispersion_version text NOT NULL,
    horizon_minutes smallint NOT NULL,
    universe_size integer NOT NULL,
    covered integer NOT NULL,
    alts_covered integer NOT NULL,
    alts_below_btc integer NOT NULL,
    btc_r24h numeric(9, 6),
    median_alt_r24h numeric(9, 6),
    dispersion numeric(9, 6),
    share_below_btc numeric(9, 6),
    coverage numeric(9, 6) NOT NULL,
    usable boolean NOT NULL,
    reason text,
    computed_at timestamptz NOT NULL DEFAULT now(),
    inputs jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    CONSTRAINT {PRIMARY_KEY} PRIMARY KEY (id),
    CONSTRAINT {FOREIGN_KEY} FOREIGN KEY (exchange_id)
        REFERENCES exchanges (id) ON DELETE RESTRICT,
    CONSTRAINT {UNIQUE_READING}
        UNIQUE (exchange_id, dispersion_version, end_time),
    CONSTRAINT ck_{TABLE}_reason_states_unusability
        CHECK (usable = (reason IS NULL)),
    CONSTRAINT ck_{TABLE}_a_usable_reading_has_every_value
        CHECK (NOT usable OR (dispersion IS NOT NULL AND btc_r24h IS NOT NULL
               AND median_alt_r24h IS NOT NULL AND share_below_btc IS NOT NULL)),
    CONSTRAINT ck_{TABLE}_dispersion_is_the_difference
        CHECK (dispersion IS NULL OR dispersion = median_alt_r24h - btc_r24h),
    CONSTRAINT ck_{TABLE}_counts_not_negative
        CHECK (covered >= 0 AND alts_covered >= 0 AND alts_below_btc >= 0
               AND universe_size >= 0),
    CONSTRAINT ck_{TABLE}_covered_within_universe CHECK (covered <= universe_size),
    CONSTRAINT ck_{TABLE}_alts_within_covered CHECK (alts_covered <= covered),
    CONSTRAINT ck_{TABLE}_below_within_alts CHECK (alts_below_btc <= alts_covered),
    CONSTRAINT ck_{TABLE}_horizon_is_positive CHECK (horizon_minutes > 0),
    CONSTRAINT ck_{TABLE}_share_is_a_fraction
        CHECK (share_below_btc IS NULL OR (share_below_btc >= 0 AND share_below_btc <= 1)),
    CONSTRAINT ck_{TABLE}_coverage_is_a_fraction
        CHECK (coverage >= 0 AND coverage <= 1),
    CONSTRAINT ck_{TABLE}_version_not_empty
        CHECK (char_length(dispersion_version) > 0)
)
"""
"""Written out rather than assembled from the model: this revision installs
*this* shape, and a later edit to ``hunter_core.db.models.dispersion`` must not
change what ``0020`` put in the database (the rule every module in this package
states). ``test_db_integration.py``/``alembic check`` is what keeps the two in
step."""

_DOWNGRADE_GUARD_MESSAGE = (
    "market_dispersion readings exist - dropping the table destroys the only record of how "
    "far the alts were from the BTC at each minute, and it is not recomputable after the "
    "fact with the universe that was monitored then (markets.is_monitored is overwritten "
    "in place)"
)
_DOWNGRADE_GUARD_HINT = (
    "export market_dispersion before reversing, and understand what it costs: every cohort "
    "cut by dispersion becomes uncuttable, and a version gated on dispersion would decide "
    "with no series to gate it"
)


def create_dispersion_table() -> None:
    """The table and its unique reading key — which is also its only index."""
    op.execute(_CREATE_TABLE)


def drop_dispersion_table() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")


def grant_dispersion_privileges() -> None:
    """Read for the API, append for the worker, and nothing else for either."""
    for table in DISPERSION_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in DISPERSION_WORKER_APPEND_TABLES:
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
