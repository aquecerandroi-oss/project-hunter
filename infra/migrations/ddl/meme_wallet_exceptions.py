"""``0068_meme_wallet_exceptions`` — Everton's audited per-mint exception to
§3.2's ``wallet_unrecognized_holdings`` (decision 2026-09-28,
``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``).

**One table, global, RLS-free** (DATABASE.md §1.1), the shape of
``meme_live_*``/``meme_treasury_swaps``: the desk wallet belongs to no
organization. One row per exception: **one wallet, one token program, one
mint**, the balance (``max_atoms``, ``decimals``) and state (``require_frozen``)
the owner verified on chain, the evidence (``jsonb``: accounts, state,
authorities, slot, observed_at, how), the reason, the Obsidian note that
covers it (path + sha256) and who/when. A revocation fills
``revoked_at``/``revoked_by``/``revoke_reason`` once; a row is **never deleted**.

**Who writes what.** Only the schema owner, through
``infra/scripts/wallet_holding_exception.py`` (``--apply``, with an
``audit_logs`` row in the same transaction). ``hunter_worker`` (the executor's
holdings verdict, ``hunter_meme_executor.wallet_exceptions``) and ``hunter_app``
get ``SELECT`` and nothing else. A ``BEFORE UPDATE OR DELETE`` row trigger and a
``BEFORE TRUNCATE`` statement trigger hold the owner to the same rule: the only
change a row ever takes is its one revocation, every original column unchanged,
stamped ``revoked_at = now()`` — an accident guard, not a claim that a schema
owner cannot drop its own triggers. A ``BEFORE INSERT`` row trigger stamps
``created_at = now()`` whatever the writer passed and refuses a row born revoked
(database-architect review, 28/09). ``max_atoms`` is a u64 (``BETWEEN 1 AND
2^64 − 1``, which also refuses ``NaN``). At most one **active** row per (wallet, mint) (partial unique index).
**The downgrade refuses while any row exists**, revoked ones included (§17.7:
a revoked exception still explains the admissions it covered).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

TABLE = "meme_wallet_holding_exceptions"
FUNCTION = "meme_wallet_holding_exceptions_guard"
ROW_TRIGGER = "meme_wallet_holding_exceptions_revoke_only"
INSERT_TRIGGER = "meme_wallet_holding_exceptions_stamp_insert"
U64_MAX = 18_446_744_073_709_551_615
TRUNCATE_TRIGGER = "meme_wallet_holding_exceptions_no_truncate"
ACTIVE_INDEX = "ux_meme_wallet_holding_exceptions_active"
MEME_WALLET_EXCEPTIONS_APP_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)
MEME_WALLET_EXCEPTIONS_WORKER_READ_ONLY_TABLES: tuple[str, ...] = (TABLE,)

TOKEN_PROGRAMS_0068: tuple[str, ...] = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
)
ORIGINAL_COLUMNS: tuple[str, ...] = (
    "id",
    "wallet",
    "token_program",
    "mint",
    "max_atoms",
    "decimals",
    "require_frozen",
    "evidence",
    "reason",
    "note_path",
    "note_sha256",
    "created_by",
    "created_at",
)
"""What a revocation must leave untouched (the trigger compares them all)."""


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_CREATE = f"""
CREATE TABLE {TABLE} (
    id uuid NOT NULL,
    wallet text NOT NULL,
    token_program text NOT NULL,
    mint text NOT NULL,
    max_atoms numeric(20, 0) NOT NULL,
    decimals smallint NOT NULL,
    require_frozen boolean NOT NULL,
    evidence jsonb NOT NULL,
    reason text NOT NULL,
    note_path text NOT NULL,
    note_sha256 text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revoked_by text,
    revoke_reason text,
    CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
    CONSTRAINT ck_{TABLE}_program_is_a_token_program
        CHECK (token_program IN ({_labels(TOKEN_PROGRAMS_0068)})),
    CONSTRAINT ck_{TABLE}_identity_is_well_formed
        CHECK (char_length(wallet) BETWEEN 32 AND 44 AND char_length(mint) BETWEEN 32 AND 44
               AND char_length(created_by) > 0),
    CONSTRAINT ck_{TABLE}_a_reason_is_given CHECK (char_length(reason) >= 10),
    CONSTRAINT ck_{TABLE}_note_is_under_obsidian
        CHECK (note_path LIKE 'obsidian/%.md' AND char_length(note_sha256) = 64),
    CONSTRAINT ck_{TABLE}_atoms_fit_a_u64 CHECK (max_atoms BETWEEN 1 AND {U64_MAX}),
    CONSTRAINT ck_{TABLE}_decimals_fit_a_byte CHECK (decimals BETWEEN 0 AND 255),
    CONSTRAINT ck_{TABLE}_evidence_is_an_object CHECK (jsonb_typeof(evidence) = 'object'),
    CONSTRAINT ck_{TABLE}_a_revocation_is_whole
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)
               AND (revoked_at IS NULL) = (revoke_reason IS NULL)),
    CONSTRAINT ck_{TABLE}_a_revocation_is_named
        CHECK (revoked_at IS NULL OR (char_length(revoked_by) > 0
               AND char_length(revoke_reason) >= 10 AND revoked_at >= created_at))
)
"""

_INDEX = f"CREATE UNIQUE INDEX {ACTIVE_INDEX} ON {TABLE} (wallet, mint) WHERE revoked_at IS NULL"


def _guard_body() -> str:
    old = ", ".join(f"OLD.{c}" for c in ORIGINAL_COLUMNS)
    new = ", ".join(f"NEW.{c}" for c in ORIGINAL_COLUMNS)
    refuse = "RAISE EXCEPTION USING ERRCODE = 'restrict_violation', MESSAGE = 'PROJECT HUNTER: "
    return (
        "BEGIN "
        "IF TG_OP = 'INSERT' THEN "
        "IF NEW.revoked_at IS NOT NULL OR NEW.revoked_by IS NOT NULL "
        f"OR NEW.revoke_reason IS NOT NULL THEN {refuse}an exception is born active'; "
        "END IF; NEW.created_at := now(); RETURN NEW; END IF; "
        f"IF TG_OP IN ('DELETE', 'TRUNCATE') THEN {refuse}{TABLE} is never deleted - "
        "revoke the row (revoked_at, revoked_by, revoke_reason)'; END IF; "
        f"IF OLD.revoked_at IS NOT NULL THEN {refuse}exception ' || OLD.id || "
        "' is already revoked - a revocation is final'; END IF; "
        f"IF NEW.revoked_at IS NULL THEN {refuse}the only change an exception takes "
        "is its revocation'; END IF; "
        f"IF ROW({new}) IS DISTINCT FROM ROW({old}) THEN {refuse}a revocation leaves "
        "every original column unchanged'; END IF; "
        f"IF NEW.revoked_at IS DISTINCT FROM now() THEN {refuse}a revocation is stamped "
        "by the database (revoked_at = now())'; END IF; "
        "RETURN NEW; END"
    )


def create_meme_wallet_exceptions() -> None:
    op.execute(_CREATE)
    op.execute(_INDEX)
    op.execute(
        f"CREATE FUNCTION public.{FUNCTION}() RETURNS trigger LANGUAGE plpgsql "
        f"SET search_path = pg_catalog, pg_temp AS $$ {_guard_body()} $$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.{FUNCTION}() FROM PUBLIC")
    op.execute(
        f"CREATE TRIGGER {ROW_TRIGGER} BEFORE UPDATE OR DELETE ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{FUNCTION}()"
    )
    op.execute(
        f"CREATE TRIGGER {INSERT_TRIGGER} BEFORE INSERT ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{FUNCTION}()"
    )
    op.execute(
        f"CREATE TRIGGER {TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {TABLE} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{FUNCTION}()"
    )


def grant_meme_wallet_exceptions_privileges() -> None:
    """``SELECT`` to both roles, nothing else: the owner's CLI is the only writer."""
    for table in MEME_WALLET_EXCEPTIONS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_WALLET_EXCEPTIONS_WORKER_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")


def refuse_a_downgrade_that_would_lose_an_exception() -> None:
    """§17.7: count **every** row (a revoked one still explains the admissions it
    covered), under a lock that keeps a new row from landing between the count
    and the drop (Astra, design review)."""
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608 - this module's own frozen name
        f"SELECT count(*) INTO offenders FROM {TABLE}; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {TABLE} rows exist - each is an "
        "audited decision of the owner about the desk wallet (revoked ones included); "
        "dropping them loses why admissions were allowed', "
        f"HINT = 'COPY (SELECT * FROM {TABLE}) TO ... before reversing'; "
        "END IF; END $$;"
    )


def drop_meme_wallet_exceptions() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS public.{FUNCTION}()")
