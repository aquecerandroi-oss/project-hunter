"""``0031_meme_lab_ticks`` — one durable row per tick of the Lab loop (T4.15).

Until this revision the only record of what the gate refused, minute by
minute, was ``hb:meme:radar``'s ``lab_gate_refusals`` — a Redis hash the
next tick overwrites. The daily close (``infra/scripts/meme_close_day.py``)
has to answer "how much of the day did the gate actually see, and why did it
refuse?" for a day that ended hours ago, and a heartbeat cannot answer that.

**``meme_lab_ticks``** — the loop writes one row at the end of every tick:
when it ran (``ticked_at``, the tick's own ``now``), the newest closed minute
it evaluated (``tick_minute``, ``NULL`` when the backlog had nothing), the
counters ``TickReport`` already carries, and ``refusals`` — the same
``{rule set name: {refusal: count}}`` the heartbeat publishes, frozen. Global
and RLS-free (DATABASE.md §1.1), the shape of every ``meme_*`` table.

**Who writes what.** ``hunter_worker``: ``SELECT``/``INSERT`` (``ON CONFLICT
DO NOTHING`` on ``ticked_at`` — a restart re-running the same instant writes
nothing twice). ``hunter_app``: ``SELECT`` (the diary and, later, the desk).
``UPDATE``/``DELETE`` to nobody: a tick is what happened. **The downgrade
refuses** while a row exists (§17.7): the day's coverage lesson is derived
from these rows and nothing else can rebuild them.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_LAB_TICK_TABLES_0031: tuple[str, ...] = ("meme_lab_ticks",)
MEME_LAB_TICKS_APP_READ_ONLY_TABLES: tuple[str, ...] = MEME_LAB_TICK_TABLES_0031
MEME_LAB_TICKS_WORKER_APPEND_TABLES: tuple[str, ...] = MEME_LAB_TICK_TABLES_0031

_TICKS = """
CREATE TABLE meme_lab_ticks (
    ticked_at timestamptz NOT NULL,
    tick_minute timestamptz,
    minutes_evaluated integer NOT NULL,
    rows_evaluated integer NOT NULL,
    rule_sets_active integer NOT NULL,
    proposals integer NOT NULL,
    expired integer NOT NULL,
    cancelled integer NOT NULL,
    fills integer NOT NULL,
    unfilled integer NOT NULL,
    closes integer NOT NULL,
    bets_open integer NOT NULL,
    refusals jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT pk_meme_lab_ticks PRIMARY KEY (ticked_at),
    CONSTRAINT ck_meme_lab_ticks_counters_are_not_negative
        CHECK (minutes_evaluated >= 0 AND rows_evaluated >= 0 AND rule_sets_active >= 0
               AND proposals >= 0 AND expired >= 0 AND cancelled >= 0 AND fills >= 0
               AND unfilled >= 0 AND closes >= 0 AND bets_open >= 0),
    CONSTRAINT ck_meme_lab_ticks_refusals_is_an_object CHECK (jsonb_typeof(refusals) = 'object')
)
"""


def create_meme_lab_ticks() -> None:
    op.execute(_TICKS)


def grant_meme_lab_ticks_privileges() -> None:
    """Read for the API; read and append for the loop; nobody edits or deletes."""
    for table in MEME_LAB_TICKS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_LAB_TICKS_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def drop_meme_lab_ticks() -> None:
    for table in reversed(MEME_LAB_TICK_TABLES_0031):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def refuse_a_downgrade_that_would_lose_the_ticks() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "
        "SELECT count(*) INTO offenders FROM meme_lab_ticks; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_lab_ticks rows exist - "
        "the per-tick record of what the Lab gate saw and refused; the daily close "
        "derives the coverage lesson from them and nothing else can rebuild them', "
        "HINT = 'COPY (SELECT * FROM meme_lab_ticks) TO ... before reversing'; "
        "END IF; END $$;"
    )
