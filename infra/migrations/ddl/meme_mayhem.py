"""``0025_meme_mayhem_denominator`` — the third provenance of the denominator.

T4.2e read the Mayhem program's per-coin account (``MayhemState``) and settled
what T4.2d had to leave unknown: a Mayhem curve's initial real token reserve
**is** the ``/global-params`` record's, for a Mayhem curve as for any other —
what pushes its reserve above the initial is the agent's own billion, minted
beside the curve's supply and sold *net* into it (``docs/PUMPFUN-ONCHAIN.md``
§3.5; the fixture ``2sduGq…`` holds 822 644 036,902123 = 793 100 000 +
29 544 036,902123, the agent's net sells to the subunit). So
``progress_denominator_source`` gains ``mayhem_state``: the record's initial,
written only after the coin's four accounts (curve, ``MayhemState``, vault,
mint) reconciled on chain in the same finalized slot.

One CHECK widened, nothing else: no column, no table, no view, no trigger.
The widened constraint is added ``NOT VALID`` and then ``VALIDATE``d — every
row of today already satisfies it (a superset of the ``0024`` list), and
``VALIDATE CONSTRAINT`` takes ``SHARE UPDATE EXCLUSIVE``, which lets the
collector's upserts through while the scan runs (``ADD CONSTRAINT`` without
``NOT VALID`` would hold ``SHARE ROW EXCLUSIVE`` for the whole scan).

**The downgrade refuses** while any row carries a ``mayhem_state`` denominator:
narrowing the CHECK back would make that row unrepresentable, and the on-chain
reconciliation that produced it is not something the ``0024`` schema can hold.
"""

from __future__ import annotations

from alembic import op

DENOMINATOR_SOURCES_0025: tuple[str, ...] = ("observed_virgin", "global_params", "mayhem_state")
"""The closed list this revision freezes — ``0024``'s two plus ``mayhem_state``."""

DENOMINATOR_SOURCES_0024: tuple[str, ...] = ("observed_virgin", "global_params")
"""``ddl/meme_graduation.py``'s list, copied and frozen: the downgrade must
restore what ``0024`` shipped, not what a later edit of that module says."""

CHECK_NAME = "ck_meme_tokens_denominator_source_is_a_known_label"


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_check(values: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE meme_tokens DROP CONSTRAINT IF EXISTS {CHECK_NAME}")
    op.execute(
        f"ALTER TABLE meme_tokens ADD CONSTRAINT {CHECK_NAME} "
        "CHECK (progress_denominator_source IS NULL OR progress_denominator_source IN "
        f"({_labels(values)})) NOT VALID"
    )
    op.execute(f"ALTER TABLE meme_tokens VALIDATE CONSTRAINT {CHECK_NAME}")


def widen_denominator_source() -> None:
    """``0024``'s two labels plus ``mayhem_state``."""
    _replace_check(DENOMINATOR_SOURCES_0025)


def narrow_denominator_source() -> None:
    """Back to ``0024``'s list — only after the guard below counted zero."""
    _replace_check(DENOMINATOR_SOURCES_0024)


def refuse_a_downgrade_that_would_lose_a_mayhem_denominator() -> None:
    """§17.7: count, name, stop. A ``mayhem_state`` denominator is the result of
    an on-chain reconciliation the ``0024`` schema cannot represent."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "
        "SELECT count(*) INTO offenders FROM meme_tokens "
        "WHERE progress_denominator_source = 'mayhem_state'; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_tokens rows carry a mayhem_state "
        "denominator - the 0024 CHECK cannot hold that label', "
        "HINT = 'COPY (SELECT * FROM meme_tokens WHERE progress_denominator_source = "
        "''mayhem_state'') TO ... before reversing'; "
        "END IF; END $$;"
    )
