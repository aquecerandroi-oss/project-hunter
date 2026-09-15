"""``0036_meme_creator_watch`` / ``0038_meme_creator_watch_live`` — the creator's
sale, seen on the chain (T4.2h, T4.2h-b).

Three columns, on ``meme_paper_bets`` (``0036``) and, with exactly the same
names, meaning and CHECKs, on ``meme_live_positions`` (``0038``):
``creator_sold_seen_at`` (the instant of the reading that saw the creator's
token balance fall), ``creator_sold_fraction`` (sold ÷ previous balance, a
fraction in (0, 1]) and ``creator_balance_reason`` (``creator_ata_missing``
when the creator holds no token account — unmeasured, never "did not sell").
``services/meme-worker/hunter_meme_worker/creator_watch.py`` writes both every
15 s; ``lab_repo_bets`` reads the paper one as ``creator_net_seller = true`` so
``creator_dump`` closes on the next photo, and the executor's exit loop
(``hunter_meme_executor.exits``) reads the live one on its 5 s tick.

**Same names on purpose:** one watch loop writes both, one query measures
``exit_at − creator_sold_seen_at`` on either side, and an operator who learned
the paper column does not have to learn a second word for the real position.

The downgrade refuses while any row carries ``creator_sold_seen_at`` — the
latency between the creator's sale and the exit is the evidence this task
exists to measure (§17.7).
"""

from __future__ import annotations

from alembic import op

PAPER_TABLE = "meme_paper_bets"
LIVE_TABLE = "meme_live_positions"
BALANCE_REASONS: tuple[str, ...] = ("creator_ata_missing",)


def _add(table: str) -> str:
    return (
        f"ALTER TABLE {table} "
        "ADD COLUMN creator_sold_seen_at timestamptz, "
        "ADD COLUMN creator_sold_fraction numeric(9, 6), "
        "ADD COLUMN creator_balance_reason text"
    )


def _drop(table: str) -> str:
    return (
        f"ALTER TABLE {table} "
        "DROP COLUMN creator_sold_seen_at, DROP COLUMN creator_sold_fraction, "
        "DROP COLUMN creator_balance_reason"
    )


def _checks(table: str) -> tuple[tuple[str, str], ...]:
    labels = ", ".join(f"'{reason}'" for reason in BALANCE_REASONS)
    return (
        (
            f"ck_{table}_creator_sold_fraction_is_a_fraction",
            "creator_sold_fraction IS NULL "
            "OR (creator_sold_fraction > 0 AND creator_sold_fraction <= 1)",
        ),
        (
            f"ck_{table}_a_creator_sale_has_its_fraction",
            "(creator_sold_seen_at IS NULL) = (creator_sold_fraction IS NULL)",
        ),
        (
            f"ck_{table}_creator_balance_reason_is_a_known_label",
            f"creator_balance_reason IS NULL OR creator_balance_reason IN ({labels})",
        ),
    )


def _add_columns(table: str) -> None:
    op.execute(_add(table))
    for name, predicate in _checks(table):
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({predicate})")


def _drop_columns(table: str) -> None:
    for name, _predicate in _checks(table):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(_drop(table))


def _refuse(table: str, noun: str) -> None:
    """§17.7: count, name, stop. ``table``/``noun`` are this module's own
    constants, never input — S608 has no user string to reach."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {table} WHERE creator_sold_seen_at IS NOT NULL; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} {noun} carry a creator sale "
        "seen on the chain - the columns cannot be dropped under them', "
        "HINT = 'COPY (SELECT id, mint, creator_sold_seen_at, creator_sold_fraction FROM "
        f"{table} WHERE creator_sold_seen_at IS NOT NULL) TO ... before reversing'; "
        "END IF; END $$;"
    )


def add_creator_watch_columns() -> None:
    _add_columns(PAPER_TABLE)


def drop_creator_watch_columns() -> None:
    _drop_columns(PAPER_TABLE)


def refuse_a_downgrade_that_would_lose_a_creator_sale() -> None:
    _refuse(PAPER_TABLE, "rows")


def add_creator_watch_live_columns() -> None:
    """T4.2h-b: the same three columns on the **real** position.

    No grant is issued: ``hunter_worker`` already holds table-wide
    ``SELECT, INSERT, UPDATE`` on ``meme_live_positions`` (``0028``), so the
    watch loop can write them, and ``hunter_app``'s column grant stays the two
    ``sell_requested_*`` columns — the API may still ask for a sale and record
    nothing (``ddl/meme_live.py``).
    """
    _add_columns(LIVE_TABLE)


def drop_creator_watch_live_columns() -> None:
    _drop_columns(LIVE_TABLE)


def refuse_a_downgrade_that_would_lose_a_live_creator_sale() -> None:
    _refuse(LIVE_TABLE, "positions")
