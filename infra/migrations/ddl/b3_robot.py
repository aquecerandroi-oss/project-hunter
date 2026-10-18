"""``0071_b3_robot`` — the B3 robot's schema: catalogue, RLS, grants, the shared
triggers and the downgrade guard (DATABASE.md §74, ``docs/RISK_ENGINE_B3.md``).

Twenty-four **tenant** tables (``organization_id``, RLS enabled *and forced*,
``tenant_isolation``) — the first tenant tables since ``0006``. The per-table
state machines are in :mod:`ddl.b3_robot_guards`; this module holds what every
table shares:

- **Grants** in three classes, frozen below. ``hunter_app`` is the API, the only
  writer (the robot reaches the database through it with its own token, design
  §3.7); ``hunter_worker`` reads (the watchdog and the daily report). Nobody has
  ``DELETE``.
- **Never deleted, never truncated** (every table except the heartbeats):
  ``b3_never_deleted`` refuses a row ``DELETE`` and a ``TRUNCATE`` for every
  role, the owner included. Consequence, declared: the ``ON DELETE CASCADE`` from
  ``organizations`` stops at a B3 row, so an organization with B3 records cannot
  be removed — that trail is evidence of real-money decisions.
- **Append-only** (:data:`B3_APP_APPEND_TABLES`): ``b3_append_only`` refuses any
  ``UPDATE``.
- **Retire-only** config (:data:`B3_APP_CONFIG_TABLES`): the only change a row
  takes is its retirement column set once; the privilege is the column grant.
- **Audited** (:data:`B3_AUDITED`): a deferred constraint trigger requires, at
  COMMIT, an ``audit_logs`` row of the same organization with ``entity_type`` =
  the table name and ``entity_id`` = the row's identity, written by **this**
  transaction (``xmin = pg_current_xact_id()::xid`` — §18.7/§20.2's proof).
  A write inside a ``SAVEPOINT`` carries a subtransaction xid and is refused:
  a false refusal, never a false approval.

Nothing depends on session state (no prepared statement, ``LISTEN``, session
advisory lock); the one advisory lock in the guards is transaction-scoped.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, ORG_MATCH, TENANT_POLICY, WORKER_ROLE

B3_APP_CONFIG_TABLES: dict[str, str] = {
    "b3_risk_profiles": "superseded_at",
    "b3_session_grids": "retired_at",
    "b3_holidays": "retired_at",
    "b3_contracts": "retired_at",
    "b3_fee_schedules": "retired_at",
}
"""``SELECT``/``INSERT`` and ``UPDATE`` of the retirement column only, for ``hunter_app``."""

B3_APP_APPEND_TABLES: tuple[str, ...] = (
    "b3_spec_pins",
    "b3_strategy_magics",
    "b3_kill_switch_transitions",
    "b3_robot_instances",
    "b3_entry_proposals",
    "b3_robot_events",
    "b3_deals",
    "b3_reconciliations",
    "b3_session_anchors",
    "b3_exit_intents",
)
"""``SELECT`` + ``INSERT`` for ``hunter_app`` — never ``UPDATE`` (a trigger holds the owner too)."""

B3_APP_NO_DELETE_TABLES: tuple[str, ...] = (
    "b3_robot_accounts",
    "b3_robot_authority",
    "b3_management_epochs",
    "b3_robot_heartbeats",
    "b3_entry_intents",
    "b3_orders",
    "b3_positions",
    "b3_sltp_requests",
    "b3_bracket_learning",
)
"""``SELECT``/``INSERT``/``UPDATE`` for ``hunter_app`` — state machines, held by their guards."""

B3_TENANT_TABLES: tuple[str, ...] = (
    *B3_APP_CONFIG_TABLES,
    *B3_APP_APPEND_TABLES,
    *B3_APP_NO_DELETE_TABLES,
)
"""Every table this revision adds — all tenant, all RLS-forced. Frozen."""

B3_AUDITED: dict[str, str] = {
    "b3_risk_profiles": "id",
    "b3_session_grids": "id",
    "b3_holidays": "id",
    "b3_contracts": "id",
    "b3_fee_schedules": "id",
    "b3_spec_pins": "id",
    "b3_strategy_magics": "id",
    "b3_robot_accounts": "id",
    "b3_kill_switch_transitions": "id",
    "b3_robot_instances": "instance_id",
    "b3_robot_authority": "id",
    "b3_management_epochs": "epoch_id",
    "b3_entry_proposals": "proposal_id",
    "b3_entry_intents": "proposal_id",
    "b3_orders": "id",
    "b3_deals": "id",
    "b3_positions": "id",
    "b3_sltp_requests": "sltp_request_id",
    "b3_exit_intents": "id",
    "b3_bracket_learning": "id",
    "b3_reconciliations": "id",
    "b3_session_anchors": "id",
}
"""Table -> the column ``audit_logs.entity_id`` names. Absent on purpose:
``b3_robot_heartbeats`` (liveness every 5 s) and ``b3_robot_events`` (a receipt;
the event's effects are audited). ``b3_reconciliations`` only when not clean."""

NOT_DELETED: tuple[str, ...] = tuple(t for t in B3_TENANT_TABLES if t != "b3_robot_heartbeats")

AUDIT_FUNCTION = "b3_mutation_is_audited"
NEVER_DELETED = "b3_never_deleted"
APPEND_ONLY = "b3_append_only"
RETIRE_ONLY = "b3_retire_only"
CLIENT_ORDER_ID = "b3_client_order_id"


def _function(name: str, body: str, *, returns: str = "trigger") -> None:
    op.execute(f"""
CREATE FUNCTION {name}() RETURNS {returns}
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $${body}$$
""")


def create_client_order_id_function() -> None:
    """§1.1: ``"HB" + base32(sha256(proposal_id.bytes)).rstrip("=").upper()[:16]``.

    Sixteen base32 characters are exactly the first 80 bits (10 bytes) of the
    digest, so the function never needs padding. ``uuid_send`` is the 16
    big-endian bytes, i.e. Python's ``uuid.bytes``. ``IMMUTABLE`` honestly: it
    reads nothing but its argument, and every name is ``pg_catalog``-pinned.
    """
    op.execute(f"""
CREATE FUNCTION {CLIENT_ORDER_ID}(proposal_id uuid) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT 'HB' || string_agg(
               substr('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567',
                      substr(b.bits, i * 5 + 1, 5)::bit(5)::integer + 1, 1),
               '' ORDER BY i)
    FROM (
        SELECT string_agg(get_byte(sha256(uuid_send(proposal_id)), k)::bit(8)::text, ''
                          ORDER BY k) AS bits
        FROM generate_series(0, 9) AS k
    ) AS b, generate_series(0, 15) AS i
$$
""")  # noqa: S608


def drop_client_order_id_function() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {CLIENT_ORDER_ID}(uuid)")


def enable_b3_row_level_security() -> None:
    for table in B3_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {TENANT_POLICY} ON {table} USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})"
        )


