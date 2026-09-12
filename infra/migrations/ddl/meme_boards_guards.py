"""What ``0023_meme_boards_trades`` changes on the ``0021`` tables, and its guard.

Split from ``ddl/meme_boards.py`` for the 350-line budget: the *new* tables are
there, the *edits* to existing ones and the refusal to lose their rows are here.

**``meme_features_1m`` gains the columns the boards and the tape can fill**
(``docs/plans/T4-FEATURES.md`` F-A3/F-A4/F-A5, F-B3, F-C1/F-C3), each with a
reason column and the biconditional CHECK of ``0021``: ``holders``,
``dev_share``, ``snipers`` (from the board or the risk read, with the instant
and the source they were read at), ``buys_1m``/``sells_1m``/``net_sol_flow_1m``
/``curve_volume_1m_sol`` (one ``tape_reason`` for the four, because they come
from one source and are absent together) and ``creator_net_seller`` (net SOL of
the creator's sells minus buys over the tape covered so far — the EXP-M1
gate's input, distinct from ``creator_sold`` = any sell at all).

**``meme_trades.commitment`` becomes nullable.** ``0021`` wrote ``NOT NULL``
for an on-chain decoder that states finality on every read; the producer that
actually landed (``swap-api``, T4.2c) states none, and the honest row says
``NULL`` — the same word ``meme_curve_snapshots.commitment`` already uses for
the REST mirror — instead of a ``confirmed`` nobody observed.

**The downgrade refuses** while a board minute or a risk read exists, while a
feature row carries one of the new columns, or while a trade carries a ``NULL``
commitment (restoring ``NOT NULL`` would fail mid-way otherwise): count, name,
stop (§17.7). On every database of today each counts zero.
"""

from __future__ import annotations

from alembic import op

FEATURE_COLUMNS_0023: tuple[str, ...] = (
    "holders",
    "holders_reason",
    "holders_observed_at",
    "holders_source",
    "dev_share",
    "dev_share_reason",
    "snipers",
    "snipers_reason",
    "buys_1m",
    "sells_1m",
    "net_sol_flow_1m",
    "curve_volume_1m_sol",
    "tape_reason",
    "creator_net_seller",
    "creator_net_seller_reason",
)
"""Frozen: what ``0023`` adds and what its downgrade removes."""

_ADD_FEATURE_COLUMNS = (
    "ALTER TABLE meme_features_1m "
    "ADD COLUMN holders integer, "
    "ADD COLUMN holders_reason text, "
    "ADD COLUMN holders_observed_at timestamptz, "
    "ADD COLUMN holders_source text, "
    "ADD COLUMN dev_share numeric(9, 6), "
    "ADD COLUMN dev_share_reason text, "
    "ADD COLUMN snipers integer, "
    "ADD COLUMN snipers_reason text, "
    "ADD COLUMN buys_1m integer, "
    "ADD COLUMN sells_1m integer, "
    "ADD COLUMN net_sol_flow_1m numeric(28, 10), "
    "ADD COLUMN curve_volume_1m_sol numeric(28, 10), "
    "ADD COLUMN tape_reason text, "
    "ADD COLUMN creator_net_seller boolean, "
    "ADD COLUMN creator_net_seller_reason text"
)

_FEATURE_CHECKS = (
    (
        "ck_meme_features_1m_holders_is_null_with_a_reason",
        "(holders IS NULL) = (holders_reason IS NOT NULL)",
    ),
    (
        "ck_meme_features_1m_holders_name_their_reading",
        "(holders IS NULL) = (holders_observed_at IS NULL) "
        "AND (holders IS NULL) = (holders_source IS NULL)",
    ),
    (
        "ck_meme_features_1m_dev_share_is_null_with_a_reason",
        "(dev_share IS NULL) = (dev_share_reason IS NOT NULL)",
    ),
    (
        "ck_meme_features_1m_snipers_is_null_with_a_reason",
        "(snipers IS NULL) = (snipers_reason IS NOT NULL)",
    ),
    (
        "ck_meme_features_1m_tape_is_null_with_a_reason",
        "(buys_1m IS NULL) = (tape_reason IS NOT NULL) "
        "AND (buys_1m IS NULL) = (sells_1m IS NULL) "
        "AND (buys_1m IS NULL) = (net_sol_flow_1m IS NULL) "
        "AND (buys_1m IS NULL) = (curve_volume_1m_sol IS NULL)",
    ),
    (
        "ck_meme_features_1m_creator_net_seller_is_null_with_a_reason",
        "(creator_net_seller IS NULL) = (creator_net_seller_reason IS NOT NULL)",
    ),
    (
        "ck_meme_features_1m_holders_and_snipers_are_not_negative",
        "(holders IS NULL OR holders >= 0) AND (snipers IS NULL OR snipers >= 0) "
        "AND (buys_1m IS NULL OR buys_1m >= 0) AND (sells_1m IS NULL OR sells_1m >= 0)",
    ),
    (
        "ck_meme_features_1m_dev_share_is_a_fraction",
        "dev_share IS NULL OR (dev_share >= 0 AND dev_share <= 1)",
    ),
    (
        "ck_meme_features_1m_curve_volume_is_not_negative",
        "curve_volume_1m_sol IS NULL OR curve_volume_1m_sol >= 0",
    ),
)

