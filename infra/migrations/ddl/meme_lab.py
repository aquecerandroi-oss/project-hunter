"""``0022_meme_lab`` — the continuous paper Lab on the pump.fun curve, frozen.

Four tables, seven indexes and grants by subtraction; the two views, the seed
and the downgrade guard live in ``ddl/meme_lab_views.py`` (the 350-line cut
``meme_radar_guards.py`` took). **Global and RLS-free** (DATABASE.md §1.1), the
shape of ``0021``: a paper bet on an on-chain curve belongs to no organization.

The schema is the contract ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md``
froze on 2026-09-12 04:25 BRT so the operator desk (T4.7, ``apps/**``) could be
built in parallel: the column list, the status vocabulary and the grants below
are copied from it, and every departure is a line under its "Emendas".

Every list here is **frozen as of ``0022``**, in the pattern of every ``ddl/``
module: a later edit to ``hunter_core.db.models.meme_lab`` must not change what
this revision put in the database; ``alembic check`` keeps the two in step and
``test_migrations.py`` unions these tuples with the earlier ones.

**Who writes what** — the one thing this revision exists to make a privilege
rather than a promise:

- ``hunter_worker`` (the loop in ``services/meme-worker``) proposes, fills,
  marks and closes: ``SELECT``/``INSERT``/``UPDATE`` on ``meme_proposals`` and
  ``meme_paper_bets``, ``UPDATE (applied_at, result)`` on the commands it
  executes, ``SELECT`` on the rule sets. **Never ``DELETE``** anywhere: a bet is
  evidence, and an unfilled proposal is the refusal that explains a quiet desk;
- ``hunter_app`` (the API of T4.7) decides and orders: ``INSERT`` on
  ``meme_proposals`` (a manual buy) and ``meme_operator_commands`` (sell now /
  cancel), and ``UPDATE`` of exactly the four decision columns of a proposal —
  never its quote, its reasons or its ``bet_id``. Everything else is ``SELECT``.

**Nothing here can become an order.** ``mode`` is ``CHECK``-locked to
``'paper'``: the column exists so T4.8 can add ``'live'`` with its own revision
behind ``ENABLE_MEME_LIVE_TRADING``, and until that revision no role — owner
included — can write a row that claims to be real.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_LAB_APP_READ_ONLY_TABLES: tuple[str, ...] = ("meme_rule_sets", "meme_paper_bets")
"""``SELECT`` for ``hunter_app`` and nothing else: the rule sets are seeded by
the migration and retired by an operator script, the bets are written only by
the loop. The desk reads both."""

MEME_LAB_APP_APPEND_TABLES: tuple[str, ...] = ("meme_operator_commands",)
"""``SELECT``/``INSERT`` for ``hunter_app``: an operator order is written once
and applied by the loop; the API never edits what it asked for."""

MEME_LAB_APP_DECISION_TABLES: tuple[str, ...] = ("meme_proposals",)
"""``SELECT``/``INSERT`` plus ``UPDATE`` of :data:`MEME_LAB_DECISION_COLUMNS``
only — the ``0007`` column-grant shape (``PAPER_LOCK_ONLY_TABLES``). The API can
approve, reject or create a manual proposal; it cannot touch the quote, the
reasons, the ``bet_id`` or the refusal, which are the loop's evidence."""

MEME_LAB_DECISION_COLUMNS: tuple[str, ...] = ("status", "decision", "decided_by", "decided_at")

MEME_LAB_WORKER_READ_ONLY_TABLES: tuple[str, ...] = ("meme_rule_sets",)
MEME_LAB_WORKER_UPSERT_TABLES: tuple[str, ...] = ("meme_proposals", "meme_paper_bets")
"""``SELECT``/``INSERT``/``UPDATE`` for ``hunter_worker`` — a proposal moves
through its states and a bet is marked on every snapshot, so ``UPDATE`` is the
legal shape here (unlike the append-only series of ``0021``). ``DELETE`` is
granted to nobody."""

MEME_LAB_WORKER_APPLY_TABLES: tuple[str, ...] = ("meme_operator_commands",)
"""``SELECT`` plus ``UPDATE (applied_at, result)`` for ``hunter_worker``: the
loop reports what it did with an order and cannot rewrite the order itself."""

MEME_LAB_APPLY_COLUMNS: tuple[str, ...] = ("applied_at", "result")

MEME_LAB_TABLES_0022: tuple[str, ...] = (
    "meme_rule_sets",
    "meme_proposals",
    "meme_paper_bets",
    "meme_operator_commands",
)
"""Creation order: the bets reference the proposals and the rule sets, the
commands reference both; ``meme_proposals.bet_id`` closes the cycle with an
``ALTER TABLE`` after the bets exist."""

_RULE_SETS = """
CREATE TABLE meme_rule_sets (
    id uuid NOT NULL,
    name text NOT NULL,
    version text NOT NULL,
    kind text NOT NULL,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    code_ref text NOT NULL,
    exp_ref text,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    CONSTRAINT pk_meme_rule_sets PRIMARY KEY (id),
    CONSTRAINT uq_meme_rule_sets_name_version UNIQUE (name, version),
    CONSTRAINT ck_meme_rule_sets_kind_is_a_known_label
        CHECK (kind IN ('research_only', 'operator')),
    CONSTRAINT ck_meme_rule_sets_status_is_a_known_label CHECK (status IN ('active', 'retired')),
    CONSTRAINT ck_meme_rule_sets_a_retired_set_says_when
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    CONSTRAINT ck_meme_rule_sets_research_names_its_experiment
        CHECK (kind = 'operator' OR exp_ref IS NOT NULL),
    CONSTRAINT ck_meme_rule_sets_identity_is_not_empty
        CHECK (char_length(name) > 0 AND char_length(version) > 0 AND char_length(code_ref) > 0)
)
"""

_PROPOSALS = """
CREATE TABLE meme_proposals (
    id uuid NOT NULL,
    mint text NOT NULL,
    rule_set_id uuid NOT NULL,
    origin text NOT NULL,
    status text NOT NULL DEFAULT 'proposed',
    proposed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    features_end_time timestamptz,
    quote jsonb NOT NULL DEFAULT '{}'::jsonb,
    reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    suggested jsonb NOT NULL DEFAULT '{}'::jsonb,
    decision jsonb,
    decided_by text,
    decided_at timestamptz,
    bet_id uuid,
    refusal text,
    CONSTRAINT pk_meme_proposals PRIMARY KEY (id),
    CONSTRAINT fk_meme_proposals_rule_set_id_meme_rule_sets
        FOREIGN KEY (rule_set_id) REFERENCES meme_rule_sets (id),
    CONSTRAINT ck_meme_proposals_origin_is_a_known_label CHECK (origin IN ('rules', 'operator')),
    CONSTRAINT ck_meme_proposals_status_is_a_known_label
        CHECK (status IN ('proposed', 'approved', 'rejected', 'expired', 'filled', 'unfilled')),
    CONSTRAINT ck_meme_proposals_expiry_is_after_proposal CHECK (expires_at > proposed_at),
    CONSTRAINT ck_meme_proposals_a_rules_proposal_names_its_minute
        CHECK (origin = 'operator' OR features_end_time IS NOT NULL),
    CONSTRAINT ck_meme_proposals_a_decision_names_who_and_when
        CHECK ((decided_at IS NULL) = (decided_by IS NULL)),
    CONSTRAINT ck_meme_proposals_a_decided_status_carries_a_decision
        CHECK (status IN ('proposed', 'expired') OR decided_at IS NOT NULL),
    CONSTRAINT ck_meme_proposals_a_fill_names_its_bet
        CHECK ((status = 'filled') = (bet_id IS NOT NULL)),
    CONSTRAINT ck_meme_proposals_an_unfilled_proposal_names_its_refusal
        CHECK ((status = 'unfilled') = (refusal IS NOT NULL)),
    CONSTRAINT ck_meme_proposals_mint_is_not_empty CHECK (char_length(mint) > 0)
)
"""

_BETS = """
CREATE TABLE meme_paper_bets (
    id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    rule_set_id uuid NOT NULL,
    mint text NOT NULL,
    mode text NOT NULL DEFAULT 'paper',
    status text NOT NULL DEFAULT 'open',
    entry_at timestamptz NOT NULL,
    entry jsonb NOT NULL,
    initial_risk_sol numeric(28, 10) NOT NULL,
    params jsonb NOT NULL,
    exit_intent jsonb,
    exit_at timestamptz,
    exit jsonb,
    pnl_sol numeric(28, 10),
    r_multiple numeric(28, 10),
    mark_sol numeric(28, 10),
    mark_at timestamptz,
    high_water_x numeric(28, 10),
    sol_usd_at_entry numeric(28, 10),
    sol_usd_at_exit numeric(28, 10),
    CONSTRAINT pk_meme_paper_bets PRIMARY KEY (id),
    CONSTRAINT uq_meme_paper_bets_proposal_id UNIQUE (proposal_id),
    CONSTRAINT fk_meme_paper_bets_proposal_id_meme_proposals
        FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
    CONSTRAINT fk_meme_paper_bets_rule_set_id_meme_rule_sets
        FOREIGN KEY (rule_set_id) REFERENCES meme_rule_sets (id),
    CONSTRAINT ck_meme_paper_bets_every_bet_is_paper CHECK (mode = 'paper'),
    CONSTRAINT ck_meme_paper_bets_status_is_a_known_label CHECK (status IN ('open', 'closed')),
    CONSTRAINT ck_meme_paper_bets_a_closed_bet_says_when
        CHECK ((status = 'closed') = (exit_at IS NOT NULL)),
    CONSTRAINT ck_meme_paper_bets_an_exit_carries_its_numbers
        CHECK ((exit_at IS NULL) = (exit IS NULL)
               AND (exit_at IS NULL) = (pnl_sol IS NULL)
               AND (exit_at IS NULL) = (r_multiple IS NULL)),
    CONSTRAINT ck_meme_paper_bets_an_exit_is_after_the_entry
        CHECK (exit_at IS NULL OR exit_at > entry_at),
    CONSTRAINT ck_meme_paper_bets_a_mark_says_when CHECK ((mark_sol IS NULL) = (mark_at IS NULL)),
    CONSTRAINT ck_meme_paper_bets_the_risk_is_what_was_spent CHECK (initial_risk_sol > 0),
    CONSTRAINT ck_meme_paper_bets_mint_is_not_empty CHECK (char_length(mint) > 0)
)
"""

_COMMANDS = """
CREATE TABLE meme_operator_commands (
    id uuid NOT NULL,
    bet_id uuid,
    proposal_id uuid,
    command text NOT NULL,
    issued_by text NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz,
    result jsonb,
    CONSTRAINT pk_meme_operator_commands PRIMARY KEY (id),
    CONSTRAINT fk_meme_operator_commands_bet_id_meme_paper_bets
        FOREIGN KEY (bet_id) REFERENCES meme_paper_bets (id),
    CONSTRAINT fk_meme_operator_commands_proposal_id_meme_proposals
        FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
    CONSTRAINT ck_meme_operator_commands_command_is_a_known_label
        CHECK (command IN ('sell_now', 'cancel')),
    CONSTRAINT ck_meme_operator_commands_exactly_one_target
        CHECK ((bet_id IS NULL) <> (proposal_id IS NULL)),
    CONSTRAINT ck_meme_operator_commands_a_sale_targets_a_bet
        CHECK (command <> 'sell_now' OR bet_id IS NOT NULL),
    CONSTRAINT ck_meme_operator_commands_a_cancel_targets_a_proposal
        CHECK (command <> 'cancel' OR proposal_id IS NOT NULL),
    CONSTRAINT ck_meme_operator_commands_an_application_says_what_happened
        CHECK ((applied_at IS NULL) = (result IS NULL)),
    CONSTRAINT ck_meme_operator_commands_issuer_is_not_empty CHECK (char_length(issued_by) > 0)
)
"""

_BET_BACKLINK = (
    "ALTER TABLE meme_proposals ADD CONSTRAINT fk_meme_proposals_bet_id_meme_paper_bets "
    "FOREIGN KEY (bet_id) REFERENCES meme_paper_bets (id)"
)
"""The cycle proposals → bets → proposals, closed after both exist. Dropped
first on the way down, because ``DROP TABLE`` will not cut it for us."""

_INDEXES = (
    "CREATE INDEX ix_meme_proposals_status_proposed_at ON meme_proposals (status, proposed_at)",
    "CREATE INDEX ix_meme_proposals_mint_proposed_at ON meme_proposals (mint, proposed_at)",
    "CREATE UNIQUE INDEX uq_meme_proposals_one_per_rule_set_mint_minute "
    "ON meme_proposals (rule_set_id, mint, features_end_time) WHERE origin = 'rules'",
    "CREATE INDEX ix_meme_paper_bets_status_entry_at ON meme_paper_bets (status, entry_at)",
    "CREATE INDEX ix_meme_paper_bets_rule_set_id_entry_at ON meme_paper_bets (rule_set_id, entry_at)",
    "CREATE INDEX ix_meme_paper_bets_mint ON meme_paper_bets (mint)",
    "CREATE INDEX ix_meme_operator_commands_pending ON meme_operator_commands (issued_at) "
    "WHERE applied_at IS NULL",
)
"""The contract's five, ascending (a btree read backwards serves ``ORDER BY ...
DESC`` identically, and an ascending index is what ``alembic check`` can compare),
plus two of the loop's own: the partial unique index is what makes "one proposal
per rule set per mint per closed minute" a fact of the schema instead of a
memory of the process (a restart re-evaluating a minute writes nothing twice),
and the pending-commands index is the loop's one hot read."""


def create_meme_lab_tables() -> None:
    """The four tables, the closing foreign key and the seven indexes."""
    for statement in (_RULE_SETS, _PROPOSALS, _BETS, _COMMANDS):
        op.execute(statement)
    op.execute(_BET_BACKLINK)
    for statement in _INDEXES:
        op.execute(statement)


def grant_meme_lab_privileges() -> None:
    """Read for the API plus its two writes; propose/fill/mark for the loop."""
    for table in MEME_LAB_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_LAB_APP_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
    for table in MEME_LAB_APP_DECISION_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
        op.execute(
            f"GRANT UPDATE ({', '.join(MEME_LAB_DECISION_COLUMNS)}) ON {table} TO {APP_ROLE}"
        )
    for table in MEME_LAB_WORKER_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")
    for table in MEME_LAB_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")
    for table in MEME_LAB_WORKER_APPLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")
        op.execute(
            f"GRANT UPDATE ({', '.join(MEME_LAB_APPLY_COLUMNS)}) ON {table} TO {WORKER_ROLE}"
        )


def drop_meme_lab_tables() -> None:
    """The backlink first (it is the cycle), then the tables in reverse order."""
    op.execute(
        "ALTER TABLE meme_proposals DROP CONSTRAINT IF EXISTS fk_meme_proposals_bet_id_meme_paper_bets"
    )
    for table in reversed(MEME_LAB_TABLES_0022):
        op.execute(f"DROP TABLE IF EXISTS {table}")