def grant_b3_privileges() -> None:
    for table, column in B3_APP_CONFIG_TABLES.items():
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT UPDATE ({column}) ON {table} TO {APP_ROLE}")
    for table in B3_APP_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
    for table in B3_APP_NO_DELETE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    for table in B3_TENANT_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")


def create_shared_triggers() -> None:
    """Never deleted, append-only, retire-only, and audited."""
    _function(
        NEVER_DELETED,
        """
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = 'restrict_violation',
            MESSAGE = TG_TABLE_NAME || ': a B3 record is never deleted (' || TG_OP || ')',
            HINT = 'retire or close it; an organization with B3 records cannot be removed '
                || '(DATABASE.md §74)';
    END;
""",
    )
    _function(
        APPEND_ONLY,
        """
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = 'restrict_violation',
            MESSAGE = TG_TABLE_NAME || ' is append-only: a recorded fact is never edited',
            HINT = 'write a new row (DATABASE.md §74)';
    END;
""",
    )
    _function(
        RETIRE_ONLY,
        """
    DECLARE
        col text := TG_ARGV[0];
    BEGIN
        IF to_jsonb(OLD) ->> col IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                MESSAGE = TG_TABLE_NAME || ' ' || OLD.id || ' is already retired';
        END IF;
        IF to_jsonb(NEW) ->> col IS NULL
           OR to_jsonb(NEW) - col IS DISTINCT FROM to_jsonb(OLD) - col THEN
            RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                MESSAGE = TG_TABLE_NAME || ' ' || OLD.id || ' may only be retired (' || col || ')',
                HINT = 'a change is a new row; the old one is retired, never edited';
        END IF;
        RETURN NEW;
    END;
""",
    )
    _function(
        AUDIT_FUNCTION,
        """
    DECLARE
        row_id uuid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM audit_logs a
            WHERE a.entity_type = TG_TABLE_NAME
              AND a.entity_id = row_id
              AND a.organization_id = NEW.organization_id
              AND a.created_at >= now() - interval '1 day'
              AND a.xmin = pg_current_xact_id()::xid
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = 'integrity_constraint_violation',
                MESSAGE = TG_TABLE_NAME || ' ' || row_id || ' was written without an audit_logs '
                    || 'row of this transaction',
                HINT = 'insert audit_logs (organization_id, entity_type = ''' || TG_TABLE_NAME
                    || ''', entity_id = the row) in the same transaction, outside a SAVEPOINT';
        END IF;
        RETURN NULL;
    END;
""",
    )
    for table in NOT_DELETED:
        op.execute(
            f"CREATE TRIGGER {table}_never_deleted BEFORE DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {NEVER_DELETED}()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_never_truncated BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {NEVER_DELETED}()"
        )
    for table in B3_APP_APPEND_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY}()"
        )
    for table, column in B3_APP_CONFIG_TABLES.items():
        op.execute(
            f"CREATE TRIGGER {table}_retire_only BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {RETIRE_ONLY}('{column}')"
        )
    for table, column in B3_AUDITED.items():
        when = " WHEN (NOT NEW.clean)" if table == "b3_reconciliations" else ""
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_insert_audited AFTER INSERT ON {table} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW{when} "
            f"EXECUTE FUNCTION {AUDIT_FUNCTION}('{column}')"
        )
        if table in B3_APP_APPEND_TABLES:
            continue
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_update_audited AFTER UPDATE ON {table} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) "
            f"EXECUTE FUNCTION {AUDIT_FUNCTION}('{column}')"
        )


