"""``0071_b3_robot`` — the per-table guards of the B3 state machines (DATABASE.md §74).

What the contract (``docs/RISK_ENGINE_B3.md``) says no code path may do, the
schema refuses for every role:

- **Authority (§2)**: one row per account; a new grant needs the previous one
  revoked or past its expiry, bumps ``fencing_token`` by exactly one and stamps
  ``granted_at`` with the database clock; inside a grant nothing that anchors
  it (instance, host, session, token, ``granted_at``, ``authority_expires_at``)
  ever changes — no renewal; ``revoked``/``expired`` are terminal until a new
  grant; arming names the **current** ``limits_version`` and stamps ``armed_at``.
- **Claim (§3.3), the identity half**: ``approved → submitting`` locks the robot
  account row, then — with ``clock_timestamp()`` read *after* the lock (a waiting
  transaction's ``now()`` is stale, Astra R3 must-fix 1) — needs the account's
  authority to be this instance and token, active, ``entries`` and unexpired, the
  approval unexpired and the limits unchanged; it stamps ``claimed_at``. The kill
  switch and the grid version stay in the API's claim statement (R4), which
  takes the system → organization → robot locks first.
- **Intent (§3.1, §6.1)**: the transition table, terminals that never move, the
  decision and the claim written once.
- **Kill switch (§7)**: every robot-scope move needs its transition row in the
  same transaction (§18.7's shape); who may release what is in the CHECKs of
  ``b3_kill_switch_transitions``.
- **Position (§4)**: ``closed`` is terminal; an exit never returns to
  protection (I-X-3) — not even through ``unattributed``, because an exit
  intent pins it; the slot returns to ``idle`` only when no request of the
  position is still ``intended``/``unknown`` (I-SL-3).
- **SLTP request (§4.3)**: born ``intended``; a terminal status never moves; the
  request itself is frozen.
- **Config**: contiguous versions; no two current grids/contracts/fees overlap
  (a transaction-scoped advisory lock serializes the check, no extension).

Every guard is ``BEFORE`` and runs as the caller — under RLS for ``hunter_app``,
which only ever writes its own organization's rows.
"""

from __future__ import annotations

from alembic import op

FROZEN = "b3_frozen_columns"
_TERMINAL_INTENT = (
    "ARRAY['rejected', 'expired', 'aborted_before_send', 'broker_rejected', 'filled', "
    "'canceled', 'resolved_manual']"
)
_LOCK_ACCOUNT = (
    "PERFORM 1 FROM b3_robot_accounts WHERE organization_id = NEW.organization_id "
    "AND registered_account_hash = NEW.account_hash FOR UPDATE;"
)
_LOCK_ORG_ACCOUNTS = (
    "PERFORM 1 FROM b3_robot_accounts WHERE organization_id = NEW.organization_id "
    "ORDER BY id FOR UPDATE;"
)
_CURRENT_LIMITS = (
    "SELECT limits_version INTO current_limits FROM b3_risk_profiles "
    "WHERE organization_id = NEW.organization_id AND superseded_at IS NULL;"
)


def _refuse(message: str, hint: str = "") -> str:
    """A ``RAISE`` with a fixed SQLSTATE R4 can map (23001, restrict_violation)."""
    hint_sql = f", HINT = {hint}" if hint else ""
    return f"RAISE EXCEPTION USING ERRCODE = 'restrict_violation', MESSAGE = {message}{hint_sql};"


def _function(name: str, body: str) -> None:
    op.execute(f"""
CREATE FUNCTION {name}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $${body}$$
""")


def _trigger(name: str, timing: str, table: str, function: str, args: str = "") -> None:
    op.execute(
        f"CREATE TRIGGER {name} {timing} ON {table} FOR EACH ROW EXECUTE FUNCTION {function}({args})"
    )


_FROZEN_TABLES: dict[str, tuple[str, ...]] = {
    "b3_robot_heartbeats": ("instance_id", "organization_id", "account_hash"),
    "b3_management_epochs": (
        "epoch_id", "organization_id", "account_hash", "instance_id", "authority_id",
        "host_hash", "opened_at",
    ),
    "b3_entry_intents": (
        "proposal_id", "organization_id", "account_hash", "instance_id", "created_at",
    ),
    "b3_orders": (
        "id", "organization_id", "account_hash", "proposal_id", "ticket", "symbol", "side",
        "magic", "volume_initial", "created_at",
    ),
    "b3_positions": ("id", "organization_id", "account_hash", "position_id", "symbol", "created_at"),
    "b3_sltp_requests": (
        "sltp_request_id", "organization_id", "account_hash", "position_id", "epoch_id",
        "request_position_ticket", "sl", "tp", "purpose", "built_at", "created_at",
    ),
    "b3_bracket_learning": ("id", "organization_id", "account_hash", "session_date", "symbol"),
    "b3_robot_accounts": ("id", "organization_id", "registered_account_hash", "created_at"),
    "b3_robot_authority": ("id", "organization_id", "account_hash"),
}  # fmt: skip
"""Identity columns no ``UPDATE`` may move (one generic trigger, the columns as arguments)."""


