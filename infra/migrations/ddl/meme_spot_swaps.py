"""Schema piece of ``0056_meme_spot_swaps`` (T4.73): two nullable columns on
``meme_treasury_swaps`` naming the mint pair of a generic spot swap.

``0051``'s columns (``usdc_in``, ``sol_out_quoted``, ``sol_out_filled``,
``wallet_sol_before``/``after``) are plain ``numeric`` — nothing in the
table's CHECK constraints names USDC or SOL by value, only by column label
(``docs/RISK_ENGINE_MEME.md`` §16, ``infra/migrations/ddl/
meme_treasury_swaps.py``). A row for any other pair can therefore reuse those
same numeric columns (input amount in ``usdc_in``, quoted/filled output in
``sol_out_quoted``/``sol_out_filled``) with ``reason`` naming the pair
(``"spot_swap:SOL->WIF"``) — but leaving the pair to free text in ``reason``
alone would make every reader parse a string to know what moved. These two
columns are the minimal, additive fix: ``NULL`` for every existing (and every
future USDC->SOL treasury) row, and the mint pair for a row
``infra/scripts/meme_spot_swap.py`` writes.
"""

from __future__ import annotations

from alembic import op

__all__ = [
    "add_spot_swap_mint_columns",
    "drop_spot_swap_mint_columns",
    "refuse_a_downgrade_that_would_lose_a_spot_swap_mint_pair",
]

_TABLE = "meme_treasury_swaps"
_COLUMNS: tuple[str, ...] = ("input_mint", "output_mint")


def add_spot_swap_mint_columns() -> None:
    """Two nullable ``text`` columns — a base58 mint address, or ``NULL`` for
    every row written before this revision (the USDC->SOL treasury never sets
    them; T4.73's script always does, for both columns together)."""
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {column} text")
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT ck_meme_treasury_swaps_mint_pair_is_named "
        f"CHECK (({_COLUMNS[0]} IS NULL) = ({_COLUMNS[1]} IS NULL))"
    )


def drop_spot_swap_mint_columns() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS ck_meme_treasury_swaps_mint_pair_is_named"
    )
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS {column}")


def refuse_a_downgrade_that_would_lose_a_spot_swap_mint_pair() -> None:
    """§17.7: a spot swap row without its mint pair is just a pair of numbers
    with no way to say what they were of — dropping the columns while any row
    carries one loses that fact for good."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {_TABLE} WHERE input_mint IS NOT NULL; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_treasury_swaps rows carry a "
        "spot swap mint pair - dropping the columns loses which mints a real (or refused) "
        "swap moved', "
        f"HINT = 'COPY (SELECT id, input_mint, output_mint FROM {_TABLE} "
        "WHERE input_mint IS NOT NULL) TO ... before reversing'; "
        "END IF; END $$;"
    )
