"""``0051_meme_treasury_swaps`` — the audit trail of every USDC->SOL treasury
top-up the executor ever attempted (T4.54).

**One table, global, RLS-free** (DATABASE.md §1.1), the shape of
``meme_wallet_trades``: this wallet's treasury belongs to no organization.
Written only by ``hunter_worker`` (the meme-executor's own
``hunter_meme_executor.treasury`` module, which signs nothing else and never
holds a key beyond the one ``MemeSigner`` already reads once); ``hunter_app``
reads it for the desk. One row per attempt, updated in place as it advances
through ``quoted -> simulated -> submitted -> confirmed | failed``, or stops
at ``refused`` before anything is ever built. A ``refused`` row never carries
a signature (nothing was sent); a ``confirmed`` row always carries one, the
filled amount, and the wallet's SOL balance after — the three numbers a swap
is judged by. Nothing here is deleted: like every meme audit table, the
downgrade refuses while a row exists (§17.7).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_TREASURY_SWAPS_TABLE = "meme_treasury_swaps"

TREASURY_SWAP_STATUSES_0051: tuple[str, ...] = (
    "quoted",
    "simulated",
    "submitted",
    "confirmed",
    "failed",
    "refused",
)


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_TABLE = f"""
CREATE TABLE meme_treasury_swaps (
    id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL,
    usdc_in numeric(28, 10) NOT NULL,
    sol_out_quoted numeric(28, 10) NOT NULL,
    sol_out_filled numeric(28, 10),
    price_impact_pct numeric(9, 6) NOT NULL,
    slippage_bps integer NOT NULL,
    signature text,
    status text NOT NULL,
    refusal text,
    wallet_sol_before numeric(28, 10) NOT NULL,
    wallet_sol_after numeric(28, 10),
    CONSTRAINT pk_meme_treasury_swaps PRIMARY KEY (id),
    CONSTRAINT ck_meme_treasury_swaps_status_is_a_known_label
        CHECK (status IN ({_labels(TREASURY_SWAP_STATUSES_0051)})),
    CONSTRAINT ck_meme_treasury_swaps_a_refusal_is_named
        CHECK ((status = 'refused') = (refusal IS NOT NULL)),
    CONSTRAINT ck_meme_treasury_swaps_a_refused_swap_sends_nothing
        CHECK (status <> 'refused' OR signature IS NULL),
    CONSTRAINT ck_meme_treasury_swaps_a_confirmed_swap_has_a_fill
        CHECK (status <> 'confirmed' OR (signature IS NOT NULL
               AND sol_out_filled IS NOT NULL AND wallet_sol_after IS NOT NULL)),
    CONSTRAINT ck_meme_treasury_swaps_amounts_are_not_negative
        CHECK (usdc_in >= 0 AND sol_out_quoted >= 0
               AND (sol_out_filled IS NULL OR sol_out_filled >= 0)
               AND price_impact_pct >= 0 AND slippage_bps >= 0
               AND wallet_sol_before >= 0
               AND (wallet_sol_after IS NULL OR wallet_sol_after >= 0)),
    CONSTRAINT ck_meme_treasury_swaps_identity_is_not_empty
        CHECK (char_length(reason) > 0)
)
"""

_INDEXES = (
    "CREATE INDEX ix_meme_treasury_swaps_requested_at ON meme_treasury_swaps (requested_at)",
    "CREATE UNIQUE INDEX ix_meme_treasury_swaps_signature "
    "ON meme_treasury_swaps (signature) WHERE signature IS NOT NULL",
)


def create_meme_treasury_swaps_table() -> None:
    op.execute(_TABLE)
    for statement in _INDEXES:
        op.execute(statement)


def grant_meme_treasury_swaps_privileges() -> None:
    """The executor appends and updates its own audit trail; the desk only reads.
    ``DELETE`` to nobody — a treasury swap is evidence, like every other meme
    audit table."""
    op.execute(f"GRANT SELECT ON {MEME_TREASURY_SWAPS_TABLE} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {MEME_TREASURY_SWAPS_TABLE} TO {WORKER_ROLE}")


def drop_meme_treasury_swaps_table() -> None:
    op.execute(f"DROP TABLE IF EXISTS {MEME_TREASURY_SWAPS_TABLE}")


def refuse_a_downgrade_that_would_lose_a_treasury_swap() -> None:
    """§17.7: a treasury swap is real money moved (or refused) on the owner's
    behalf — count, name, stop, exactly as ``meme_wallet_trades`` (``0027``)."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "
        "SELECT count(*) INTO offenders FROM meme_treasury_swaps; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_treasury_swaps rows exist - "
        "each is a real (or refused) USDC->SOL treasury attempt; dropping them loses the "
        "only record of what the executor did with the owner''s capital', "
        "HINT = 'COPY (SELECT * FROM meme_treasury_swaps) TO ... before reversing'; "
        "END IF; END $$;"
    )