def _create_frozen() -> None:
    _function(
        FROZEN,
        f"""
    DECLARE
        col text;
    BEGIN
        FOREACH col IN ARRAY TG_ARGV LOOP
            IF to_jsonb(NEW) -> col IS DISTINCT FROM to_jsonb(OLD) -> col THEN
                {_refuse("TG_TABLE_NAME || '.' || col || ' is an identity and never changes'")}
            END IF;
        END LOOP;
        RETURN NEW;
    END;
""",
    )
    for table, columns in _FROZEN_TABLES.items():
        args = ", ".join(f"'{c}'" for c in columns)
        _trigger(f"{table}_frozen", "BEFORE UPDATE", table, FROZEN, args)


def _create_config_guards() -> None:
    _function(
        "b3_risk_profiles_version",
        f"""
    DECLARE
        expected integer;
    BEGIN
        {_LOCK_ORG_ACCOUNTS}
        PERFORM pg_advisory_xact_lock(hashtextextended('b3_risk_profiles:' || NEW.organization_id, 0));
        SELECT coalesce(max(limits_version), 0) + 1 INTO expected
          FROM b3_risk_profiles WHERE organization_id = NEW.organization_id;
        IF NEW.limits_version IS DISTINCT FROM expected OR NEW.superseded_at IS NOT NULL THEN
            {_refuse("'b3_risk_profiles: the next version is ' || expected || ', born current'")}
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    _trigger(
        "b3_risk_profiles_version", "BEFORE INSERT", "b3_risk_profiles", "b3_risk_profiles_version"
    )
    _function(
        "b3_session_grids_guard",
        f"""
    DECLARE
        expected integer;
    BEGIN
        {_LOCK_ORG_ACCOUNTS}
        PERFORM pg_advisory_xact_lock(hashtextextended(
            'b3_session_grids:' || NEW.organization_id || ':' || NEW.symbol_root, 0));
        SELECT coalesce(max(grid_version), 0) + 1 INTO expected FROM b3_session_grids
         WHERE organization_id = NEW.organization_id AND symbol_root = NEW.symbol_root;
        IF NEW.grid_version IS DISTINCT FROM expected OR NEW.retired_at IS NOT NULL THEN
            {
            _refuse(
                "'b3_session_grids: the next version of ' || NEW.symbol_root || ' is ' || expected"
            )
        }
        END IF;
        IF EXISTS (
            SELECT 1 FROM b3_session_grids g
             WHERE g.organization_id = NEW.organization_id AND g.symbol_root = NEW.symbol_root
               AND g.special_day = NEW.special_day AND g.retired_at IS NULL
               AND daterange(g.valid_from, g.valid_until, '[]')
                   && daterange(NEW.valid_from, NEW.valid_until, '[]')
        ) THEN
            {
            _refuse(
                "'b3_session_grids: two current grids of ' || NEW.symbol_root || ' overlap'",
                "'retire the old grid first, in the same transaction'",
            )
        }
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    _trigger(
        "b3_session_grids_guard", "BEFORE INSERT", "b3_session_grids", "b3_session_grids_guard"
    )
    _function(
        "b3_validity_no_overlap",
        f"""
    DECLARE
        key_value text := to_jsonb(NEW) ->> TG_ARGV[0];
        found_overlap boolean;
    BEGIN
        PERFORM pg_advisory_xact_lock(hashtextextended(
            TG_TABLE_NAME || ':' || NEW.organization_id || ':' || key_value, 0));
        IF NEW.retired_at IS NOT NULL THEN
            {_refuse("TG_TABLE_NAME || ': a row is born current'")}
        END IF;
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %I t WHERE t.organization_id = $1 AND t.%I = $2 '
            'AND t.retired_at IS NULL AND daterange(t.valid_from, t.valid_until, %L) '
            '&& daterange($3, $4, %L))', TG_TABLE_NAME, TG_ARGV[0], '[]', '[]')
        INTO found_overlap USING NEW.organization_id, key_value, NEW.valid_from, NEW.valid_until;
        IF found_overlap THEN
            {
            _refuse(
                "TG_TABLE_NAME || ': two current rows of ' || key_value || ' overlap'",
                "'retire the old row first, in the same transaction'",
            )
        }
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    for table, key in (("b3_contracts", "root"), ("b3_fee_schedules", "symbol_root")):
        _trigger(
            f"{table}_no_overlap", "BEFORE INSERT", table, "b3_validity_no_overlap", f"'{key}'"
        )


def _create_kill_switch_guards() -> None:
    _function(
        "b3_robot_accounts_guard",
        f"""
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.kill_state <> 'ACTIVE' OR cardinality(NEW.active_causes) > 0 THEN
                {_refuse("'b3_robot_accounts: an account is registered ACTIVE, with no latch'")}
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.kill_state IS DISTINCT FROM OLD.kill_state
           OR NEW.active_causes IS DISTINCT FROM OLD.active_causes THEN
            NEW.kill_changed_at := now();
        END IF;
        RETURN NEW;
    END;
""",
    )
    _trigger(
        "b3_robot_accounts_guard",
        "BEFORE INSERT OR UPDATE",
        "b3_robot_accounts",
        "b3_robot_accounts_guard",
    )
    _function(
        "b3_robot_accounts_kill_is_audited",
        f"""
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM b3_kill_switch_transitions t
             WHERE t.organization_id = NEW.organization_id
               AND t.account_hash = NEW.registered_account_hash
               AND t.xmin = pg_current_xact_id()::xid
               AND t.from_state = OLD.kill_state AND t.to_state = NEW.kill_state
               AND t.from_causes @> OLD.active_causes AND t.from_causes <@ OLD.active_causes
               AND t.causes_after @> NEW.active_causes AND t.causes_after <@ NEW.active_causes
        ) THEN
            {
            _refuse(
                "'b3_robot_accounts: the robot kill switch moved from ' || OLD.kill_state "
                "|| ' to ' || NEW.kill_state || ' without its transition'",
                "'insert b3_kill_switch_transitions for this move in the same transaction'",
            )
        }
        END IF;
        RETURN NULL;
    END;
""",  # noqa: S608
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER b3_robot_accounts_kill_is_audited AFTER UPDATE "
        "ON b3_robot_accounts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "WHEN (OLD.kill_state IS DISTINCT FROM NEW.kill_state "
        "OR OLD.active_causes IS DISTINCT FROM NEW.active_causes) "
        "EXECUTE FUNCTION b3_robot_accounts_kill_is_audited()"
    )


def _create_authority_guard() -> None:
    _function(
        "b3_robot_authority_guard",
        f"""
    DECLARE
        stamp timestamptz;
        current_limits integer;
    BEGIN
        {_LOCK_ACCOUNT}
        stamp := clock_timestamp();
        IF TG_OP = 'INSERT' THEN
            IF NEW.fencing_token <> 1 OR NEW.status <> 'active' OR NEW.phase <> 'management' THEN
                {
            _refuse("'b3_robot_authority: the first grant is fencing_token 1, active, management'")
        }
            END IF;
            NEW.granted_at := stamp;
            RETURN NEW;
        END IF;
        IF NEW.authority_id <> OLD.authority_id THEN
            IF OLD.status = 'active' AND OLD.authority_expires_at > stamp THEN
                {
            _refuse(
                "'b3_robot_authority: the previous grant is still active'",
                "'revoke it (with the instance neutralized) before granting again, §2.2'",
            )
        }
            END IF;
            IF NEW.fencing_token <> OLD.fencing_token + 1 OR NEW.status <> 'active'
               OR NEW.phase <> 'management' OR NEW.revoked_at IS NOT NULL
               OR NEW.expired_at IS NOT NULL THEN
                {
            _refuse("'b3_robot_authority: a new grant is fencing_token + 1, active, management'")
        }
            END IF;
            NEW.granted_at := stamp;
            RETURN NEW;
        END IF;
        IF (NEW.host_hash, NEW.instance_id, NEW.session_date, NEW.fencing_token, NEW.granted_at,
            NEW.authority_expires_at)
           IS DISTINCT FROM (OLD.host_hash, OLD.instance_id, OLD.session_date, OLD.fencing_token,
                             OLD.granted_at, OLD.authority_expires_at) THEN
            {_refuse("'b3_robot_authority: a grant is never renewed nor moved (§2.4 G3)'")}
        END IF;
        IF OLD.status <> 'active' THEN
            IF to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
                {
            _refuse("'b3_robot_authority: ' || OLD.status || ' is terminal until a new grant'")
        }
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.phase = 'entries' AND OLD.phase <> 'entries' THEN
            IF NEW.status <> 'active' OR OLD.authority_expires_at <= stamp THEN
                {_refuse("'b3_robot_authority: arming needs an active, unexpired grant'")}
            END IF;
            {_CURRENT_LIMITS}
            IF current_limits IS DISTINCT FROM NEW.limits_version THEN
                {
            _refuse(
                "'b3_robot_authority: arming names limits_version ' || NEW.limits_version "
                "|| ', the current one is ' || coalesce(current_limits::text, 'none')"
            )
        }
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM b3_spec_pins p
                 WHERE p.organization_id = NEW.organization_id AND p.id = NEW.spec_pin_id
                   AND p.account_hash = NEW.account_hash
            ) THEN
                {_refuse("'b3_robot_authority: the spec pin is not of this account'")}
            END IF;
            NEW.armed_at := stamp;
        ELSIF NEW.phase = 'entries'
              AND (NEW.armed_at, NEW.armed_strategy_key, NEW.armed_strategy_version,
                   NEW.armed_params_hash, NEW.limits_version, NEW.spec_pin_id)
                  IS DISTINCT FROM (OLD.armed_at, OLD.armed_strategy_key,
                                    OLD.armed_strategy_version, OLD.armed_params_hash,
                                    OLD.limits_version, OLD.spec_pin_id) THEN
            {_refuse("'b3_robot_authority: re-arming is disarm, then arm'")}
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    _trigger(
        "b3_robot_authority_guard",
        "BEFORE INSERT OR UPDATE",
        "b3_robot_authority",
        "b3_robot_authority_guard",
    )


