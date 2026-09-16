"""``0042_meme_executable_mcap`` — ``mcap_executable_sol`` beside the
theoretical market cap on both feature series (T4.27).

**The fact that motivated it** (VPS, 3 days to 16/09/2026,
``infra/scripts/sql/research/2026-09-16-t427-picos-sao-mayhem.sql``): every
one of the 95 "peaks" of ``mcap_sol`` above 500 SOL was a Mayhem coin, 76 of
them with less than 20 % of the curve sold. KAT's ``virtual_sol_reserves``
went 23,9 → 1 977 SOL in 60 s with 5 holders — the agent pushed the virtual
reserve (``set_mayhem_virtual_params``); nobody paid SOL in. ``mcap_sol``
(marginal price × supply, ``T4-MEME-RADAR.md`` §4) is theoretical by
definition and, on a Mayhem coin, reads the agent's virtual SOL as if it were
demand.

**One nullable column on each series** — ``meme_features_1m`` and
``meme_features_15s`` — ``mcap_executable_sol numeric(28, 10)``: ``mcap_sol``
capped at the photo's ``real_sol_reserves`` (the SOL actually in the curve,
all that could ever leave it) for a Mayhem coin, equal to ``mcap_sol`` for a
standard coin (``hunter_indicators.meme.executable``). Not a price: a ceiling
on what every holder together could extract. One CHECK per series: the
executable value never exceeds the theoretical one and never exists without
it; ``NULL`` on every row folded before this revision (the ``line_points IS
NULL`` argument of ``0026``: an old row claims nothing it did not compute).
The theoretical column keeps its name; its label ("theoretical, and on a
Mayhem coin the agent's virtual SOL") lives on the model's docstring and in
``docs/RISK_ENGINE_MEME.md`` §6 — no ``COMMENT ON``, which ``alembic check``
would have to see mirrored on the model.

**Upgrade guard: none, and that is an assertion** — nullable columns, no
backfill, no seed. **The downgrade refuses** while a row carries an executable
cap: dropping it would leave the Mayhem peaks looking like price again, which
is the evidence this revision exists to label (§17.7).
"""

from __future__ import annotations

from alembic import op

COLUMN_0042 = "mcap_executable_sol"
FEATURE_SERIES_0042: tuple[str, ...] = ("meme_features_1m", "meme_features_15s")
CHECK_0042 = "executable_mcap_within_theoretical"
"""Short enough to survive Postgres 63-character identifier limit with the table prefix."""
_PREDICATE = f"{COLUMN_0042} IS NULL OR (mcap_sol IS NOT NULL AND {COLUMN_0042} <= mcap_sol)"


def _check_name(table: str) -> str:
    return f"ck_{table}_{CHECK_0042}"


def add_executable_mcap_columns() -> None:
    """One nullable column and one CHECK per series; no backfill."""
    for table in FEATURE_SERIES_0042:
        op.execute(f"ALTER TABLE {table} ADD COLUMN {COLUMN_0042} numeric(28, 10)")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {_check_name(table)} CHECK ({_PREDICATE})")


def drop_executable_mcap_columns() -> None:
    for table in reversed(FEATURE_SERIES_0042):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {_check_name(table)}")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {COLUMN_0042}")


def refuse_a_downgrade_that_would_unlabel_a_mayhem_peak() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table in FEATURE_SERIES_0042:
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} WHERE {COLUMN_0042} IS NOT NULL; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows carry an executable "
            f"market cap - dropping it would make the Mayhem peaks read as price again', "
            f"HINT = 'COPY (SELECT * FROM {table} WHERE {COLUMN_0042} IS NOT NULL) TO ... "
            f"before reversing'; "
            f"END IF; END $$;"
        )
