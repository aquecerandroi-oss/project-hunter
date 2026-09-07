"""The geometry of a filed request, and the dust that is not a position — §21.

``0009_paper_geometry`` adds the two columns three tasks asked for by name, and
tightens the request guard around the first of them:

- **``trade_proposals.request_payload``** — what an operator actually asked for.
  ``trade_proposals`` stored the *identity* of a request (the key and the
  digest) and none of its **geometry**, so a row filed by the API could be
  recognised and never decided: ``notes-T3.5.md`` §5.1 records the execution
  worker logging ``pending_request_without_geometry`` once per second, for ever,
  because ``entry_ref``, ``stop``, ``assumed_costs`` and the ceiling exist
  nowhere in the schema. Writing them into ``risk_decision`` was never an option
  — the guard of §19.4 refuses an ``INSERT`` by the API that carries one, and it
  would be a decision nobody took.
- **``positions.is_residual``** — the dust a spot exit leaves behind. A buy pays
  its fee in the coin, so the sellable quantity is almost never a multiple of
  ``step_size`` and a few ten-thousandths stay in the wallet, below ``min_qty``
  and unsellable at any price. Until now that leftover sat in ``status =
  'closing'`` with ``qty > 0``, and every reader of "live positions" counted it:
  a slot held for ever, exposure that is not exposure, and a second order in
  that coin refused as a duplicate (``review-T3.5.md`` item 3, reproduced four
  hours after the stop).

**The request guard grows two refusals, and both come from the security review
of ``0007``** (``review-T3.1c-security.md``, S1): a filed request must *carry*
its geometry, and it may **not** carry a ``request_digest`` or a
``kill_switch_snapshot``. The digest is what proves "this is the same request",
and a digest written by the caller proves nothing about the caller — the engine
recomputes it from the payload, the row and the market reference, and
``coalesce(request_digest, …)`` on a value the API supplied was trusting the
side of the wall the guard exists to hold.

Every list here is **frozen as of this revision**, like ``ddl/tables.py`` as of
``0001`` and ``ddl/paper_roles.py`` as of ``0007``: the guard body below is a
*copy* of ``0007``'s with the new branches, never a read of
``ddl.paper_roles._REQUEST_SHAPE`` at migration time, for the reason §16.5 and
§17.1 froze everything else in this package — a later edit there must not
silently redefine what ``0009`` installed. The **downgrade** goes the other way
and calls ``0007``'s own ``create_request_guard()``: reverting to ``0007`` means
having the guard ``0007`` describes.

Nothing here depends on session state: two columns, two constraints, one partial
index and one trigger that reads only ``NEW`` and ``pg_has_role``. No
session-level prepared statement, no ``LISTEN``/``NOTIFY``, no session advisory
lock (§18.10, §19.7, §20.6).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

REQUEST_GUARD = "trade_proposals_the_app_only_files_requests"
"""The same trigger ``0007`` created. This revision replaces its **body**."""

REQUEST_PAYLOAD_KEYS_0009: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("client_key", ("string",)),
    ("market_id", ("string",)),
    ("direction", ("string",)),
    ("entry_ref", ("string",)),
    ("stop", ("string",)),
    ("target", ("string", "null")),
    ("requested_notional", ("string", "null")),
    ("assumed_costs", ("object",)),
)
"""``key -> the JSON types it may hold`` in ``trade_proposals.request_payload``.

Eight keys, and **every one of them is present** in a well-formed payload:
"absent" is written as JSON ``null``, never by omission. That is the same choice
``opportunity_stage`` made with ``NONE`` instead of a nullable column (§17.1) —
a reader must not have to decide whether a missing ``target`` means "no target"
or "the writer forgot", and a key that is required to exist is a key a later
route can fill without another migration.

**Money is a JSON string**, as everywhere else the project canonicalises a
number (§17.8, ``model_dump(mode="json")``): a JSON number is a float on the way
back through most parsers, and a price that survives a round trip as
``0.30000000000000004`` is the bug the whole ``Decimal`` discipline exists to
prevent.

