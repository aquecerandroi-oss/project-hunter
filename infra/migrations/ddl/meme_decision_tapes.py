"""``0062_meme_decision_tapes`` — what the event lane saw at the instant it
decided (T4.89).

R73 (``.claude/state/notes-R73.md`` §2/§6, KB-0153): the desk decides on the
``meme_event_gate_v1`` lane over a WS tape held in memory that was never
persisted trade by trade, and ``meme_trades`` — the only recorded tape — is a
polling copy ~44 s late (p90 ≈ 129 s). R73 could recover decision-time
coverage for 1 of 91 real positions, and H-010 died of that data limit. One
row here per decision instant of that lane (``as_of`` = the evaluation
instant, the proposal's ``features_end_time`` and the refusal trail's
``as_of`` — not the proposal's later ``decided_at``): the newest ≤ 50 fills
of the judged minute, each with both clocks, and the derived block (windows,
largest buyer and holder since the subscription with their shares, the
creator's position, the coverage) that the lane also appends to the
proposal's ``reasons``.

Global (no ``organization_id``), no RLS (§1.1), like ``meme_trades``.
Append-only for ``hunter_worker`` (``SELECT``/``INSERT``/``DELETE``: the lane
writes, its own daily sweep prunes — **no** ``UPDATE``: a tape is never
rewritten). ``hunter_app``: ``SELECT``. Retention, row by row (no monthly
partition can express "7 d unless a proposal points at it"): 7 d for a tape
that only explains a refusal-trail row, 90 d when ``proposal_ids`` is not
empty (``docs/DATABASE.md`` §64). The ceiling CHECK (200 fills) keeps a
misconfigured slice from turning this into the next 17 GB table.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "meme_decision_tapes"
SLICE_CEILING = 200

_CREATE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    mint text NOT NULL,
    as_of timestamptz NOT NULL,
    series text NOT NULL,
    proposal_ids uuid[] NOT NULL DEFAULT '{{}}',
    trades jsonb NOT NULL,
    trades_in_window integer NOT NULL,
    derived jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
    CONSTRAINT uq_{TABLE}_mint_as_of UNIQUE (mint, as_of),
    CONSTRAINT ck_{TABLE}_mint_not_blank CHECK (mint <> ''),
    CONSTRAINT ck_{TABLE}_series_not_blank CHECK (series <> ''),
    CONSTRAINT ck_{TABLE}_trades_is_an_array CHECK (jsonb_typeof(trades) = 'array'),
    CONSTRAINT ck_{TABLE}_derived_is_an_object CHECK (jsonb_typeof(derived) = 'object'),
    CONSTRAINT ck_{TABLE}_slice_within_window
        CHECK (jsonb_typeof(trades) <> 'array'
               OR jsonb_array_length(trades) <= trades_in_window),
    CONSTRAINT ck_{TABLE}_slice_is_bounded
        CHECK (jsonb_typeof(trades) <> 'array'
               OR jsonb_array_length(trades) <= {SLICE_CEILING})
)
"""
_INDEX = f"CREATE INDEX ix_{TABLE}_as_of ON {TABLE} (as_of)"
_AUTOVACUUM = (
    f"ALTER TABLE {TABLE} SET (autovacuum_vacuum_scale_factor = 0.05, "
    f"toast.autovacuum_vacuum_scale_factor = 0.05)"
)
"""Row-wise daily deletes on a TOAST-heavy table: vacuum at 5 % dead rows,
not the default 20 %, so the freed space is reused before the next day's
inserts extend the files (database-architect review, T4.89)."""

MEME_DECISION_TAPES_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
MEME_DECISION_TAPES_WORKER_TABLES: tuple[str, ...] = (TABLE,)


def create_meme_decision_tapes() -> None:
    op.execute(_CREATE)
    op.execute(_INDEX)
    op.execute(_AUTOVACUUM)


def grant_meme_decision_tapes_privileges() -> None:
    for table in MEME_DECISION_TAPES_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_DECISION_TAPES_WORKER_TABLES:
        op.execute(f"GRANT SELECT, INSERT, DELETE ON {table} TO {WORKER_ROLE}")


def drop_meme_decision_tapes() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")


def refuse_a_downgrade_that_would_lose_the_decision_tapes() -> None:
    """§17.7: reversing is allowed, losing what the desk saw is not. The
    lock comes first (``0057``'s pattern, §63): counting and then dropping
    leaves a window for the worker to insert a tape between the two."""
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - the table name is this module's own frozen constant
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {TABLE} rows exist - "
        f"the WS tape the event lane decided on (T4.89); nothing else can rebuild it', "
        f"HINT = 'COPY (SELECT * FROM {TABLE}) TO ... before reversing'; "
        f"END IF; END $$;"
    )
