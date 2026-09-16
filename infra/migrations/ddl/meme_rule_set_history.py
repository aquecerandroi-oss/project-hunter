"""``0046_meme_rule_set_history`` — one row per param the operator ever changed
on a live rule set (T4.35).

R27 (16/09/2026, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica.md``)
found ``operator/5`` edited four times in 100 minutes by
``infra/scripts/meme_rule_set.py --set-param``, and no row anywhere kept the
value it carried before each edit — the study had to *infer* the old sniper
cap from a tick's aggregated refusal counts, an hour of forensics for one
number. ``meme_rule_sets.params`` is a live cell (``UPDATE ... SET params =
params || ...``); this table is its diary.

**Written only by the CLI, in the same transaction as the ``UPDATE``.** No
``hunter_app``/``hunter_worker`` grant at all: unlike every other ``meme_*``
table (DATABASE.md §1.1's own shape), nothing here is read or written by a
running service — the operator's own act writes it and the operator's own
script reads it back (``--history``), both over ``DATABASE_URL_MIGRATIONS``
as the owner, exactly as ``meme_rule_sets`` itself is only ever mutated that
way. Global (no ``organization_id``), kept forever (an audit trail is not a
cache): the volume is a handful of rows per calibration, not a stream.

``system_event_id`` names the ``system_events`` row the same act wrote, **not**
a foreign key: ``system_events`` is partitioned by ``created_at`` with **30-day
retention** (§1.3) and a partitioned parent cannot back a plain single-column
foreign key. A ``NULL`` here after 30 days is not corruption — the structured
half of the audit (this table) outlives the free-text half on purpose.
"""

from __future__ import annotations

from alembic import op

TABLE = "meme_rule_set_param_history"

_CREATE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    rule_set_id uuid NOT NULL REFERENCES meme_rule_sets (id),
    changed_at timestamptz NOT NULL DEFAULT now(),
    changed_by text NOT NULL,
    reason text NOT NULL,
    key text NOT NULL,
    old_value jsonb,
    new_value jsonb NOT NULL,
    system_event_id uuid,
    CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
    CONSTRAINT ck_{TABLE}_changed_by_not_blank CHECK (changed_by <> ''),
    CONSTRAINT ck_{TABLE}_reason_not_blank CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_{TABLE}_key_not_blank CHECK (key <> '')
)
"""
_INDEX = f"CREATE INDEX ix_{TABLE}_rule_set_changed_at ON {TABLE} (rule_set_id, changed_at)"


def create_meme_rule_set_param_history() -> None:
    op.execute(_CREATE)
    op.execute(_INDEX)


def drop_meme_rule_set_param_history() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")


def refuse_a_downgrade_that_would_lose_the_param_history() -> None:
    """§17.7: reversing is allowed, losing the diary of a calibration is not."""
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - the table name is this module's own frozen constant
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {TABLE} rows exist - "
        f"the only durable record of a param a rule set carried before it was "
        f"overwritten (R27); nothing else can rebuild them', "
        f"HINT = 'COPY (SELECT * FROM {TABLE}) TO ... before reversing'; "
        f"END IF; END $$;"
    )
