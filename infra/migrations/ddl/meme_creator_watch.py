"""``0036_meme_creator_watch`` — the creator's sale, seen on the chain (T4.2h).

Three columns on ``meme_paper_bets``: ``creator_sold_seen_at`` (the instant of the
reading that saw the creator's token balance fall), ``creator_sold_fraction``
(sold ÷ previous balance, a fraction in [0, 1]) and ``creator_balance_reason``
(``creator_ata_missing`` when the creator holds no token account — unmeasured,
never "did not sell"). ``services/meme-worker/hunter_meme_worker/creator_watch.py``
writes them every 15 s; ``lab_repo_bets`` reads the first as
``creator_net_seller = true`` so ``creator_dump`` closes on the next photo.

The downgrade refuses while any bet carries ``creator_sold_seen_at`` — the
latency between the creator's sale and the exit is the evidence this task
exists to measure (§17.7).
"""

from __future__ import annotations

from alembic import op

_ADD = (
    "ALTER TABLE meme_paper_bets "
    "ADD COLUMN creator_sold_seen_at timestamptz, "
    "ADD COLUMN creator_sold_fraction numeric(9, 6), "
    "ADD COLUMN creator_balance_reason text"
)
_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_meme_paper_bets_creator_sold_fraction_is_a_fraction",
        "creator_sold_fraction IS NULL OR (creator_sold_fraction > 0 AND creator_sold_fraction <= 1)",
    ),
    (
        "ck_meme_paper_bets_a_creator_sale_has_its_fraction",
        "(creator_sold_seen_at IS NULL) = (creator_sold_fraction IS NULL)",
    ),
    (
        "ck_meme_paper_bets_creator_balance_reason_is_a_known_label",
        "creator_balance_reason IS NULL OR creator_balance_reason IN ('creator_ata_missing')",
    ),
)
_DROP = (
    "ALTER TABLE meme_paper_bets "
    "DROP COLUMN creator_sold_seen_at, DROP COLUMN creator_sold_fraction, "
    "DROP COLUMN creator_balance_reason"
)


def add_creator_watch_columns() -> None:
    op.execute(_ADD)
    for name, predicate in _CHECKS:
        op.execute(f"ALTER TABLE meme_paper_bets ADD CONSTRAINT {name} CHECK ({predicate})")


def drop_creator_watch_columns() -> None:
    for name, _predicate in _CHECKS:
        op.execute(f"ALTER TABLE meme_paper_bets DROP CONSTRAINT IF EXISTS {name}")
    op.execute(_DROP)


def refuse_a_downgrade_that_would_lose_a_creator_sale() -> None:
    """§17.7: count, name, stop."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "
        "SELECT count(*) INTO offenders FROM meme_paper_bets WHERE creator_sold_seen_at IS NOT NULL; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_paper_bets rows carry a creator sale "
        "seen on the chain - the columns cannot be dropped under them', "
        "HINT = 'COPY (SELECT id, mint, creator_sold_seen_at, creator_sold_fraction FROM "
        "meme_paper_bets WHERE creator_sold_seen_at IS NOT NULL) TO ... before reversing'; "
        "END IF; END $$;"
    )
