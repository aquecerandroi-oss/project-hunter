"""``0027_meme_wallets`` — the observed wallet: Everton's **real** pump.fun trades,
read from the chain, become rows next to the paper Lab (T4.12).

Two tables and one view rewritten. **Global and RLS-free** (DATABASE.md §1.1),
the shape of ``0021``/``0022``: a public wallet's fills on an on-chain curve
belong to no organization. The system never signs anything — the collector
(``services/meme-worker/hunter_meme_worker/wallets.py``) reads
``getSignaturesForAddress`` + ``getTransaction`` for the public addresses in
``MEME_WATCH_WALLETS`` and writes what it decoded, or what it could not.

**``meme_wallet_trades``** — the ledger, one row per fill (or per signature
nothing decoded), keyed ``(signature, event_index)`` so a transaction is never
counted twice and a bundle of two fills in one transaction is never halved
(the ``meme_trades`` lesson, ``0021``). ``side`` is ``buy`` | ``sell`` |
``unknown``; ``venue`` is ``curve`` (the pump program's ``TradeEvent``) or
``pool`` (a PumpSwap swap read from the wallet's own balance deltas —
``decode`` says which path spoke). ``sol_lamports`` is the trade leg as the
chain reports it and ``fee_lamports`` every deduction on top of it (protocol,
creator, cashback, and the network fee when the wallet paid it): a buy cost
``sol + fee``, a sell netted ``sol − fee``, lamport-exact. An ``unknown`` keeps
``raw`` (bounded, and the reason by name) and no number — never an invented
fill. ``lab_context`` is written on a **buy** only: what every active rule
set's gate said, in the last closed minute before the fill, about that mint —
the answer to "would the Lab have done the same?" — with the minute's
``hype_score``/``line_reason`` beside it (T4.10a).

**``meme_wallet_positions``** — derived from the ledger and recomputed from it
(a restart changes nothing): per wallet × mint, tokens held, SOL spent, SOL
received, the FIFO cost of what is still held, realized PnL (FIFO), the mark by
the latest curve snapshot or tape (``mark_source``, or ``mark_reason`` when
neither exists), the unrealized PnL against that mark, and R with **risk =
SOL spent** (RISK_ENGINE_MEME §5). A sell with no observed buy behind it is
``unmatched_sell_tokens``: its proceeds count in ``sol_received`` and nowhere
else, because its cost was never seen.

**The scoreboard** ``meme_lab_scoreboard_v1`` gains one row per observed
wallet per Brasília day of first buy, named ``wallet:<8 chars>`` with ``kind =
'real_observed'`` and a deterministic ``rule_set_id`` (``md5``), so the diary
and the desk read real and paper on the same board. ``pnl_usd`` is ``NULL``
and ``unpriced_usd`` counts every closed position: no on-chain fill carries an
observed SOL/USD quote, and the board never prices a day by a rate nobody saw.
``rugs`` here is a closed position that realized a loss of 90 % or more of its
SOL spent — a definition, declared, not a guess.

**Who writes what.** ``hunter_worker``: ``SELECT``/``INSERT``/``UPDATE`` on
both (the ledger gains ``lab_context`` after the insert; the positions are
upserted). ``hunter_app``: ``SELECT``. ``DELETE`` to nobody — a real trade is
evidence. **The downgrade refuses** while ``meme_wallet_trades`` holds a row.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_lab_views import MEME_LAB_SCOREBOARD_VIEW, recreate_scoreboard_0022
from ddl.meme_lines import LINE_REASONS_0026
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_WALLET_TABLES_0027: tuple[str, ...] = ("meme_wallet_trades", "meme_wallet_positions")
"""Creation order; the positions carry no foreign key into the ledger (they are
recomputed from it, and a ledger row may name a mint the token table pruned)."""

MEME_WALLET_APP_READ_ONLY_TABLES: tuple[str, ...] = MEME_WALLET_TABLES_0027
MEME_WALLET_WORKER_UPSERT_TABLES: tuple[str, ...] = MEME_WALLET_TABLES_0027

WALLET_TRADE_SIDES_0027: tuple[str, ...] = ("buy", "sell", "unknown")
WALLET_TRADE_VENUES_0027: tuple[str, ...] = ("curve", "pool")
WALLET_TRADE_DECODES_0027: tuple[str, ...] = ("trade_event", "balance_delta", "none")
WALLET_POSITION_STATUSES_0027: tuple[str, ...] = ("open", "closed")
WALLET_MARK_SOURCES_0027: tuple[str, ...] = ("curve_snapshot", "tape")


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_TRADES = f"""
CREATE TABLE meme_wallet_trades (
    wallet text NOT NULL,
    signature text NOT NULL,
    event_index smallint NOT NULL DEFAULT 0,
    slot bigint NOT NULL,
    block_time timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    mint text,
    side text NOT NULL,
    venue text,
    sol_lamports bigint,
    token_amount numeric(28, 10),
    fee_lamports bigint,
    decode text NOT NULL,
    raw jsonb,
    lab_context jsonb,
    hype_score numeric(9, 6),
    line_reason text,
    CONSTRAINT pk_meme_wallet_trades PRIMARY KEY (signature, event_index),
    CONSTRAINT ck_meme_wallet_trades_side_is_a_known_label
        CHECK (side IN ({_labels(WALLET_TRADE_SIDES_0027)})),
    CONSTRAINT ck_meme_wallet_trades_venue_is_a_known_label
        CHECK (venue IS NULL OR venue IN ({_labels(WALLET_TRADE_VENUES_0027)})),
    CONSTRAINT ck_meme_wallet_trades_decode_is_a_known_label
        CHECK (decode IN ({_labels(WALLET_TRADE_DECODES_0027)})),
    CONSTRAINT ck_meme_wallet_trades_an_unknown_is_what_nothing_decoded
        CHECK ((side = 'unknown') = (decode = 'none')),
    CONSTRAINT ck_meme_wallet_trades_an_unknown_keeps_the_raw
        CHECK (side <> 'unknown' OR raw IS NOT NULL),
    CONSTRAINT ck_meme_wallet_trades_a_fill_carries_its_numbers
        CHECK (side = 'unknown' OR (mint IS NOT NULL AND venue IS NOT NULL
               AND block_time IS NOT NULL AND sol_lamports IS NOT NULL
               AND fee_lamports IS NOT NULL AND token_amount IS NOT NULL)),
    CONSTRAINT ck_meme_wallet_trades_chain_counters_are_not_negative
        CHECK (slot >= 0 AND event_index >= 0
               AND (sol_lamports IS NULL OR sol_lamports >= 0)
               AND (fee_lamports IS NULL OR fee_lamports >= 0)
               AND (token_amount IS NULL OR token_amount >= 0)),
    CONSTRAINT ck_meme_wallet_trades_lab_context_belongs_to_a_buy
        CHECK (lab_context IS NULL OR side = 'buy'),
    CONSTRAINT ck_meme_wallet_trades_hype_score_is_a_fraction
        CHECK (hype_score IS NULL OR (hype_score >= 0 AND hype_score <= 1)),
    CONSTRAINT ck_meme_wallet_trades_line_reason_is_a_known_label
        CHECK (line_reason IS NULL OR line_reason IN ({_labels(LINE_REASONS_0026)})),
    CONSTRAINT ck_meme_wallet_trades_identity_is_not_empty
        CHECK (char_length(wallet) > 0 AND char_length(signature) > 0)
)
"""

_POSITIONS = f"""
CREATE TABLE meme_wallet_positions (
    wallet text NOT NULL,
    mint text NOT NULL,
    status text NOT NULL,
    tokens_held numeric(28, 10) NOT NULL,
    sol_spent numeric(28, 10) NOT NULL,
    sol_received numeric(28, 10) NOT NULL,
    open_cost_sol numeric(28, 10) NOT NULL,
    avg_cost_sol_per_token numeric(38, 18),
    realized_pnl_sol numeric(28, 10) NOT NULL,
    unmatched_sell_tokens numeric(28, 10) NOT NULL DEFAULT 0,
    buys integer NOT NULL,
    sells integer NOT NULL,
    first_buy_at timestamptz,
    last_trade_at timestamptz NOT NULL,
    mark_sol numeric(28, 10),
    mark_at timestamptz,
    mark_source text,
    mark_reason text,
    unrealized_pnl_sol numeric(28, 10),
    r_multiple numeric(28, 10),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_wallet_positions PRIMARY KEY (wallet, mint),
    CONSTRAINT ck_meme_wallet_positions_status_is_a_known_label
        CHECK (status IN ({_labels(WALLET_POSITION_STATUSES_0027)})),
    CONSTRAINT ck_meme_wallet_positions_a_closed_position_holds_nothing
        CHECK ((status = 'closed') = (tokens_held = 0)),
    CONSTRAINT ck_meme_wallet_positions_a_mark_names_its_source_and_when
        CHECK ((mark_sol IS NULL) = (mark_at IS NULL)
               AND (mark_sol IS NULL) = (mark_source IS NULL)
               AND (mark_sol IS NULL) = (mark_reason IS NOT NULL)
               AND (mark_sol IS NULL) = (unrealized_pnl_sol IS NULL)),
    CONSTRAINT ck_meme_wallet_positions_mark_source_is_a_known_label
        CHECK (mark_source IS NULL OR mark_source IN ({_labels(WALLET_MARK_SOURCES_0027)})),
    CONSTRAINT ck_meme_wallet_positions_amounts_are_not_negative
        CHECK (tokens_held >= 0 AND sol_spent >= 0 AND sol_received >= 0
               AND open_cost_sol >= 0 AND unmatched_sell_tokens >= 0
               AND buys >= 0 AND sells >= 0),
    CONSTRAINT ck_meme_wallet_positions_a_buy_says_when
        CHECK ((buys = 0) = (first_buy_at IS NULL)),
    CONSTRAINT ck_meme_wallet_positions_identity_is_not_empty
        CHECK (char_length(wallet) > 0 AND char_length(mint) > 0)
)
"""

_INDEXES = (
    "CREATE INDEX ix_meme_wallet_trades_wallet_block_time "
    "ON meme_wallet_trades (wallet, block_time)",
    "CREATE INDEX ix_meme_wallet_trades_wallet_mint ON meme_wallet_trades (wallet, mint)",
    "CREATE INDEX ix_meme_wallet_trades_mint_block_time ON meme_wallet_trades (mint, block_time)",
    "CREATE INDEX ix_meme_wallet_positions_status_last_trade_at "
    "ON meme_wallet_positions (status, last_trade_at)",
)

_SCOREBOARD_0027 = f"""
CREATE VIEW {MEME_LAB_SCOREBOARD_VIEW} AS
WITH bets AS (
    SELECT b.rule_set_id,
           (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt,
           b.id, b.status, b.pnl_sol, b.r_multiple, b.exit_at, b.sol_usd_at_exit,
           b.exit ->> 'reason' AS exit_reason
    FROM meme_paper_bets b
), curve AS (
    SELECT rule_set_id, day_brt, exit_at, id,
           sum(pnl_sol) OVER (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id) AS cum_pnl
    FROM bets WHERE status = 'closed'
), excursions AS (
    SELECT rule_set_id, day_brt,
           cum_pnl - GREATEST(0, max(cum_pnl) OVER
               (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id)) AS drawdown
    FROM curve
), drawdowns AS (
    SELECT rule_set_id, day_brt, -min(drawdown) AS max_drawdown_sol
    FROM excursions GROUP BY rule_set_id, day_brt
), positions AS (
    SELECT p.wallet, p.mint, p.status, p.realized_pnl_sol, p.r_multiple, p.last_trade_at,
           p.sol_spent,
           (p.first_buy_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt
    FROM meme_wallet_positions p WHERE p.first_buy_at IS NOT NULL
), wallet_curve AS (
    SELECT wallet, day_brt, last_trade_at, mint,
           sum(realized_pnl_sol) OVER
               (PARTITION BY wallet, day_brt ORDER BY last_trade_at, mint) AS cum_pnl
    FROM positions WHERE status = 'closed'
), wallet_excursions AS (
    SELECT wallet, day_brt,
           cum_pnl - GREATEST(0, max(cum_pnl) OVER
               (PARTITION BY wallet, day_brt ORDER BY last_trade_at, mint)) AS drawdown
    FROM wallet_curve
), wallet_drawdowns AS (
    SELECT wallet, day_brt, -min(drawdown) AS max_drawdown_sol
    FROM wallet_excursions GROUP BY wallet, day_brt
)
SELECT r.id AS rule_set_id, r.name, r.version, r.kind, r.exp_ref, r.status AS rule_set_status,
       b.day_brt,
       count(*) AS bets,
       count(*) FILTER (WHERE b.status = 'closed') AS closed,
       count(*) FILTER (WHERE b.status = 'closed' AND b.pnl_sol > 0) AS wins,
       sum(b.pnl_sol) FILTER (WHERE b.status = 'closed') AS pnl_sol,
       sum(b.pnl_sol * b.sol_usd_at_exit)
           FILTER (WHERE b.status = 'closed' AND b.sol_usd_at_exit IS NOT NULL) AS pnl_usd,
       count(*) FILTER (WHERE b.status = 'closed' AND b.sol_usd_at_exit IS NULL) AS unpriced_usd,
       sum(b.r_multiple) FILTER (WHERE b.status = 'closed') AS r_sum,
       d.max_drawdown_sol,
       count(*) FILTER (WHERE b.exit_reason = 'rug_no_snapshot') AS rugs
FROM bets b
JOIN meme_rule_sets r ON r.id = b.rule_set_id
LEFT JOIN drawdowns d ON d.rule_set_id = b.rule_set_id AND d.day_brt = b.day_brt
GROUP BY r.id, r.name, r.version, r.kind, r.exp_ref, r.status, b.day_brt, d.max_drawdown_sol
UNION ALL
SELECT md5('wallet:' || p.wallet)::uuid AS rule_set_id,
       'wallet:' || left(p.wallet, 8) AS name, '1' AS version, 'real_observed' AS kind,
       NULL::text AS exp_ref, 'active' AS rule_set_status,
       p.day_brt,
       count(*) AS bets,
       count(*) FILTER (WHERE p.status = 'closed') AS closed,
       count(*) FILTER (WHERE p.status = 'closed' AND p.realized_pnl_sol > 0) AS wins,
       sum(p.realized_pnl_sol) FILTER (WHERE p.status = 'closed') AS pnl_sol,
       NULL::numeric AS pnl_usd,
       count(*) FILTER (WHERE p.status = 'closed') AS unpriced_usd,
       sum(p.r_multiple) FILTER (WHERE p.status = 'closed') AS r_sum,
       w.max_drawdown_sol,
       count(*) FILTER (WHERE p.status = 'closed' AND p.sol_spent > 0
                        AND p.realized_pnl_sol <= -0.9 * p.sol_spent) AS rugs
FROM positions p
LEFT JOIN wallet_drawdowns w ON w.wallet = p.wallet AND w.day_brt = p.day_brt
GROUP BY p.wallet, p.day_brt, w.max_drawdown_sol
"""  # noqa: S608 - the only interpolation is the frozen view name
"""The ``0022`` board, byte for byte, plus one block per observed wallet. The
paper rows keep their ``rule_set_id``; a wallet's id is ``md5('wallet:' ||
wallet)`` so two databases agree on it without a rule-set row."""


def create_meme_wallet_tables() -> None:
    """The ledger, the derived positions and the four indexes."""
    op.execute(_TRADES)
    op.execute(_POSITIONS)
    for statement in _INDEXES:
        op.execute(statement)


def grant_meme_wallet_privileges() -> None:
    """Read for the API; read, append and update for the loop; ``DELETE`` to nobody."""
    for table in MEME_WALLET_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_WALLET_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")


def replace_scoreboard_with_observed_wallets() -> None:
    """Drop the ``0022`` view and create the ``UNION ALL`` one under the same name
    and the same grants (a view's grants do not survive a ``DROP``)."""
    op.execute(f"DROP VIEW IF EXISTS {MEME_LAB_SCOREBOARD_VIEW}")
    op.execute(_SCOREBOARD_0027)
    op.execute(f"GRANT SELECT ON {MEME_LAB_SCOREBOARD_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def restore_scoreboard_0022() -> None:
    op.execute(f"DROP VIEW IF EXISTS {MEME_LAB_SCOREBOARD_VIEW}")
    recreate_scoreboard_0022()


def drop_meme_wallet_tables() -> None:
    for table in reversed(MEME_WALLET_TABLES_0027):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def refuse_a_downgrade_that_would_lose_an_observed_trade() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop.
    Only the ledger is guarded: the positions are recomputed from it."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "
        "SELECT count(*) INTO offenders FROM meme_wallet_trades; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_wallet_trades rows exist - "
        "real fills observed on the chain for a watched wallet; dropping them loses the "
        "only record of what the operator actually did', "
        "HINT = 'COPY (SELECT * FROM meme_wallet_trades) TO ... before reversing'; "
        "END IF; END $$;"
    )