def drop_shared_functions() -> None:
    """After the tables are gone (dropping a table drops its triggers)."""
    for name in (AUDIT_FUNCTION, RETIRE_ONLY, APPEND_ONLY, NEVER_DELETED):
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")


def refuse_a_populated_downgrade() -> None:
    """§17.7: every B3 row is evidence of a real-money decision — refuse, never drop.

    Locked first so nothing lands between the count and the ``DROP``.
    """
    tables = ", ".join(B3_TENANT_TABLES)
    counts = " + ".join(f"(SELECT count(*) FROM {t})" for t in B3_TENANT_TABLES)  # noqa: S608
    op.execute(f"LOCK TABLE {tables} IN ACCESS EXCLUSIVE MODE")
    # FORCE ROW LEVEL SECURITY filters the owner too: without lifting it, a migrating
    # role that is not a superuser would count zero rows and drop real ones. Inside
    # the migration's transaction, so a refusal rolls this back with everything else.
    for table in B3_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"""
DO $$
DECLARE
    n bigint := {counts};
BEGIN
    IF n > 0 THEN
        RAISE EXCEPTION USING
            MESSAGE = '0071_b3_robot cannot be reversed: ' || n || ' B3 row(s) exist',
            HINT = 'every B3 row is evidence of a decision about real money; COPY the b3_* '
                || 'tables out and remove them deliberately before reversing (DATABASE.md §74)';
    END IF;
END
$$
""")