_INTENT_TRANSITIONS = """
            allowed := CASE OLD.status::text
                WHEN 'proposed' THEN ARRAY['rejected', 'approved', 'expired']
                WHEN 'approved' THEN ARRAY['expired', 'submitting']
                WHEN 'submitting' THEN ARRAY['aborted_before_send', 'working', 'partially_filled',
                                             'filled', 'broker_rejected', 'unknown']
                WHEN 'working' THEN ARRAY['partially_filled', 'filled', 'cancel_requested',
                                          'canceled', 'broker_rejected', 'unknown']
                WHEN 'partially_filled' THEN ARRAY['filled', 'cancel_requested', 'canceled',
                                                   'unknown']
                WHEN 'cancel_requested' THEN ARRAY['canceled', 'filled', 'unknown']
                WHEN 'unknown' THEN ARRAY['working', 'partially_filled', 'filled', 'canceled',
                                          'broker_rejected', 'resolved_manual']
                ELSE ARRAY[]::text[]
            END;"""
"""§3.1 plus the recovery edges of §6.1 (``proposed → expired`` when the instance
died, ``submitting → unknown``) and of §3.6 (``unknown`` → what the broker proves,
or ``resolved_manual``). Nothing ever goes back to ``approved``/``submitting``:
an intent is never re-sent (I-E-2)."""


