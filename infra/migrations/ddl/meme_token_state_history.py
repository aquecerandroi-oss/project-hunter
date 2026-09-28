"""``0067_meme_token_state_history`` — the append-only history of a token's
``completed_at``/``migrated_at`` (EXP-M26 J, Astra's must-fix 2; ``docs/DATABASE.md`` §70).

**Why it exists.** ``meme_tokens.completed_at`` is a reduction written with
``LEAST(existing, new)`` — it can move *earlier* when the indexer's retrospective
``gd`` arrives (§36.1) — and ``migrated_at`` is written once but carries the
event's instant, not the write's. A reading that must know those two values *as
they were known at an instant L* (H-022's read, ``infra/research/exp_m26``) had
only the current row: a fact written between L and the export could flip a
paper sale from priced to censored. This table makes "known at L" a query.

**Written at commit, stamped at commit.** Two ``CONSTRAINT TRIGGER``s on
``meme_tokens`` (``AFTER INSERT`` for a row born with either value, ``AFTER
UPDATE`` for a change), ``DEFERRABLE INITIALLY DEFERRED``: the ``WHEN`` is checked
when the row changes, the row is inserted when the transaction commits, and
``recorded_at`` (``clock_timestamp()``) is therefore the commit's clock, not the
statement's — the worker's board loop (``wiring.run_board``) upserts a whole batch
in one transaction, and an immediate trigger would stamp a change minutes before
it became visible (Astra, J round 3). What remains between that clock and the
commit being visible is the commit's own processing; the H-022 export proves, before
its data snapshot, that no writer open since before L is still in flight
(``export_h022.sql`` 'meta', ``estado_token.provar_visibilidade``). A
token changed and deleted in the same transaction writes nothing (no parent at
commit: the history leaves with the token, the commit does not fail). A
session that ran ``SET CONSTRAINTS ALL IMMEDIATE`` would stamp at the statement
again — nothing in the repository does. The ``WHEN`` compares ``OLD``/``NEW``
values, **no** ``UPDATE OF`` list: the upsert names both columns on every
observation, so a column list would filter nothing; a no-op (``LEAST`` keeping
the older value, ``COALESCE`` keeping the first) queues no event.

**Only the trigger writes.** The function is ``SECURITY DEFINER`` (owned by the
migration role, ``search_path`` pinned to ``pg_catalog, pg_temp``, every object
schema-qualified, ``EXECUTE`` revoked from ``PUBLIC``), so neither role holds
``INSERT``: no application path can write a row, nor choose its ``recorded_at``.
``db_role`` is the role the writer had ``SET`` (``current_setting('role')``, which
``SECURITY DEFINER`` does not change), else the login.

**Retention = the token's.** ``mint`` references ``meme_tokens`` ``ON DELETE
CASCADE``: the history leaves exactly when its token is pruned by the declared
retention (``MEME_RETENTION_DAYS``, ``repo.prune_tokens`` behind
``app.meme_retention``), so a surviving token always has its whole history. The
cascade runs as the table owner: the worker holds **no** ``DELETE`` here.

Global (no ``organization_id``), no RLS (§1.1): a public token's lifecycle. Both
roles get ``SELECT`` only. The id is ``BIGSERIAL`` (declared deviation from §1,
like ``outbox_events``): rows are born inside the database, where no application
can mint a UUID v7, and insertion order breaks ties within a mint.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "meme_token_state_history"
FUNCTION = "meme_token_state_history_record"
INSERT_TRIGGER = "meme_tokens_state_history_on_insert"
UPDATE_TRIGGER = "meme_tokens_state_history_on_update"
STATE_COLUMNS: tuple[str, ...] = ("completed_at", "migrated_at")
OPERATIONS: tuple[str, ...] = ("insert", "update")

MEME_TOKEN_STATE_HISTORY_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
MEME_TOKEN_STATE_HISTORY_WORKER_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_CREATE = f"""
CREATE TABLE {TABLE} (
    id bigserial NOT NULL,
    mint text NOT NULL,
    column_name text NOT NULL,
    old_value timestamptz,
    new_value timestamptz,
    operation text NOT NULL,
    db_role text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
    CONSTRAINT fk_{TABLE}_mint_meme_tokens
        FOREIGN KEY (mint) REFERENCES meme_tokens (mint) ON DELETE CASCADE,
    CONSTRAINT ck_{TABLE}_column_is_a_state_column
        CHECK (column_name IN ({_labels(STATE_COLUMNS)})),
    CONSTRAINT ck_{TABLE}_operation_is_a_known_label
        CHECK (operation IN ({_labels(OPERATIONS)})),
    CONSTRAINT ck_{TABLE}_a_row_is_a_change CHECK (old_value IS DISTINCT FROM new_value),
    CONSTRAINT ck_{TABLE}_an_insert_starts_from_nothing
        CHECK (operation <> 'insert' OR old_value IS NULL)
)
"""
_INDEX = f"CREATE INDEX ix_{TABLE}_mint_recorded_at ON {TABLE} (mint, recorded_at)"
"""The one read ("every change of mint M, in order") and the foreign key's index
(every FK indexed, §1) — the cascade of a pruned token walks it too."""

_WRITER = "COALESCE(NULLIF(pg_catalog.current_setting('role'), 'none'), session_user)"


def _record(column: str, old: str, operation: str) -> str:
    return (
        f"INSERT INTO public.{TABLE} "  # noqa: S608 - this module's own frozen names
        "(mint, column_name, old_value, new_value, operation, db_role) "
        f"VALUES (NEW.mint, '{column}', {old}, NEW.{column}, '{operation}', {_WRITER}); "
    )


def _function_body() -> str:
    born = "".join(
        f"IF NEW.{c} IS NOT NULL THEN {_record(c, 'NULL', 'insert')}END IF; " for c in STATE_COLUMNS
    )
    moved = "".join(
        f"IF NEW.{c} IS DISTINCT FROM OLD.{c} THEN {_record(c, f'OLD.{c}', 'update')}END IF; "
        for c in STATE_COLUMNS
    )
    # A token changed and deleted in the same transaction has no parent left at commit:
    # its history leaves with it (the cascade's own rule) instead of failing the commit.
    gone = "PERFORM 1 FROM public.meme_tokens WHERE mint = NEW.mint; IF NOT FOUND THEN RETURN NULL; END IF; "
    return f"BEGIN {gone}IF TG_OP = 'INSERT' THEN {born}ELSE {moved}END IF; RETURN NULL; END"


def create_meme_token_state_history() -> None:
    op.execute(_CREATE)
    op.execute(_INDEX)
    op.execute(
        f"CREATE FUNCTION public.{FUNCTION}() RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$ {_function_body()} $$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.{FUNCTION}() FROM PUBLIC")
    born = " OR ".join(f"NEW.{c} IS NOT NULL" for c in STATE_COLUMNS)
    moved = " OR ".join(f"OLD.{c} IS DISTINCT FROM NEW.{c}" for c in STATE_COLUMNS)
    for trigger, event, when in (
        (INSERT_TRIGGER, "INSERT", born),
        (UPDATE_TRIGGER, "UPDATE", moved),
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER {event} ON meme_tokens "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN ({when}) "
            f"EXECUTE FUNCTION public.{FUNCTION}()"
        )


def grant_meme_token_state_history_privileges() -> None:
    for table in MEME_TOKEN_STATE_HISTORY_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_TOKEN_STATE_HISTORY_WORKER_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")


def refuse_a_downgrade_that_would_lose_a_state_change() -> None:
    """§17.7: reversing is allowed, losing what was known when is not. Writers
    first, in the worker's own order (``meme_tokens`` → history), so no change can
    land between the count and the drop and no lock cycle can form with an upsert
    already holding ``meme_tokens``."""
    op.execute("LOCK TABLE meme_tokens IN SHARE ROW EXCLUSIVE MODE")
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - this module's own frozen table name
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {TABLE} rows exist - "
        f"when each completed_at/migrated_at became known; the current row cannot rebuild it', "
        f"HINT = 'COPY (SELECT * FROM {TABLE}) TO ... before reversing'; "
        f"END IF; END $$;"
    )


def drop_meme_token_state_history() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER} ON meme_tokens")
    op.execute(f"DROP TRIGGER IF EXISTS {INSERT_TRIGGER} ON meme_tokens")
    op.execute(f"DROP FUNCTION IF EXISTS public.{FUNCTION}()")
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
