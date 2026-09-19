"""``0057_spot_desk`` — the ``spot/1`` desk: a Lab signal (Binance) executed on
Solana through Jupiter by the robot's wallet (T4.74-1, design
``docs/design/spot1-lab-solana.md`` §2/§5, DATABASE.md §63).

**Three tables, grants by subtraction, a 50-row seed.** Global and RLS-free
(DATABASE.md §1.1), the shape of ``0028_meme_live``: an order signed against a
Jupiter route belongs to no organization. No enum, no partition, no view.

- ``spot_desk_markets``: the map ``binance_symbol -> solana_mint`` of R63
  §2a, seeded from ``ddl/spot_desk_seed.py`` (52 executable markets minus
  ``SOLUSDT`` and ``ENAUSDT``). Keyed by the Binance symbol — the ``JOIN`` the
  signal query makes (§2) and the line a position names. **No FK to
  ``markets``**: the seed has to plant on an empty database. ``enabled`` at
  seed = ``tier <> 'C' AND round trip <= 0,4 %``; afterwards only the audited
  script ``infra/scripts/spot_desk_markets.py`` moves it. ``decimals`` is
  ``NULL`` until the executor reads the mint once and writes it back.
- ``spot_orders``: ``meme_live_orders``' shape (same status labels, same
  "a refusal names its reason" / "a confirmed order carries its fill and its
  signature" / "a sent order has a signature" CHECKs, ``attempt >= 1``, unique
  ``client_order_id``, one buy per **signal**, one order per signature) plus
  ``desk``, ``signal_id -> agent_signals``, ``position_id -> spot_positions``
  (a sell names the position it closes, a buy never does), ``market_symbol
  -> spot_desk_markets``, ``mint`` and ``quote`` (the Jupiter quote that
  produced the transaction). ``fill`` is the **real deltas** read from the
  chain after ``confirmed`` — never the quote.
- ``spot_positions``: ``meme_live_positions``' shape with ``signal_id``
  unique, ``market_symbol``, ``mint``, ``ata_rent_lamports`` (the 0,00204 SOL
  a sell through Jupiter leaves in the token ATA — kept **out** of
  ``pnl_sol``), ``mark_source IN ('jupiter_quote')`` and
  ``initial_risk_sol = r_unit_sol`` (the R of the row is the signal's R).

**Who writes what** (the ``0028`` shape). ``hunter_worker`` (the executor):
``SELECT``/``INSERT``/``UPDATE`` on the three. ``hunter_app``: ``SELECT`` on
the three plus ``UPDATE (sell_requested_at, sell_requested_by)`` on the
positions — the API may ask for a sale, never record one. ``DELETE`` to
nobody. **The downgrade refuses** (§17.7) while ``spot_orders`` holds a row
with ``tx_signature`` — a real transaction would lose its ledger.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from ddl.spot_desk_seed import SEED_WRITER_0057, seed_rows
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

SPOT_DESK_TABLES_0057: tuple[str, ...] = ("spot_desk_markets", "spot_orders", "spot_positions")
"""Creation order; the ``spot_orders.position_id`` FK closes the cycle by ``ALTER``."""

SPOT_DESK_APP_READ_ONLY_TABLES: tuple[str, ...] = ("spot_desk_markets", "spot_orders")
SPOT_DESK_APP_SELL_REQUEST_TABLES: tuple[str, ...] = ("spot_positions",)
"""``SELECT`` plus ``UPDATE`` of :data:`SPOT_DESK_SELL_REQUEST_COLUMNS` only."""

SPOT_DESK_SELL_REQUEST_COLUMNS: tuple[str, ...] = ("sell_requested_at", "sell_requested_by")
SPOT_DESK_WORKER_UPSERT_TABLES: tuple[str, ...] = SPOT_DESK_TABLES_0057

SPOT_MARKET_KINDS_0057: tuple[str, ...] = ("nativo", "ponte", "representacao")
SPOT_MARKET_TIERS_0057: tuple[str, ...] = ("A", "B", "C")
SPOT_ORDER_SIDES_0057: tuple[str, ...] = ("buy", "sell")
SPOT_ORDER_STATUSES_0057: tuple[str, ...] = (
    "admitted",
    "refused",
    "simulated",
    "submitted_unconfirmed",
    "confirmed",
    "failed",
)
SPOT_POSITION_STATUSES_0057: tuple[str, ...] = ("open", "closed")
SPOT_MARK_SOURCES_0057: tuple[str, ...] = ("jupiter_quote",)
SPOT_DESK_LABEL_0057 = "spot/1"

_POSITION_FK = "fk_spot_orders_position_id_spot_positions"


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_MARKETS = f"""
CREATE TABLE spot_desk_markets (
    binance_symbol text NOT NULL,
    base text NOT NULL,
    mint text NOT NULL,
    units_per_binance_unit numeric(28, 10) NOT NULL DEFAULT 1,
    kind text NOT NULL,
    tier text NOT NULL,
    liquidity_usd_at_seed numeric(28, 10) NOT NULL,
    round_trip_cost_pct_at_seed numeric(9, 6) NOT NULL,
    decimals smallint,
    enabled boolean NOT NULL DEFAULT false,
    note text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL,
    CONSTRAINT pk_spot_desk_markets PRIMARY KEY (binance_symbol),
    CONSTRAINT ck_spot_desk_markets_kind_is_a_known_label
        CHECK (kind IN ({_labels(SPOT_MARKET_KINDS_0057)})),
    CONSTRAINT ck_spot_desk_markets_tier_is_a_known_label
        CHECK (tier IN ({_labels(SPOT_MARKET_TIERS_0057)})),
    CONSTRAINT ck_spot_desk_markets_identity_is_not_empty
        CHECK (char_length(binance_symbol) > 0 AND char_length(base) > 0
               AND char_length(mint) > 0 AND char_length(updated_by) > 0),
    CONSTRAINT ck_spot_desk_markets_units_are_positive CHECK (units_per_binance_unit > 0),
    CONSTRAINT ck_spot_desk_markets_liquidity_is_not_negative CHECK (liquidity_usd_at_seed >= 0),
    CONSTRAINT ck_spot_desk_markets_decimals_are_a_token_scale
        CHECK (decimals IS NULL OR (decimals >= 0 AND decimals <= 18))
)
"""

_ORDERS = f"""
CREATE TABLE spot_orders (
    id uuid NOT NULL,
    desk text NOT NULL DEFAULT '{SPOT_DESK_LABEL_0057}',
    signal_id uuid NOT NULL,
    position_id uuid,
    market_symbol text NOT NULL,
    mint text NOT NULL,
    side text NOT NULL,
    client_order_id text NOT NULL,
    attempt integer NOT NULL DEFAULT 1,
    quote jsonb,
    intent jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    admission jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    status text NOT NULL,
    reason text,
    tx_signature text,
    signatures jsonb NOT NULL DEFAULT '[]'::jsonb,
    last_valid_block_height bigint,
    signing_at timestamptz,
    fill jsonb,
    received_at timestamptz NOT NULL DEFAULT now(),
    admitted_at timestamptz,
    simulated_at timestamptz,
    submitted_at timestamptz,
    settled_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_spot_orders PRIMARY KEY (id),
    CONSTRAINT uq_spot_orders_client_order_id UNIQUE (client_order_id),
    CONSTRAINT fk_spot_orders_signal_id_agent_signals
        FOREIGN KEY (signal_id) REFERENCES agent_signals (id),
    CONSTRAINT fk_spot_orders_market_symbol_spot_desk_markets
        FOREIGN KEY (market_symbol) REFERENCES spot_desk_markets (binance_symbol),
    CONSTRAINT ck_spot_orders_side_is_a_known_label
        CHECK (side IN ({_labels(SPOT_ORDER_SIDES_0057)})),
    CONSTRAINT ck_spot_orders_status_is_a_known_label
        CHECK (status IN ({_labels(SPOT_ORDER_STATUSES_0057)})),
    CONSTRAINT ck_spot_orders_a_refusal_or_failure_names_its_reason
        CHECK (status NOT IN ('refused', 'failed') OR reason IS NOT NULL),
    CONSTRAINT ck_spot_orders_a_confirmed_order_carries_its_fill
        CHECK (status <> 'confirmed' OR (fill IS NOT NULL AND tx_signature IS NOT NULL)),
    CONSTRAINT ck_spot_orders_a_sent_order_has_a_signature
        CHECK (status NOT IN ('submitted_unconfirmed', 'confirmed') OR tx_signature IS NOT NULL),
    CONSTRAINT ck_spot_orders_a_sell_names_its_position
        CHECK ((side = 'sell') = (position_id IS NOT NULL)),
    CONSTRAINT ck_spot_orders_attempt_is_positive CHECK (attempt >= 1),
    CONSTRAINT ck_spot_orders_identity_is_not_empty
        CHECK (char_length(client_order_id) > 0 AND char_length(desk) > 0
               AND char_length(mint) > 0)
)
"""

_POSITIONS = f"""
CREATE TABLE spot_positions (
    id uuid NOT NULL,
    signal_id uuid NOT NULL,
    entry_order_id uuid NOT NULL,
    market_symbol text NOT NULL,
    mint text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    entry_at timestamptz NOT NULL,
    entry jsonb NOT NULL,
    tokens bigint NOT NULL,
    sol_spent_lamports bigint NOT NULL,
    initial_risk_sol numeric(28, 10) NOT NULL,
    params jsonb NOT NULL,
    ata_rent_lamports bigint NOT NULL DEFAULT 0,
    mark_sol numeric(28, 10),
    mark_at timestamptz,
    mark_source text,
    mark_reason text,
    high_water_sol numeric(28, 10),
    exit_intent jsonb,
    sell_requested_at timestamptz,
    sell_requested_by text,
    exit_order_id uuid,
    exit_at timestamptz,
    exit jsonb,
    sol_received_lamports bigint,
    pnl_sol numeric(28, 10),
    r_multiple numeric(28, 10),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_spot_positions PRIMARY KEY (id),
    CONSTRAINT uq_spot_positions_signal_id UNIQUE (signal_id),
    CONSTRAINT uq_spot_positions_entry_order_id UNIQUE (entry_order_id),
    CONSTRAINT fk_spot_positions_signal_id_agent_signals
        FOREIGN KEY (signal_id) REFERENCES agent_signals (id),
    CONSTRAINT fk_spot_positions_entry_order_id_spot_orders
        FOREIGN KEY (entry_order_id) REFERENCES spot_orders (id),
    CONSTRAINT fk_spot_positions_exit_order_id_spot_orders
        FOREIGN KEY (exit_order_id) REFERENCES spot_orders (id),
    CONSTRAINT fk_spot_positions_market_symbol_spot_desk_markets
        FOREIGN KEY (market_symbol) REFERENCES spot_desk_markets (binance_symbol),
    CONSTRAINT ck_spot_positions_status_is_a_known_label
        CHECK (status IN ({_labels(SPOT_POSITION_STATUSES_0057)})),
    CONSTRAINT ck_spot_positions_a_closed_position_says_when
        CHECK ((status = 'closed') = (exit_at IS NOT NULL)),
    CONSTRAINT ck_spot_positions_an_exit_carries_its_numbers
        CHECK ((exit_at IS NULL) = (exit IS NULL)
               AND (exit_at IS NULL) = (pnl_sol IS NULL)
               AND (exit_at IS NULL) = (r_multiple IS NULL)),
    CONSTRAINT ck_spot_positions_an_exit_is_after_the_entry
        CHECK (exit_at IS NULL OR exit_at > entry_at),
    CONSTRAINT ck_spot_positions_a_mark_says_when_and_whence
        CHECK ((mark_sol IS NULL) = (mark_at IS NULL)
               AND (mark_sol IS NULL) = (mark_source IS NULL)),
    CONSTRAINT ck_spot_positions_mark_source_is_a_known_label
        CHECK (mark_source IS NULL OR mark_source IN ({_labels(SPOT_MARK_SOURCES_0057)})),
    CONSTRAINT ck_spot_positions_a_sell_request_names_who
        CHECK ((sell_requested_at IS NULL) = (sell_requested_by IS NULL)),
    CONSTRAINT ck_spot_positions_the_risk_is_the_signal_s_r
        CHECK (initial_risk_sol > 0 AND sol_spent_lamports > 0 AND tokens >= 0),
    CONSTRAINT ck_spot_positions_rent_is_not_negative CHECK (ata_rent_lamports >= 0),
    CONSTRAINT ck_spot_positions_mint_is_not_empty CHECK (char_length(mint) > 0)
)
"""

_CLOSE_THE_CYCLE = (
    f"ALTER TABLE spot_orders ADD CONSTRAINT {_POSITION_FK} "
    "FOREIGN KEY (position_id) REFERENCES spot_positions (id)"
)

_INDEXES = (
    "CREATE UNIQUE INDEX uq_spot_orders_one_buy_per_signal "
    "ON spot_orders (signal_id) WHERE side = 'buy'",
    "CREATE UNIQUE INDEX uq_spot_orders_tx_signature "
    "ON spot_orders (tx_signature) WHERE tx_signature IS NOT NULL",
    "CREATE INDEX ix_spot_orders_status_received_at ON spot_orders (status, received_at)",
    "CREATE INDEX ix_spot_orders_signal_id_side ON spot_orders (signal_id, side)",
    "CREATE INDEX ix_spot_orders_market_symbol_status ON spot_orders (market_symbol, status)",
    "CREATE INDEX ix_spot_orders_position_id ON spot_orders (position_id) "
    "WHERE position_id IS NOT NULL",
    "CREATE INDEX ix_spot_positions_status_entry_at ON spot_positions (status, entry_at)",
    "CREATE INDEX ix_spot_positions_market_symbol_status ON spot_positions (market_symbol, status)",
    "CREATE INDEX ix_spot_positions_exit_order_id ON spot_positions (exit_order_id) "
    "WHERE exit_order_id IS NOT NULL",
)

_SEED = sa.text(
    "INSERT INTO spot_desk_markets (binance_symbol, base, mint, units_per_binance_unit, kind, "
    "  tier, liquidity_usd_at_seed, round_trip_cost_pct_at_seed, enabled, updated_by) "
    "VALUES (:binance_symbol, :base, :mint, :units_per_binance_unit, :kind, :tier, "
    "  :liquidity_usd_at_seed, :round_trip_cost_pct_at_seed, :enabled, :updated_by) "
    "ON CONFLICT (binance_symbol) DO NOTHING"
)


def create_spot_desk_tables() -> None:
    op.execute(_MARKETS)
    op.execute(_ORDERS)
    op.execute(_POSITIONS)
    op.execute(_CLOSE_THE_CYCLE)
    for statement in _INDEXES:
        op.execute(statement)


def grant_spot_desk_privileges() -> None:
    for table in SPOT_DESK_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in SPOT_DESK_APP_SELL_REQUEST_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
        columns = ", ".join(SPOT_DESK_SELL_REQUEST_COLUMNS)
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP_ROLE}")
    for table in SPOT_DESK_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")


def seed_spot_desk_markets() -> None:
    """The 50 rows of R63 §2a, ``ON CONFLICT DO NOTHING`` — a row an operator
    already edited is never overwritten by a re-run."""
    parameters = [{**row._asdict(), "updated_by": SEED_WRITER_0057} for row in seed_rows()]
    op.get_bind().execute(_SEED, parameters)


def drop_spot_desk_tables() -> None:
    """Reverse of creation: the cycle first, then positions, orders, markets."""
    op.execute(f"ALTER TABLE IF EXISTS spot_orders DROP CONSTRAINT IF EXISTS {_POSITION_FK}")
    for table in reversed(SPOT_DESK_TABLES_0057):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def refuse_a_downgrade_that_would_lose_a_signed_spot_order() -> None:
    """§17.7: reversing is allowed, losing a real transaction's ledger is not —
    lock, count, name, stop.

    The lock comes first (Astra, review of this DDL): counting and then
    dropping leaves a window in which the executor confirms a signature between
    the two. ``LOCK TABLE`` inside the migration's transaction is exactly what
    the ``DROP`` will take anyway, only earlier — transaction-scoped, never
    session state. Positions count too, whatever their entry order says: a
    position is money on the chain. Refused and failed attempts without a
    signature are decisions, not money, and are let go (the design's declared
    boundary).
    """
    op.execute("LOCK TABLE spot_orders, spot_positions IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ DECLARE signed bigint; positions bigint; BEGIN "
        "SELECT count(*) INTO signed FROM spot_orders WHERE tx_signature IS NOT NULL; "
        "SELECT count(*) INTO positions FROM spot_positions; "
        "IF signed > 0 OR positions > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || signed || ' spot_orders rows carry a tx_signature and ' "
        "|| positions || ' spot_positions rows exist - real Jupiter transactions signed by the "
        "wallet; dropping the spot/1 tables loses the only ledger of what the desk did with the "
        "owner''s money', "
        "HINT = 'COPY (SELECT * FROM spot_orders) TO ... and "
        "COPY (SELECT * FROM spot_positions) TO ... before reversing'; "
        "END IF; END $$;"
    )


__all__ = [
    "SPOT_DESK_APP_READ_ONLY_TABLES",
    "SPOT_DESK_APP_SELL_REQUEST_TABLES",
    "SPOT_DESK_LABEL_0057",
    "SPOT_DESK_SELL_REQUEST_COLUMNS",
    "SPOT_DESK_TABLES_0057",
    "SPOT_DESK_WORKER_UPSERT_TABLES",
    "SPOT_MARKET_KINDS_0057",
    "SPOT_MARKET_TIERS_0057",
    "SPOT_MARK_SOURCES_0057",
    "SPOT_ORDER_SIDES_0057",
    "SPOT_ORDER_STATUSES_0057",
    "SPOT_POSITION_STATUSES_0057",
    "create_spot_desk_tables",
    "drop_spot_desk_tables",
    "grant_spot_desk_privileges",
    "refuse_a_downgrade_that_would_lose_a_signed_spot_order",
    "seed_spot_desk_markets",
]
