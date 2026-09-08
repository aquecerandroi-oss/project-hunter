"""``0013_replay_runs`` — the durable receipt of a historical replay slice.

T3.19b shipped the replay engine and wrote one ledger row per run into two
places: ``system_events`` (``component = 'replay_engine'``) and a local JSONL.
Its brief forbade it from writing a migration, so it wrote one instead —
``.claude/state/brief-T3.19b-db-replay-runs.md`` — and this is the revision that
answers it.

Why a table at all, when the row already exists twice:

- ``system_events`` has **30-day retention** (DATABASE.md §1.3), and the
  replication protocol counts 15 and 30 days of results measured *from* a
  marker. A run older than the window the protocol reasons over would be
  unprovable exactly when someone asks;
- the JSONL is honest and fragile: it proves a run only if the file survived.

The question the scoreboard and the on-call actually ask — "how many simulated
decisions has this version accumulated, over what window, and when?" — is a
query, and a query needs a table.

**Every list here is frozen as of this revision**, the rule ``ddl/shadow.py``,
``ddl/analysis.py``, ``ddl/paper*.py``, ``ddl/strategy_purpose.py`` and
``ddl/replication.py`` state for their own: a later edit here must never change
what ``0013`` installs. :data:`REPLAY_COHORT_PATTERN_0013` is therefore a
**copy** of ``hunter_core.domain.enums.REPLAY_COHORT_PATTERN``, never an import
— the database's contract must not silently follow a later edit to a Python
constant (``ddl/paper_geometry.py``'s docstring) — and
``test_migrations.py::test_0013_and_the_domain_constant_agree_on_the_replay_grammar``
is what keeps the copy honest.

Described in ``docs/DATABASE.md`` §25.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "replay_runs"

_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

REPLAY_COHORT_PATTERN_0013 = f"^replay:{_UUID}$"
"""``replay:<run_id>`` and nothing else — the second branch of
``0012``'s ``COHORT_PATTERN_0012``, byte for byte.

A receipt is never ``prospective`` (that is the live clock's reserved forward
evaluation) and never a replication arm (that is a sibling running forward
too). Writing the wider grammar here and hoping callers stay inside it is the
kind of promise §15.6 calls a no-op.
"""

REPLAY_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT`` for ``hunter_app``. The scoreboard reads a receipt; it never
writes one, exactly like ``fx_observations`` and ``market_betas`` (§18.9)."""

REPLAY_WORKER_APPEND_TABLES: tuple[str, ...] = (TABLE,)
"""``SELECT``/``INSERT`` for ``hunter_worker`` — never ``UPDATE``, never
``DELETE``.

The strategy-worker is the only writer (``replay/ledger.py``), and a receipt
that its own writer can edit is not a receipt. This is also the argument that
decided §25.1's slice-per-row shape: the accumulating alternative would have
needed ``UPDATE`` on this very table.

No retention job either (§1.3 gains no row): these lines are the research
record, and the ``Registro de Tentativas`` rule counts attempts that nobody may
quietly stop counting.
"""


def grant_replay_run_privileges() -> None:
    """Read for the API, append for the worker, and nothing else for either."""
    for table in REPLAY_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in REPLAY_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def revoke_replay_run_privileges() -> None:
    """Reverse :func:`grant_replay_run_privileges`; the roles survive."""
    for table in {*REPLAY_APP_READ_ONLY_TABLES, *REPLAY_WORKER_APPEND_TABLES}:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}, {WORKER_ROLE}")


def refuse_a_downgrade_that_would_lose_a_receipt() -> None:
    """§17.7: reversing is allowed, losing evidence is not.

    A ``replay_runs`` row is the only durable proof that a given version was
    replayed over a given window at a given cost. ``system_events`` holds the
    same JSON for **30 days** and then deletes it; the JSONL exists only if
    whoever ran the job passed ``--ledger`` and kept the file. Dropping the
    table therefore destroys, silently and permanently, the count of simulated
    decisions the replication protocol reasons about — and "the migration
    reversed without error" would be the only report of it.

    Nothing is deleted here: the guard counts the offenders and refuses, naming
    them, with the instruction to export first — the same boundary, and the same
    deliberate absence of a ready-made command, as §18.9 and §24.6. On a database
    that never ran a replay it counts zero and the downgrade proceeds.
    """
    message = (
        "replay_runs rows would be dropped - the only durable receipt of a replay "
        "(system_events keeps the same JSON for 30 days and then deletes it, and the "
        "JSONL ledger exists only if someone kept the file)"
    )
    hint = (
        "export them first (COPY (SELECT * FROM replay_runs) TO ... ) and then delete the "
        "rows knowing that the simulated-decision count of docs/plans/REPLICATION.md loses "
        "its evidence"
    )
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {message}', "
        f"HINT = '{hint}'; END IF; END $$;"
    )