``target`` and ``requested_notional`` are the two that may be null: M3's
``ProposalRequest`` has no take-profit field at all — the exit geometry comes
from the protection cycle — and the ceiling is optional by contract
(RISK_ENGINE.md §4, "``requested_notional`` is only ever a ceiling the caller
adds"). The key exists so that T3.8's form and T3.14's bridge fill it rather
than migrate for it.

What is deliberately **not** here: ``organization_id``, ``portfolio_id``,
``agent_id`` and ``signal_id``. Those are columns, and a payload that repeated
them would be a second answer to a question the row already answers — the same
argument §19.3 makes about ``applied_attempts``. ``market_id`` and ``direction``
*are* repeated, and that is the exception on purpose: they are what makes the
payload self-describing enough to be read on its own, and the composite FKs
(§18.3) already make a disagreement between the two unrepresentable.
"""


_ABSENT = "absent"
"""What a missing key is called inside the CHECK — and why the ``coalesce`` is there.

``jsonb_typeof(payload -> 'k')`` is SQL ``NULL`` for an **absent** key and the
string ``'null'`` for a key present with JSON null, which looks like exactly the
distinction wanted. It is not enough on its own: a CHECK constraint is satisfied
when its expression evaluates to ``NULL`` (SQL's "unknown is not a violation"),
so ``jsonb_typeof(payload -> 'target') IN ('string','null')`` **accepts a payload
with no ``target`` at all**. Measured, not reasoned: the first version of this
constraint let a six-key payload through on a real Postgres 16, which is how this
line came to exist.

``coalesce(…, 'absent')`` turns the unknown into a value that no allow-list
contains, so presence and type are one comparison again. ``?&`` would work too
and is not used here: it puts a literal ``?`` into DDL that several DBAPI
paramstyles read as a placeholder, and it would still need the type half.
"""


def _payload_shape(column: str = "request_payload") -> str:
    """The CHECK that makes a malformed geometry unrepresentable."""
    clauses = [f"jsonb_typeof({column}) = 'object'"]
    for key, types in REQUEST_PAYLOAD_KEYS_0009:
        allowed = ", ".join(f"'{name}'" for name in types)
        clauses.append(f"coalesce(jsonb_typeof({column} -> '{key}'), '{_ABSENT}') IN ({allowed})")
    return f"{column} IS NULL OR (" + " AND ".join(clauses) + ")"


PAYLOAD_SHAPE_0009 = _payload_shape()
RESIDUAL_SHAPE_0009 = "NOT is_residual OR status = 'closing'"
"""Dust is a *closing* position and never an open one.

``is_residual`` says "what is left here is below the venue's minimum and cannot
be sold at any price". An ``open`` position claiming that would be a position the
wallet believes it holds and no reader counts — the worst of both. ``closed`` is
excluded for the opposite reason: a closed position holds nothing, so there is no
dust to declare (§21, and ``review-T3.5.md`` item 3).
"""

LIVE_POSITIONS_INDEX_0009 = "ix_positions_org_portfolio_live"
LIVE_POSITIONS_PREDICATE_0009 = "status <> 'closed' AND NOT is_residual"
"""The predicate every "live positions" reader is supposed to use from now on.

``LedgerRepository.open_positions`` (slots, exposure, duplicate-market refusal)
and the worker's own readers all ask the same question, and it is the question
the dust made them answer wrongly. The index leads with ``organization_id``
because §1 requires it of every composite index on a tenant table, and Alembic
does not compare an index *predicate* (§17.3), so ``test_schema_paper.py`` reads
``pg_indexes.indexdef`` instead of trusting ``alembic check``.
"""

_HAS_APP = f"pg_has_role(current_user, '{APP_ROLE}', 'USAGE')"
_HAS_WORKER = f"pg_has_role(current_user, '{WORKER_ROLE}', 'USAGE')"
_CALLER_IS_THE_APP = f"({_HAS_APP} AND NOT {_HAS_WORKER})"
"""The session holds the API's privileges and nothing beyond them — ``0007``'s
test, copied rather than imported (see the module docstring), and a *membership*
test rather than ``current_user = 'hunter_app'`` because a login that merely
inherits the role keeps every privilege while reporting its own name (§18.7)."""

_REQUEST_SHAPE_0009 = (
    "NEW.source <> 'manual' OR NEW.status <> 'pending' "
    "OR NEW.reservation_state <> 'none' OR NEW.reserved_slot "
    "OR NEW.admission_seq IS NOT NULL OR NEW.decided_at IS NOT NULL "
    "OR NEW.rejection_reason IS NOT NULL OR NEW.risk_decision <> '{}'::jsonb"
)
"""Everything a *request* is not yet — ``0007``'s clause, unchanged and copied."""

_FORGED_PROOF_0009 = "NEW.request_digest IS NOT NULL OR NEW.kill_switch_snapshot <> '{}'::jsonb"
"""The two columns the API may name and must not: the proof and the context.

``request_digest`` is what *proves* two requests are the same one, and the engine
read it back with ``coalesce(request_digest, :digest)`` — that is, it trusted the
digest the caller wrote. A caller that can choose the proof can make a second,
different order replay as the first one's decision (S1 of
``review-T3.1c-security.md``). With this branch there is nothing to coalesce: the
engine recomputes the digest from ``request_payload``, the row and the market
reference, and writes it at the moment it decides.

``kill_switch_snapshot`` is the same shape of lie one level up: it records *the
three scopes the decision was taken under*, and a request filed hours earlier has
not been decided under anything. A snapshot supplied by the API would be an alibi
attached to a decision nobody had taken yet.
"""

_MISSING_GEOMETRY_0009 = "NEW.request_payload IS NULL"
"""A request without its geometry cannot be decided, and pretends it can.

The shape of a non-null payload is a CHECK (:data:`PAYLOAD_SHAPE_0009`), which
applies to every writer; what the trigger adds is that the API may not skip it.
The engine's own ``INSERT`` (``hunter_core.admission.record.insert_proposal``)
legitimately writes none, because an agent proposal carries its geometry in the
decision it arrives with.
"""


def add_columns() -> None:
    """Raw DDL for the two columns, their constraints and the live-position index.

    ``is_residual`` is ``NOT NULL DEFAULT false``, which is an honest backfill and
    not an assumption: every existing row *is* a position, and the dust the
    column names is a state a later exit puts a row into. So there is no upgrade
    guard for it (§21.5), unlike the invariants ``0002``/``0003``/``0006`` had to
    refuse over.
    """
    op.execute("ALTER TABLE trade_proposals ADD COLUMN request_payload jsonb")
    op.execute(
        "ALTER TABLE trade_proposals ADD CONSTRAINT "
        f"ck_trade_proposals_request_payload_is_a_geometry CHECK ({PAYLOAD_SHAPE_0009})"
    )
    op.execute("ALTER TABLE positions ADD COLUMN is_residual boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE positions ADD CONSTRAINT "
        f"ck_positions_residual_is_a_closing_position CHECK ({RESIDUAL_SHAPE_0009})"
    )
    op.execute(
        f"CREATE INDEX {LIVE_POSITIONS_INDEX_0009} ON positions "
        f"(organization_id, portfolio_id) WHERE {LIVE_POSITIONS_PREDICATE_0009}"
    )


def drop_columns() -> None:
    """The exact reverse, innermost first."""
    op.execute(f"DROP INDEX IF EXISTS {LIVE_POSITIONS_INDEX_0009}")
    op.execute(
        "ALTER TABLE positions DROP CONSTRAINT IF EXISTS "
        "ck_positions_residual_is_a_closing_position"
    )
    op.execute("ALTER TABLE positions DROP COLUMN is_residual")
    op.execute(
        "ALTER TABLE trade_proposals DROP CONSTRAINT IF EXISTS "
        "ck_trade_proposals_request_payload_is_a_geometry"
    )
    op.execute("ALTER TABLE trade_proposals DROP COLUMN request_payload")


def create_request_guard_0009() -> None:
    """The request guard, with the geometry required and the proof forbidden.

    Three refusals instead of one, and each says which of the three happened: a
    row that arrives already decided, a row that supplies the proof of its own
    identity, and a row with no geometry to decide. Dropped and recreated rather
    than ``CREATE OR REPLACE``d so that the trigger and the function this
    revision installs are one object with one history — the same shape
    ``0008`` used for the two audited-move guards (§20.3).
    """
    op.execute(f"DROP TRIGGER IF EXISTS {REQUEST_GUARD} ON trade_proposals")
    op.execute(f"DROP FUNCTION IF EXISTS {REQUEST_GUARD}()")
    op.execute(f"""
CREATE FUNCTION {REQUEST_GUARD}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    BEGIN
        IF NOT {_CALLER_IS_THE_APP} THEN
            RETURN NEW;
        END IF;
        IF {_REQUEST_SHAPE_0009} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'trade_proposal ' || NEW.id || ' was filed by ' || current_user
                    || ' carrying a decision: the API files requests, the engine admits them',
                HINT = 'an INSERT by the application role must be a manual request: '
                    || 'source = manual, status = pending, no risk_decision, no '
                    || 'rejection_reason, no decided_at, no admission_seq and no '
                    || 'reservation. The sequence and the reservation are assigned under '
                    || 'the wallet lock by hunter_core.admission, which runs as the engine';
        END IF;
        IF {_FORGED_PROOF_0009} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'trade_proposal ' || NEW.id || ' was filed by ' || current_user
                    || ' carrying its own proof: request_digest and kill_switch_snapshot '
                    || 'are written by the engine, at the moment it decides',
                HINT = 'the digest is what proves two requests are the same one, so a '
                    || 'caller that chooses it can make a different order replay as an '
                    || 'earlier decision; the kill switch snapshot records the scopes a '
                    || 'decision was taken under, and a filed request has not been decided '
                    || 'under anything. File the geometry in request_payload and let '
                    || 'hunter_core.admission recompute the digest from it';
        END IF;
        IF {_MISSING_GEOMETRY_0009} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'trade_proposal ' || NEW.id || ' was filed by ' || current_user
                    || ' with no request_payload: a request without its geometry can '
                    || 'never be decided',
                HINT = 'request_payload carries what was asked - client_key, market_id, '
                    || 'direction, entry_ref, stop, target, requested_notional and '
                    || 'assumed_costs, money as JSON strings. Without it the execution '
                    || 'worker can only log pending_request_without_geometry, which is '
                    || 'what notes-T3.5.md section 5.1 recorded and this column ends';
        END IF;
        RETURN NEW;
    END;
$$
""")
    op.execute(
        f"CREATE TRIGGER {REQUEST_GUARD} BEFORE INSERT ON trade_proposals "
        f"FOR EACH ROW EXECUTE FUNCTION {REQUEST_GUARD}()"
    )


_DOWNGRADE_GUARDS: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT 1 FROM trade_proposals WHERE request_payload IS NOT NULL",
        "trade_proposals carry a request_payload; dropping the column discards the "
        "geometry an operator actually asked for - the entry reference, the stop, the "
        "ceiling and the cost hypothesis - which is not derivable from any column that "
        "remains. A pending request loses the only thing that would ever let it be "
        "decided, and a decided one loses the inputs its decision answered",
        "export the payloads with their proposal ids before reversing, and understand "
        "what it costs: every request still pending becomes undecidable for ever, which "
        "is the state notes-T3.5.md section 5.1 measured and this revision ended",
    ),
    (
        "SELECT 1 FROM positions WHERE is_residual",
        "positions are marked as residual dust - a leftover below the venue's minimum "
        "quantity, unsellable at any price; dropping the column makes each of them a "
        "live position again, holding a slot, counting as exposure and refusing the "
        "next order in that coin as a duplicate, which is exactly the state "
        "review-T3.5.md item 3 reproduced four hours after a stop",
        "export those position ids before reversing, or settle the dust first (sell it "
        "with the next exit, or close the position), so that reverting loses a column "
        "and not a distinction the wallet depends on",
    ),
)
"""Reversing is allowed; losing an obligation or a distinction is not.

The §17.7 boundary, applied twice. Both are *live* facts and neither is
recomputable: a payload is what a person typed, and residual-ness is a judgement
made against the venue's filters at the moment of an exit, with a ``step_size``
that can change afterwards.

**``signal_id`` has no guard here, and that is a statement**: this revision does
not add the column. ``trade_proposals.signal_id`` has existed since
``0001_initial_schema`` (§7) with its FK to ``agent_signals`` and its index, so
there is nothing for a ``0009`` downgrade to take away — see §21.3.
"""


def refuse_a_downgrade_that_would_lose_a_request_or_hide_dust() -> None:
    """Count the offenders and refuse by name, in the precedent of ``0002``."""
    for count_sql, message, hint in _DOWNGRADE_GUARDS:
        safe_message = message.replace("'", "''")
        safe_hint = hint.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM ({count_sql}) AS offending; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
            f"HINT = '{safe_hint}'; END IF; END $$;"
        )