def _create_intent_guard() -> None:
    _function(
        "b3_entry_intents_guard",
        f"""
    DECLARE
        allowed text[];
        auth record;
        current_limits integer;
        stamp timestamptz;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'proposed' THEN
                {_refuse("'b3_entry_intents: an intent is born proposed (§3.2)'")}
            END IF;
            RETURN NEW;
        END IF;
        IF OLD.status::text = ANY ({_TERMINAL_INTENT}) THEN
            IF to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
                {_refuse("'b3_entry_intents: ' || OLD.status || ' is terminal'")}
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.status <> OLD.status THEN{_INTENT_TRANSITIONS}
            IF NOT (NEW.status::text = ANY (allowed)) THEN
                {
            _refuse(
                "'b3_entry_intents: ' || OLD.status || ' -> ' || NEW.status "
                "|| ' is not a transition of §3.1'"
            )
        }
            END IF;
        END IF;
        IF OLD.decided_at IS NOT NULL
           AND (NEW.decision, NEW.decided_at, NEW.approved_at, NEW.expires_at, NEW.limits_version,
                NEW.grid_version, NEW.spec_pin_id, NEW.n_final, NEW.limit_price)
               IS DISTINCT FROM (OLD.decision, OLD.decided_at, OLD.approved_at, OLD.expires_at,
                                 OLD.limits_version, OLD.grid_version, OLD.spec_pin_id,
                                 OLD.n_final, OLD.limit_price) THEN
            {_refuse("'b3_entry_intents: the decision is written once'")}
        END IF;
        IF OLD.claimed_at IS NOT NULL
           AND (NEW.claimed_at, NEW.claim_instance_id, NEW.claim_fencing_token,
                NEW.send_deadline_utc)
               IS DISTINCT FROM (OLD.claimed_at, OLD.claim_instance_id, OLD.claim_fencing_token,
                                 OLD.send_deadline_utc) THEN
            {_refuse("'b3_entry_intents: the claim is written once (a repeat returns it, §3.3)'")}
        END IF;
        IF OLD.unknown_cause IS NOT NULL AND NEW.unknown_cause IS DISTINCT FROM OLD.unknown_cause
           AND NOT (NEW.status = 'unknown' AND OLD.status <> 'unknown') THEN
            {_refuse("'b3_entry_intents: unknown_cause changes only on entering unknown'")}
        END IF;
        IF OLD.status = 'approved' AND NEW.status = 'submitting' THEN
            {_LOCK_ACCOUNT}
            stamp := clock_timestamp();
            SELECT a.instance_id, a.fencing_token, a.status, a.phase, a.authority_expires_at
              INTO auth FROM b3_robot_authority a
             WHERE a.organization_id = NEW.organization_id AND a.account_hash = NEW.account_hash;
            IF NOT FOUND OR auth.instance_id <> NEW.claim_instance_id
               OR auth.fencing_token <> NEW.claim_fencing_token OR auth.status <> 'active'
               OR auth.authority_expires_at <= stamp THEN
                {_refuse("'b3 claim refused: authority_mismatch'")}
            END IF;
            IF auth.phase <> 'entries' THEN
                {_refuse("'b3 claim refused: not_armed'")}
            END IF;
            IF OLD.expires_at <= stamp THEN
                {_refuse("'b3 claim refused: approval_expired'")}
            END IF;
            {_CURRENT_LIMITS}
            IF current_limits IS DISTINCT FROM OLD.limits_version THEN
                {_refuse("'b3 claim refused: limits_changed'")}
            END IF;
            NEW.claimed_at := stamp;
            IF NEW.send_deadline_utc <= stamp
               OR NEW.send_deadline_utc > LEAST(OLD.expires_at, auth.authority_expires_at) THEN
                {
            _refuse(
                "'b3_entry_intents: send_deadline_utc must lie in (claimed_at, "
                "min(expires_at, authority_expires_at)]'"
            )
        }
            END IF;
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    _trigger(
        "b3_entry_intents_guard",
        "BEFORE INSERT OR UPDATE",
        "b3_entry_intents",
        "b3_entry_intents_guard",
    )


def _create_record_guards() -> None:
    """Epochs close once; positions; SLTP requests; ``k`` only grows."""
    _function(
        "b3_management_epochs_guard",
        f"""
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.closed_at IS NOT NULL THEN
                {_refuse("'b3_management_epochs: an epoch is born open'")}
            END IF;
            RETURN NEW;
        END IF;
        IF OLD.closed_at IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
            {_refuse("'b3_management_epochs: a closed epoch never changes'")}
        END IF;
        RETURN NEW;
    END;
""",
    )
    _trigger(
        "b3_management_epochs_guard",
        "BEFORE INSERT OR UPDATE",
        "b3_management_epochs",
        "b3_management_epochs_guard",
    )
    _function(
        "b3_positions_guard",
        f"""
    BEGIN
        -- closed is terminal, but the slot is the request's fact, not the position's:
        -- P3/P4 may free it and journal_lost may make it unknown after the close (§4.3, §6.5).
        IF OLD.state = 'closed' AND to_jsonb(NEW) - 'updated_at' - 'sltp_slot'
           IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' - 'sltp_slot' THEN
            {_refuse("'b3_positions: closed is terminal (only the SLTP slot may still move)'")}
        END IF;
        -- the reason an exit started with stays, except a reversal found during it (§4.2).
        IF OLD.exit_reason IS NOT NULL AND NEW.exit_reason IS DISTINCT FROM OLD.exit_reason
           AND NEW.exit_reason IS DISTINCT FROM 'reversal' THEN
            {_refuse("'b3_positions: an exit keeps its reason (only a reversal replaces it)'")}
        END IF;
        IF OLD.state IN ('exiting', 'exit_overdue')
           AND NEW.state NOT IN ('exiting', 'exit_overdue', 'closed', 'unattributed') THEN
            {_refuse("'b3_positions: an exit started ends only in closed (I-X-3)'")}
        END IF;
        IF NEW.state IN ('unprotected', 'protected', 'degraded') AND EXISTS (
            SELECT 1 FROM b3_exit_intents e
             WHERE e.organization_id = NEW.organization_id AND e.account_hash = NEW.account_hash
               AND e.position_id = NEW.position_id
        ) THEN
            {_refuse("'b3_positions: an exit started ends only in closed (I-X-3)'")}
        END IF;
        IF NEW.sltp_slot = 'idle' AND OLD.sltp_slot <> 'idle' AND EXISTS (
            SELECT 1 FROM b3_sltp_requests r
             WHERE r.organization_id = NEW.organization_id AND r.account_hash = NEW.account_hash
               AND r.position_id = NEW.position_id AND r.status IN ('intended', 'unknown')
        ) THEN
            {
            _refuse(
                "'b3_positions: the slot returns to idle only after P1, P3 or P4 (I-SL-3)'",
                "'resolve the intended/unknown request of this position first'",
            )
        }
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    _trigger("b3_positions_guard", "BEFORE UPDATE", "b3_positions", "b3_positions_guard")
    _function(
        "b3_positions_exit_is_durable",
        f"""
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM b3_exit_intents e
             WHERE e.organization_id = NEW.organization_id AND e.account_hash = NEW.account_hash
               AND e.position_id = NEW.position_id
        ) THEN
            {
            _refuse(
                "'b3_positions: ' || NEW.state || ' without its b3_exit_intents row'",
                "'record the exit obligation (exit_due_at, deadline_at) in the same "
                "transaction, §5.2'",
            )
        }
        END IF;
        RETURN NULL;
    END;
""",  # noqa: S608
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER b3_positions_exit_is_durable AFTER INSERT OR UPDATE "
        "ON b3_positions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "WHEN (NEW.state IN ('exiting', 'exit_overdue')) "
        "EXECUTE FUNCTION b3_positions_exit_is_durable()"
    )
    _function(
        "b3_sltp_requests_guard",
        f"""
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'intended' THEN
                {_refuse("'b3_sltp_requests: a request is recorded intended, before it is sent'")}
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
            OLD.status = 'intended'
            OR (OLD.status = 'unknown' AND NEW.status IN ('done', 'rejected', 'moot',
                                                         'resolved_manual'))
        ) THEN
            {
            _refuse(
                "'b3_sltp_requests: ' || OLD.status || ' -> ' || NEW.status "
                "|| ' would downgrade a request (§4.3)'"
            )
        }
        END IF;
        IF OLD.status IN ('not_sent', 'done', 'rejected', 'moot', 'resolved_manual')
           AND to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
            {_refuse("'b3_sltp_requests: ' || OLD.status || ' is terminal'")}
        END IF;
        RETURN NEW;
    END;
""",
    )
    _trigger(
        "b3_sltp_requests_guard",
        "BEFORE INSERT OR UPDATE",
        "b3_sltp_requests",
        "b3_sltp_requests_guard",
    )
    _function(
        "b3_bracket_learning_grows",
        f"""
    BEGIN
        IF NEW.k < OLD.k THEN
            {_refuse("'b3_bracket_learning: k only grows within a session (§5.3)'")}
        END IF;
        RETURN NEW;
    END;
""",
    )
    _trigger(
        "b3_bracket_learning_grows",
        "BEFORE UPDATE",
        "b3_bracket_learning",
        "b3_bracket_learning_grows",
    )


GUARD_FUNCTIONS: tuple[str, ...] = (
    FROZEN,
    "b3_risk_profiles_version",
    "b3_session_grids_guard",
    "b3_validity_no_overlap",
    "b3_robot_accounts_guard",
    "b3_robot_accounts_kill_is_audited",
    "b3_robot_authority_guard",
    "b3_entry_intents_guard",
    "b3_management_epochs_guard",
    "b3_positions_guard",
    "b3_positions_exit_is_durable",
    "b3_sltp_requests_guard",
    "b3_bracket_learning_grows",
)
"""Dropped by the downgrade after the tables (a table drop takes its triggers)."""


def create_b3_guards() -> None:
    _create_frozen()
    _create_config_guards()
    _create_kill_switch_guards()
    _create_authority_guard()
    _create_intent_guard()
    _create_record_guards()


def drop_b3_guard_functions() -> None:
    for name in GUARD_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
