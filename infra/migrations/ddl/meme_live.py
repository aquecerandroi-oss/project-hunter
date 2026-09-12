"""``0028_meme_live`` — the executor's ledger: a live mode on the proposal, the real
orders, the real positions and the durable daily latch (T4.14).

**One column, three tables, grants by subtraction.** Global and RLS-free
(DATABASE.md §1.1), the shape of ``0022``/``0027``: an order signed against an
on-chain curve belongs to no organization.

- ``meme_proposals.mode`` (``paper`` | ``live``, default ``paper``): the desk
  (T4.7) writes ``live`` on approval **only** when the API's own
  ``ENABLE_MEME_LIVE_TRADING`` is on; the paper loop keeps filling the same
  proposal in shadow. ``hunter_app`` gains ``UPDATE (mode)`` next to its four
  decision columns and nothing else.
- ``meme_live_orders``: one row per attempt (``client_order_id`` unique —
  ``meme:{proposal_id}`` for the buy, ``meme:{proposal_id}:exit:{n}`` for a
  sell), with the admission (every check, the refusal by name), the intent
  handed to the builder, the **list of signatures ever emitted** (§9.4 rule 1),
  the signing lock (rule 2, ``signing_at``), the state of §9.6
  (``admitted`` → ``simulated`` → ``submitted_unconfirmed`` → ``confirmed`` |
  ``failed``, or ``refused``) and the fill **as the ``TradeEvent`` reported it**.
  A buy is unique per proposal (partial unique index); a signature is unique
  across orders (a redelivered stream event finds its row, never creates one).
- ``meme_live_positions``: derived from confirmed buys (one per proposal), the
  honest mark with its source, the exit intent, the operator's ``sell_now``
  (``sell_requested_at/by`` — the **only** two columns ``hunter_app`` may
  update here), and the close with R where **risk = SOL spent** (§5).
- ``meme_live_kill_switch``: one row per scope (``wallet`` today) holding the
  **latched** daily state (§7) and the **durable day anchor** (``day_start_utc``,
  ``day_start_sol_equity``, ``peak_sol_equity``, ``anchor_observed_at``): the
  daily loss is measured against a persisted midnight equity, never against
  the first balance a restarted process happens to read. The executor writes ``TRADING_DISABLED`` when
  the day's loss reaches the cap; only an owner's manual ``UPDATE`` (documented
  in ``docs/DEPLOYMENT.md``) releases it — no code path does.

**Who writes what.** ``hunter_worker`` (the executor): ``SELECT``/``INSERT``/
``UPDATE`` on the three tables. ``hunter_app``: ``SELECT`` on the three plus
``UPDATE (sell_requested_at, sell_requested_by)`` on the positions. ``DELETE``
to nobody. **The downgrade refuses** while ``meme_live_orders`` holds a row or a
proposal says ``mode = 'live'``: a real order is evidence.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_LIVE_TABLES_0028: tuple[str, ...] = (
    "meme_live_orders",
    "meme_live_positions",
    "meme_live_kill_switch",
)
"""Creation order: positions reference orders."""

MEME_LIVE_APP_READ_ONLY_TABLES: tuple[str, ...] = ("meme_live_orders", "meme_live_kill_switch")
MEME_LIVE_APP_SELL_REQUEST_TABLES: tuple[str, ...] = ("meme_live_positions",)
"""``SELECT`` plus ``UPDATE`` of :data:`MEME_LIVE_SELL_REQUEST_COLUMNS` only — the
``0007``/``0022`` column-grant shape: the API may ask for a sale, never record one."""

MEME_LIVE_SELL_REQUEST_COLUMNS: tuple[str, ...] = ("sell_requested_at", "sell_requested_by")
MEME_LIVE_WORKER_UPSERT_TABLES: tuple[str, ...] = MEME_LIVE_TABLES_0028

PROPOSAL_MODES_0028: tuple[str, ...] = ("paper", "live")
LIVE_ORDER_SIDES_0028: tuple[str, ...] = ("buy", "sell")
LIVE_ORDER_STATUSES_0028: tuple[str, ...] = (
    "admitted",
    "refused",
    "simulated",
    "submitted_unconfirmed",
    "confirmed",
    "failed",
)
LIVE_POSITION_STATUSES_0028: tuple[str, ...] = ("open", "closed")
LIVE_MARK_SOURCES_0028: tuple[str, ...] = ("solana_rpc", "curve_snapshot", "tape")
KILL_SWITCH_STATES_0028: tuple[str, ...] = ("ACTIVE", "WARNING", "TRADING_DISABLED", "EMERGENCY")


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_ORDERS = f"""
CREATE TABLE meme_live_orders (
    id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    side text NOT NULL,
    client_order_id text NOT NULL,
    attempt integer NOT NULL DEFAULT 1,
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
    CONSTRAINT pk_meme_live_orders PRIMARY KEY (id),
    CONSTRAINT uq_meme_live_orders_client_order_id UNIQUE (client_order_id),
    CONSTRAINT fk_meme_live_orders_proposal_id_meme_proposals
        FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
    CONSTRAINT ck_meme_live_orders_side_is_a_known_label
        CHECK (side IN ({_labels(LIVE_ORDER_SIDES_0028)})),
    CONSTRAINT ck_meme_live_orders_status_is_a_known_label
        CHECK (status IN ({_labels(LIVE_ORDER_STATUSES_0028)})),
    CONSTRAINT ck_meme_live_orders_a_refusal_or_failure_names_its_reason
        CHECK (status NOT IN ('refused', 'failed') OR reason IS NOT NULL),
    CONSTRAINT ck_meme_live_orders_a_confirmed_order_carries_its_fill
        CHECK (status <> 'confirmed' OR (fill IS NOT NULL AND tx_signature IS NOT NULL)),
    CONSTRAINT ck_meme_live_orders_a_sent_order_has_a_signature
        CHECK (status NOT IN ('submitted_unconfirmed', 'confirmed') OR tx_signature IS NOT NULL),
    CONSTRAINT ck_meme_live_orders_attempt_is_positive CHECK (attempt >= 1),
    CONSTRAINT ck_meme_live_orders_identity_is_not_empty CHECK (char_length(client_order_id) > 0)
)
"""

_POSITIONS = f"""
CREATE TABLE meme_live_positions (
    id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    entry_order_id uuid NOT NULL,
    mint text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    entry_at timestamptz NOT NULL,
    entry jsonb NOT NULL,
    tokens bigint NOT NULL,
    sol_spent_lamports bigint NOT NULL,
    initial_risk_sol numeric(28, 10) NOT NULL,
    params jsonb NOT NULL,
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
    migrated boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_live_positions PRIMARY KEY (id),
    CONSTRAINT uq_meme_live_positions_proposal_id UNIQUE (proposal_id),
    CONSTRAINT fk_meme_live_positions_proposal_id_meme_proposals
        FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
    CONSTRAINT fk_meme_live_positions_entry_order_id_meme_live_orders
        FOREIGN KEY (entry_order_id) REFERENCES meme_live_orders (id),
    CONSTRAINT fk_meme_live_positions_exit_order_id_meme_live_orders
        FOREIGN KEY (exit_order_id) REFERENCES meme_live_orders (id),
    CONSTRAINT ck_meme_live_positions_status_is_a_known_label
        CHECK (status IN ({_labels(LIVE_POSITION_STATUSES_0028)})),
    CONSTRAINT ck_meme_live_positions_a_closed_position_says_when
        CHECK ((status = 'closed') = (exit_at IS NOT NULL)),
    CONSTRAINT ck_meme_live_positions_an_exit_carries_its_numbers
        CHECK ((exit_at IS NULL) = (exit IS NULL)
               AND (exit_at IS NULL) = (pnl_sol IS NULL)
               AND (exit_at IS NULL) = (r_multiple IS NULL)),
    CONSTRAINT ck_meme_live_positions_an_exit_is_after_the_entry
        CHECK (exit_at IS NULL OR exit_at > entry_at),
    CONSTRAINT ck_meme_live_positions_a_mark_says_when_and_whence
        CHECK ((mark_sol IS NULL) = (mark_at IS NULL)
               AND (mark_sol IS NULL) = (mark_source IS NULL)),
    CONSTRAINT ck_meme_live_positions_mark_source_is_a_known_label
        CHECK (mark_source IS NULL OR mark_source IN ({_labels(LIVE_MARK_SOURCES_0028)})),
    CONSTRAINT ck_meme_live_positions_a_sell_request_names_who
        CHECK ((sell_requested_at IS NULL) = (sell_requested_by IS NULL)),
    CONSTRAINT ck_meme_live_positions_the_risk_is_what_was_spent
        CHECK (initial_risk_sol > 0 AND sol_spent_lamports > 0 AND tokens >= 0),
    CONSTRAINT ck_meme_live_positions_mint_is_not_empty CHECK (char_length(mint) > 0)
)
"""

_KILL_SWITCH = f"""
CREATE TABLE meme_live_kill_switch (
    scope text NOT NULL,
    state text NOT NULL DEFAULT 'ACTIVE',
    reason text,
    latched_at timestamptz,
    released_at timestamptz,
    released_by text,
    day_start_utc timestamptz,
    day_start_sol_equity numeric(28, 10),
    peak_sol_equity numeric(28, 10),
    anchor_observed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_live_kill_switch PRIMARY KEY (scope),
    CONSTRAINT ck_meme_live_kill_switch_state_is_a_known_label
        CHECK (state IN ({_labels(KILL_SWITCH_STATES_0028)})),
    CONSTRAINT ck_meme_live_kill_switch_a_release_names_who
        CHECK ((released_at IS NULL) = (released_by IS NULL)),
    CONSTRAINT ck_meme_live_kill_switch_an_anchor_is_whole
        CHECK ((day_start_utc IS NULL) = (day_start_sol_equity IS NULL)
               AND (day_start_utc IS NULL) = (peak_sol_equity IS NULL)
               AND (day_start_utc IS NULL) = (anchor_observed_at IS NULL))
)
"""

_INDEXES = (
    "CREATE UNIQUE INDEX uq_meme_live_orders_one_buy_per_proposal "
    "ON meme_live_orders (proposal_id) WHERE side = 'buy'",
    "CREATE UNIQUE INDEX uq_meme_live_orders_tx_signature "
    "ON meme_live_orders (tx_signature) WHERE tx_signature IS NOT NULL",
    "CREATE INDEX ix_meme_live_orders_status_received_at ON meme_live_orders (status, received_at)",
    "CREATE INDEX ix_meme_live_orders_proposal_id_side ON meme_live_orders (proposal_id, side)",
    "CREATE INDEX ix_meme_live_positions_status_entry_at ON meme_live_positions (status, entry_at)",
    "CREATE INDEX ix_meme_live_positions_mint ON meme_live_positions (mint)",
    "CREATE INDEX ix_meme_proposals_live_decided_at ON meme_proposals (decided_at) "
    "WHERE mode = 'live'",
)


def add_proposal_mode() -> None:
    """``meme_proposals.mode``, defaulted so every row of today is ``paper``."""
    op.execute("ALTER TABLE meme_proposals ADD COLUMN mode text NOT NULL DEFAULT 'paper'")
    op.execute(
        "ALTER TABLE meme_proposals ADD CONSTRAINT ck_meme_proposals_mode_is_a_known_label "
        f"CHECK (mode IN ({_labels(PROPOSAL_MODES_0028)}))"
    )
    op.execute(f"GRANT UPDATE (mode) ON meme_proposals TO {APP_ROLE}")


def create_meme_live_tables() -> None:
    op.execute(_ORDERS)
    op.execute(_POSITIONS)
    op.execute(_KILL_SWITCH)
    for statement in _INDEXES:
        op.execute(statement)


def grant_meme_live_privileges() -> None:
    for table in MEME_LIVE_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_LIVE_APP_SELL_REQUEST_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
        columns = ", ".join(MEME_LIVE_SELL_REQUEST_COLUMNS)
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP_ROLE}")
    for table in MEME_LIVE_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")


def seed_kill_switch_scope() -> None:
    op.execute(
        "INSERT INTO meme_live_kill_switch (scope, state) VALUES ('wallet', 'ACTIVE') "
        "ON CONFLICT (scope) DO NOTHING"
    )


def drop_meme_live_tables() -> None:
    op.execute("DROP INDEX IF EXISTS ix_meme_proposals_live_decided_at")
    for table in reversed(MEME_LIVE_TABLES_0028):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def drop_proposal_mode() -> None:
    op.execute("ALTER TABLE meme_proposals DROP CONSTRAINT ck_meme_proposals_mode_is_a_known_label")
    op.execute("ALTER TABLE meme_proposals DROP COLUMN mode")


def refuse_a_downgrade_that_would_lose_a_real_order() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    op.execute(
        "DO $$ DECLARE orders bigint; live bigint; BEGIN "
        "SELECT count(*) INTO orders FROM meme_live_orders; "
        "SELECT count(*) INTO live FROM meme_proposals WHERE mode = 'live'; "
        "IF orders > 0 OR live > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || orders || ' meme_live_orders rows and ' || live || "
        "' live proposals exist - real signatures and real decisions; dropping them loses the "
        "only record of what the executor did with the owner''s money', "
        "HINT = 'COPY (SELECT * FROM meme_live_orders) TO ... before reversing'; "
        "END IF; END $$;"
    )