_TRADES_COMMITMENT_CHECK = "ck_meme_trades_commitment_is_a_known_label"


_BACKFILL_REASONS_FOR_EXISTING_ROWS = (
    # Rows folded before 0023 have every new value NULL and no reason yet; the
    # CHECKs below demand a named reason next to every NULL. The names are the
    # vocabulary of ``hunter_core.db.models.meme_features``: no reader had spoken
    # for those minutes. Production (12/09/2026 07:33 BRT, 4 000+ rows in
    # ``meme_features_1m_2026_09``) refused the first CHECK without this step.
    "UPDATE meme_features_1m SET holders_reason = 'no_holders_reader' "
    "WHERE holders IS NULL AND holders_reason IS NULL",
    "UPDATE meme_features_1m SET dev_share_reason = 'no_holders_reader' "
    "WHERE dev_share IS NULL AND dev_share_reason IS NULL",
    "UPDATE meme_features_1m SET snipers_reason = 'no_holders_reader' "
    "WHERE snipers IS NULL AND snipers_reason IS NULL",
    "UPDATE meme_features_1m SET tape_reason = 'no_trade_feed' "
    "WHERE buys_1m IS NULL AND tape_reason IS NULL",
    "UPDATE meme_features_1m SET creator_net_seller_reason = 'no_trade_feed' "
    "WHERE creator_net_seller IS NULL AND creator_net_seller_reason IS NULL",
)


def add_feature_columns() -> None:
    op.execute(_ADD_FEATURE_COLUMNS)
    for statement in _BACKFILL_REASONS_FOR_EXISTING_ROWS:
        op.execute(statement)
    for name, predicate in _FEATURE_CHECKS:
        op.execute(f"ALTER TABLE meme_features_1m ADD CONSTRAINT {name} CHECK ({predicate})")


def drop_feature_columns() -> None:
    for name, _predicate in reversed(_FEATURE_CHECKS):
        op.execute(f"ALTER TABLE meme_features_1m DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE meme_features_1m "
        + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in FEATURE_COLUMNS_0023)
    )


def relax_trade_commitment() -> None:
    """``NULL`` = the producer states no finality (``swap-api``)."""
    op.execute("ALTER TABLE meme_trades ALTER COLUMN commitment DROP NOT NULL")
    op.execute(f"ALTER TABLE meme_trades DROP CONSTRAINT IF EXISTS {_TRADES_COMMITMENT_CHECK}")
    op.execute(
        f"ALTER TABLE meme_trades ADD CONSTRAINT {_TRADES_COMMITMENT_CHECK} "
        "CHECK (commitment IS NULL OR commitment IN ('confirmed', 'finalized'))"
    )


def restore_trade_commitment() -> None:
    op.execute(f"ALTER TABLE meme_trades DROP CONSTRAINT IF EXISTS {_TRADES_COMMITMENT_CHECK}")
    op.execute(
        f"ALTER TABLE meme_trades ADD CONSTRAINT {_TRADES_COMMITMENT_CHECK} "
        "CHECK (commitment IN ('confirmed', 'finalized'))"
    )
    op.execute("ALTER TABLE meme_trades ALTER COLUMN commitment SET NOT NULL")


_GUARDED: tuple[tuple[str, str, str], ...] = (
    (
        "meme_board_observations",
        "",
        "board minutes - the only record of what the site showed and for how long, "
        "and the exposure intervals M-P7 is counted against",
    ),
    (
        "meme_risk_snapshots",
        "",
        "risk reads - nobody serves the holders, dev and sniper shares a coin had at a "
        "past instant, so these rows are the only copy",
    ),
    (
        "meme_features_1m",
        "WHERE holders IS NOT NULL OR buys_1m IS NOT NULL OR creator_net_seller IS NOT NULL "
        "OR dev_share IS NOT NULL OR snipers IS NOT NULL",
        "feature rows carry the 0023 columns - dropping them would silently turn measured "
        "holders and tape numbers into absent ones",
    ),
    (
        "meme_trades",
        "WHERE commitment IS NULL",
        "trades from a producer that states no finality - restoring NOT NULL would fail "
        "or force a commitment nobody observed",
    ),
)


def refuse_a_downgrade_that_would_lose_meme_boards_rows() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, predicate, why in _GUARDED:
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
