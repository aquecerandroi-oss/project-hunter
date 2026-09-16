"""``0046_meme_rule_set_history`` — the gate's per-mint refusal, sampled
(T4.35).

R27 measured that ``meme_lab_ticks.refusals`` (T4.15, ``0031``) is an
aggregate by name **per tick**, never per mint: "why did Kintsugi not become a
proposal at 16:20" cost an hour of SQL forensics, replaying the gate photo by
photo against the params in force at that instant. This table is the answer
recorded going forward, at write time, for the mints the question is ever
asked about — never every refusal (that would be every 15-second row of every
tracked mint, the volume ``meme_features_15s`` already carries and 7 days
already bounds, §43.2): only

- every mint the gate's own criteria let through (a proposal — ``refusal``
  ``NULL``, so a proposal explains itself the same way a refusal does), and
- every mint that failed **exactly one** named criterion (a near-miss:
  ``passed_criteria >= total - 1``) — the close calls, small by construction
  (most refused rows fail several criteria at once; R27's Kintsugi failed
  only ``snipers_above_max``).

The 15-second fast lane caps what it writes per tick (declared in the
heartbeat, ``lab_refusal_trail_rows``/``lab_refusal_trail_capped``) — a
bounded write against a table this table's own selection already keeps small.
``value``/``limit`` are the number that was judged and the threshold it was
judged against, when the criterion names one (``snipers_above_max`` →
``snipers``/``max_snipers``); a refusal this revision does not yet decode a
number for still gets its row, with both ``NULL``.

Global (no ``organization_id``), no RLS (§1.1). ``hunter_worker``:
``SELECT``/``INSERT``/``DELETE`` (the fast lane writes; the fast lane's own
7-day retention prunes, row-wise like ``meme_tokens`` — no monthly partition
for a table this small, see ``docs/DATABASE.md``). ``hunter_app``:
``SELECT`` — the answer to "why not coin X" is a query away.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "meme_gate_refusals_by_mint"

_CREATE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    as_of timestamptz NOT NULL,
    rule_set_id uuid NOT NULL REFERENCES meme_rule_sets (id),
    mint text NOT NULL,
    refusal text,
    value numeric,
    "limit" numeric,
    CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
    CONSTRAINT uq_{TABLE} UNIQUE (rule_set_id, mint, as_of),
    CONSTRAINT ck_{TABLE}_mint_not_blank CHECK (mint <> ''),
    CONSTRAINT ck_{TABLE}_refusal_not_blank CHECK (refusal IS NULL OR refusal <> '')
)
"""
_INDEX = f"CREATE INDEX ix_{TABLE}_mint_as_of ON {TABLE} (mint, as_of)"

MEME_GATE_REFUSALS_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
MEME_GATE_REFUSALS_WORKER_TABLES: tuple[str, ...] = (TABLE,)


def create_meme_gate_refusals_by_mint() -> None:
    op.execute(_CREATE)
    op.execute(_INDEX)


def grant_meme_gate_refusals_by_mint_privileges() -> None:
    for table in MEME_GATE_REFUSALS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_GATE_REFUSALS_WORKER_TABLES:
        op.execute(f"GRANT SELECT, INSERT, DELETE ON {table} TO {WORKER_ROLE}")


def drop_meme_gate_refusals_by_mint() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")


def refuse_a_downgrade_that_would_lose_the_refusal_trail() -> None:
    """§17.7: reversing is allowed, losing the near-miss trail is not."""
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - the table name is this module's own frozen constant
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {TABLE} rows exist - "
        f"the per-mint near-miss/proposal trail the fast lane samples (R27); "
        f"nothing else can rebuild them', "
        f"HINT = 'COPY (SELECT * FROM {TABLE}) TO ... before reversing'; "
        f"END IF; END $$;"
    )
