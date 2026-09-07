"""The DDL ``0006_paper_wallet`` owns beyond ``op.create_table`` — DATABASE.md §18.

Same split as :mod:`ddl.shadow` and :mod:`ddl.analysis`: the revision file stays
readable and the frozen lists have one home. Five things live here.

**Grant classes for the six new tables.** ``ddl.tables``' four classes are frozen
as of ``0001``, ``ddl.shadow``'s as of ``0002`` and ``ddl.analysis``'s as of
``0003``; these are this revision's addition, and ``test_schema_privileges.py``
unions them all so every table stays classified exactly once.

**Immutability, by trigger, where the plan says immutable.** ``fx_observations``
and ``portfolio_currency_anchor`` refuse every ``UPDATE``; ``market_betas``
refuses every ``UPDATE`` except setting ``superseded_at`` once, from ``NULL``,
which is the declared exception to RISK_ENGINE.md §6's "só INSERT" and the only
way "which revision is in force" can be decided by a unique index instead of by
convention. A trigger and not a ``REVOKE`` because no revoke reaches the table
owner (§17.2's lesson).

**Permanence of the principal wallet.** The partial unique index makes a *second*
principal wallet impossible; it does nothing about deleting the first one. And
``portfolios`` is in ``APP_WRITE_TABLES``, so ``hunter_app`` holds ``DELETE`` —
one statement erases the wallet, its anchor and its peak, and the next request
opens a fresh R$100.000. That is exactly the reset the directive forbids, so
:func:`create_permanence_guards` closes it from two sides: the identity fields
that would move a wallet out of the protected scope are frozen once it is
anchored, and deleting it is refused outright for the application role and
requires a declared teardown for anyone else.

**Guards for a populated database, and for the downgrade.** Seven invariants
cannot be derived for rows that already violate them, so the upgrade counts the
offenders and refuses with instructions (``0002``'s precedent). The downgrade
refuses whenever reversing would silently destroy an obligation or the evidence
behind a number that survives — an unprotected position, a reservation nobody
released, participation already spent, the opening rate of a wallet.

Nothing here depends on session state: no session-level prepared statement, no
``LISTEN``/``NOTIFY``, no session advisory lock. The one GUC involved,
``app.portfolio_teardown``, is read with ``NULLIF(current_setting(..., true), '')``
and written with ``SET LOCAL``, exactly like ``app.current_org`` (§15.4) and
``app.baseline_retention`` (§17.2).
"""

from __future__ import annotations

from collections.abc import Mapping

from alembic import op

from ddl.enums import INITIAL_ENUMS
from hunter_core.db.models import APP_ROLE, ORG_MATCH, TENANT_POLICY, WORKER_ROLE

PAPER_APP_READ_ONLY_TABLES: tuple[str, ...] = ("fx_observations", "market_betas")
"""``SELECT`` for ``hunter_app``, like every other global table.

The API shows the rate a wallet opened at and the beta a decision consumed; the
workers are the only writers (the market-worker collects FX, the scanner-worker
computes beta), which keeps DATABASE.md §15.6's empty write-exception list empty.
"""

PAPER_APPEND_TABLES: tuple[str, ...] = (
    "portfolio_currency_anchor",
    "participation_consumptions",
)
"""``SELECT`` + ``INSERT`` for **both** roles — never ``UPDATE``, never ``DELETE``.

The append-only shape of :data:`ddl.tables.APPEND_ONLY_TABLES`, for two tables
that are records of fact rather than state. The anchor is written once when the
wallet opens (by the API or by a worker, whichever runs the opening) and read for
ever after; the participation ledger is an event log whose entries are the
budget's memory — editing one would move money that was already spent, deleting
one would give a market's minute back.
"""

PAPER_NO_DELETE_TABLES: tuple[str, ...] = ("portfolio_exit_intents",)
"""``SELECT``/``INSERT``/``UPDATE`` for both roles — and never ``DELETE``.

An intention is genuinely mutable: it accumulates ``filled_qty`` and changes
state. It may not be *removed* — it is the proof a position was protected.
"""

PAPER_LOCK_ONLY_TABLES: tuple[str, ...] = ("portfolio_risk_state",)
"""``hunter_app``: ``SELECT``/``INSERT`` and ``UPDATE`` of **one column**.

The engine owns this row (security review, finding 5): the peak, the trading day
and its equity reference are ``hunter_worker``'s, and the API's business is the
kill-switch column and its transition (T3.6). But the API also has to *take the
wallet lock* on the way in (``hunter_core.risk.scopes.load_locked_state``), and
PostgreSQL charges ``ACL_UPDATE`` for ``SELECT ... FOR UPDATE``, so a plain
``REVOKE`` would reintroduce ``0005``'s bug with a new name — *permission denied
for table portfolio_risk_state*, aborting the whole resume transaction.

**A column-level grant is the exact shape needed, and this is measured, not
assumed.** ``GRANT UPDATE (updated_at)`` lets the role take the row lock and
refuses every ``UPDATE`` that writes a value:

    GRANT SELECT, UPDATE (updated_at) ON t TO r;
    SET ROLE r; SELECT v FROM t WHERE id = 1 FOR UPDATE;   -- 1 row
    SET ROLE r; UPDATE t SET v = 99 WHERE id = 1;          -- permission denied

(Postgres 16.15, probe of the T3.1b review. This contradicts the sentence in
§17.2 that says a column grant "não serve" for a row mark; ``0005``'s table-wide
grant on ``feature_baselines`` is left as it is, because there the immutability
lives entirely in a trigger that binds the owner too — but the claim behind it is
wrong and §17.2 now says so.)

Why the privilege and not only the trigger: ``current_user = 'hunter_app'`` is a
**name** test, and a login that merely *inherits* ``hunter_app`` keeps the
privileges while reporting its own name — Astra reproduced exactly that, updating
the peak to 999999 through an inheriting role. A privilege is inherited too, so
narrowing it to one column travels with the inheritance; the trigger stays as
defence in depth and is now a role-*membership* test rather than a name.
"""

PAPER_WORKER_APPEND_TABLES: tuple[str, ...] = ("fx_observations",)
"""``SELECT`` + ``INSERT`` for ``hunter_worker``: observations accumulate."""

PAPER_WORKER_SUPERSEDE_TABLES: tuple[str, ...] = ("market_betas",)
"""``SELECT``/``INSERT``/``UPDATE`` for ``hunter_worker`` — and no ``DELETE``.

The ``UPDATE`` is for retiring a revision (``superseded_at``), not for editing
one: ``market_betas_immutable`` refuses every other change, for every role, the
owner included. Same shape of argument as ``0005``'s row-lock grant — the
privilege is named for the capability the trigger cannot express, and the
immutability lives entirely in the trigger.
"""

PAPER_TENANT_TABLES: tuple[str, ...] = (
    "participation_consumptions",
    "portfolio_currency_anchor",
    "portfolio_exit_intents",
    "portfolio_risk_state",
)
"""The tenant tables this revision adds — RLS enabled, forced and policed.

``fx_observations`` and ``market_betas`` are deliberately **not** here: both are
global market data (§1.1). A beta computed by the scanner from global candles
belongs to no organization, and giving it an ``organization_id`` would mean
either a copy per tenant or a column that is the same value for everyone.
"""

TEARDOWN_SETTING = "app.portfolio_teardown"
"""``SET LOCAL app.portfolio_teardown = 'on'`` — an operator's declaration.

Transaction-scoped, so it cannot leak into the next transaction on a pooled
connection. It is **not** an authorisation: a marker anyone can set authorises
nobody, which is why the trigger refuses the application role even when the
marker is present (Astra). What it buys is that removing a tenant stays possible
for the operator role, and that doing so is an act rather than an accident.
"""

_FROZEN_PORTFOLIO_COLUMNS: tuple[str, ...] = (
    "organization_id",
    "workspace_id",
    "type",
    "is_arena",
    "base_currency",
    "initial_capital",
)
"""What an anchored wallet may never change.

Every one of them would move the wallet out of ``(organization_id,
workspace_id, type = 'paper', is_arena = false)`` — the scope the partial unique
index protects — and so free a second principal wallet to be opened. Flipping
``is_arena`` is the concrete one: the row leaves the index, a new principal is
created with a fresh R$100.000, and no ``DELETE`` ever happened for a delete
trigger to catch. ``base_currency`` and ``initial_capital`` are frozen for the
neighbouring reason: the anchor states what was credited, and a wallet that can
rewrite its own opening capital does not need a reset to have one.
"""

FX_IMMUTABLE = "fx_observations_immutable"
BETA_IMMUTABLE = "market_betas_immutable"
ANCHOR_IMMUTABLE = "portfolio_currency_anchor_immutable"
ANCHOR_MATCHES_FX = "portfolio_currency_anchor_matches_observation"
RISK_STATE_GUARD = "portfolio_risk_state_guard"
RISK_STATE_OPENS_HONESTLY = "portfolio_risk_state_opens_honestly"
LOCK_COLUMN = "updated_at"
"""The one column ``hunter_app`` may ``UPDATE`` — see :data:`PAPER_LOCK_ONLY_TABLES`.

It carries no risk figure, and the grant on it exists for exactly one reason:
PostgreSQL charges ``ACL_UPDATE`` for a row mark, and a *column* grant satisfies
that while refusing every ``UPDATE`` that writes a value (measured, Postgres 16)."""
PORTFOLIO_PERMANENCE = "portfolios_permanence"
WORKSPACE_PERMANENCE = "workspaces_permanence"
KILL_SWITCH_AUDITED = "portfolios_kill_switch_is_audited"
ORG_KILL_SWITCH_AUDITED = "organizations_kill_switch_is_audited"
PARTICIPATION_RELEASE = "participation_consumptions_release_within_reservation"

_IS_ANCHORED = (
    "SELECT EXISTS (SELECT 1 FROM portfolio_currency_anchor "
    "WHERE portfolio_id = OLD.id) INTO anchored;"
)
"""Read out of the f-string below so the trigger body is not flagged as query
construction: every value in it is a literal of this module."""

_MARKER_IS_SET = (
    f"NULLIF(current_setting('{TEARDOWN_SETTING}', true), '') IS NOT DISTINCT FROM 'on'"
)

_HAS_APP = f"pg_has_role(current_user, '{APP_ROLE}', 'USAGE')"
_HAS_WORKER = f"pg_has_role(current_user, '{WORKER_ROLE}', 'USAGE')"

_CALLER_IS_THE_APP = f"({_HAS_APP} AND NOT {_HAS_WORKER})"
"""The session has the API's privileges **and nothing beyond them**.

``current_user = 'hunter_app'`` was a *name* test and Astra walked through it in
the T3.1b review: a login that merely inherits ``hunter_app`` keeps every
privilege of the role while reporting its own name, so the guard did not
recognise it. ``pg_has_role(..., 'USAGE')`` asks the question the guard actually
means — *are the application's privileges available to this session?* — and the
second half is what keeps the operator out of it: a superuser (or the owner, who
is a member of both) has the worker's privileges too, so it is not "the app" and
may still tear a tenant down with the declared marker. ``hunter_app`` itself, and
anything that inherits only it, is."""

_CALLER_IS_THE_ENGINE = _HAS_WORKER
"""The session has ``hunter_worker``'s privileges — the lock row's only writer."""


def _function(name: str, body: str) -> None:
    op.execute(f"""
CREATE FUNCTION {name}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $${body}$$
""")


def _drop(trigger: str, table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute(f"DROP FUNCTION IF EXISTS {trigger}()")


def create_immutability() -> None:
    """Refuse every edit the plan calls immutable, for every role."""
    _function(
        FX_IMMUTABLE,
        """
    BEGIN
        RAISE EXCEPTION USING
            MESSAGE = 'fx_observations ' || OLD.id || ' is immutable: an observed rate '
                || 'is evidence, not a cache',
            HINT = 'record a new observation; every equity point names the observation '
                || 'it used, so editing one rewrites a past that was already published';
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {FX_IMMUTABLE} BEFORE UPDATE OR DELETE ON fx_observations "
        f"FOR EACH ROW EXECUTE FUNCTION {FX_IMMUTABLE}()"
    )
    _function(
        BETA_IMMUTABLE,
        """
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'market_betas ' || OLD.id || ' is immutable: a beta revision '
                    || 'is never deleted',
                HINT = 'retire it by setting superseded_at, which is the only column '
                    || 'this table lets an UPDATE touch';
        END IF;
        IF OLD.superseded_at IS NOT NULL THEN
            RAISE EXCEPTION USING
                MESSAGE = 'market_betas ' || OLD.id || ' was already superseded at '
                    || OLD.superseded_at,
                HINT = 'a revision is retired once; write a new revision instead';
        END IF;
        IF NEW.superseded_at IS NULL THEN
            RAISE EXCEPTION USING
                MESSAGE = 'market_betas ' || OLD.id || ' may only be updated to set '
                    || 'superseded_at',
                HINT = 'clearing superseded_at would revive a retired revision';
        END IF;
        IF to_jsonb(NEW) - 'superseded_at' IS DISTINCT FROM to_jsonb(OLD) - 'superseded_at' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'market_betas ' || OLD.id || ' is immutable except for '
                    || 'superseded_at',
                HINT = 'a recomputation is a new revision with its own input_digest, '
                    || 'never an edit of the one a decision already cited';
        END IF;
        RETURN NEW;
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {BETA_IMMUTABLE} BEFORE UPDATE OR DELETE ON market_betas "
        f"FOR EACH ROW EXECUTE FUNCTION {BETA_IMMUTABLE}()"
    )


def drop_immutability() -> None:
    _drop(FX_IMMUTABLE, "fx_observations")
    _drop(BETA_IMMUTABLE, "market_betas")


def create_anchor_guards() -> None:
    """The anchor is written once, agrees with its observation, and stays put.

    "Agrees" is four things, and the first two are the security review's finding
    6: the observation has to be **on this wallet's pair**
    (``operating_currency || origin_currency``, i.e. ``USDTBRL``) and to carry an
    ``available_at``. Without the pair check, an anchor naming a ``BTCUSDT``
    observation at 60000 opened a wallet with "R$1,2 bilhão" — every CHECK
    passed, because ``conversion_is_exact`` only proves the arithmetic is
    internally consistent, not that the rate prices the right two currencies.
    And the anchor is immutable, so the wrong opening would be permanent.
    """
    _function(
        ANCHOR_MATCHES_FX,
        """
    DECLARE observed numeric;
    DECLARE observed_pair text;
    DECLARE observed_available timestamptz;
    DECLARE declared numeric;
    DECLARE wallet_currency text;
    BEGIN
        SELECT rate, pair, available_at INTO observed, observed_pair, observed_available
        FROM fx_observations WHERE id = NEW.fx_observation_id;
        IF observed_pair IS DISTINCT FROM (NEW.operating_currency || NEW.origin_currency) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_currency_anchor names fx_observation '
                    || NEW.fx_observation_id || ' on pair '
                    || coalesce(observed_pair, 'missing') || ', and this wallet converts '
                    || NEW.origin_currency || ' into ' || NEW.operating_currency
                    || ', whose pair is ' || (NEW.operating_currency || NEW.origin_currency),
                HINT = 'the convention is operating_currency || origin_currency (USDTBRL): '
                    || 'how many units of the origin currency one unit of the operating '
                    || 'currency costs. A BTCUSDT quote copied here opens the wallet with a '
                    || 'number nobody credited, and the anchor is immutable, so the error '
                    || 'would be permanent';
        END IF;
        IF observed_available IS NULL THEN
            RAISE EXCEPTION USING
                MESSAGE = 'fx_observation ' || NEW.fx_observation_id
                    || ' has no available_at and may not anchor a wallet',
                HINT = 'available_at is when we could have acted on the rate; an opening '
                    || 'explained by a quote that was never reachable is not explained';
        END IF;
        IF observed IS DISTINCT FROM NEW.rate THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_currency_anchor rate ' || NEW.rate
                    || ' does not match fx_observation ' || NEW.fx_observation_id
                    || ' (' || coalesce(observed::text, 'missing') || ')',
                HINT = 'the anchored rate is a copy so the conversion identity can be a '
                    || 'CHECK; it may not disagree with the observation it names';
        END IF;
        SELECT initial_capital, base_currency INTO declared, wallet_currency
        FROM portfolios WHERE id = NEW.portfolio_id;
        IF declared IS DISTINCT FROM NEW.credited_amount
            OR wallet_currency IS DISTINCT FROM NEW.operating_currency THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.portfolio_id || ' says it opened with '
                    || declared || ' ' || coalesce(wallet_currency, '?')
                    || ' and the anchor credits ' || NEW.credited_amount || ' '
                    || NEW.operating_currency,
                HINT = 'two persisted sources disagreeing about the opening capital is '
                    || 'how a reconstruction starts from a number nobody credited; set '
                    || 'portfolios.initial_capital to what was actually credited';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM portfolio_risk_state WHERE portfolio_id = NEW.portfolio_id
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.portfolio_id || ' has no portfolio_risk_state',
                HINT = 'open the wallet atomically: the lock row carries the peak and the '
                    || 'FIFO sequence, and SELECT FOR UPDATE on a row that does not exist '
                    || 'serialises nothing';
        END IF;
        RETURN NEW;
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {ANCHOR_MATCHES_FX} BEFORE INSERT ON portfolio_currency_anchor "
        f"FOR EACH ROW EXECUTE FUNCTION {ANCHOR_MATCHES_FX}()"
    )
    _function(
        ANCHOR_IMMUTABLE,
        f"""
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_currency_anchor ' || OLD.id || ' is immutable',
                HINT = 'the opening of a wallet happens once; there is no aporte and no '
                    || 'reset, so there is nothing here to edit';
        END IF;
        IF {_CALLER_IS_THE_APP} OR NOT ({_MARKER_IS_SET}) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_currency_anchor ' || OLD.id || ' may not be deleted '
                    || 'by ' || current_user,
                HINT = 'removing the anchor and re-opening is the reset the directive '
                    || 'forbids; an operator role tears a tenant down with '
                    || 'SET LOCAL {TEARDOWN_SETTING} = ''on''';
        END IF;
        RETURN OLD;
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {ANCHOR_IMMUTABLE} BEFORE UPDATE OR DELETE ON portfolio_currency_anchor "
        f"FOR EACH ROW EXECUTE FUNCTION {ANCHOR_IMMUTABLE}()"
    )


def drop_anchor_guards() -> None:
    _drop(ANCHOR_IMMUTABLE, "portfolio_currency_anchor")
    _drop(ANCHOR_MATCHES_FX, "portfolio_currency_anchor")


_OBSERVED_EQUITY = (
    "greatest("
    "coalesce((SELECT max(s.equity) FROM portfolio_equity_snapshots s "
    "WHERE s.portfolio_id = NEW.portfolio_id), 0), "
    "coalesce((SELECT p.initial_capital FROM portfolios p "
    "WHERE p.id = NEW.portfolio_id), 0))"
)
"""The largest equity this wallet has ever **shown** — the ceiling of everything.

"Observed" is defined, not implied (security review, finding 5): the greatest
``portfolio_equity_snapshots.equity`` written for the wallet, or the capital its
anchor credited. Anything above that is a number the curve never showed, and
writing 999999 into ``peak_equity`` latches the wallet into a permanent
drawdown — a kill switch nobody triggered, from a peak nobody measured, and the
peak can never come back down to undo it.

**``equity_day_start`` is bounded by it, not part of it** (Astra, T3.1b diff
review). The first version put ``NEW.equity_day_start`` inside the ``greatest``,
and one statement then declared its own ceiling: an ``INSERT`` with
``peak_equity = 999999`` *and* ``equity_day_start = 999999`` passed as
``hunter_app`` with no snapshot at all. Both columns are equities of the same
wallet, so both are capped by what the wallet showed; neither may vouch for the
other.

The ``portfolios`` half is what makes the *opening* legal — the wallet's first
lock row is written before its first curve point, and the anchor already proves
``initial_capital`` is what was credited (§18.2).
"""


def create_risk_state_guards() -> None:
    """The peak only rises, the sequence only advances, and neither restarts.

    ``0006`` shipped three of those. The security review's finding 5 added the
    rest, and they are all about the same hole: ``hunter_app`` could rewrite the
    engine's own bookkeeping from inside a request handler.

    - **only the engine may ``UPDATE`` this row.** The lock row belongs to
      ``hunter_worker``; the API's business here is the kill-switch *column* and
      the transition, never the daily reference and never the peak (T3.6). The
      test is role **membership** (:data:`_CALLER_IS_THE_ENGINE`) and not
      ``current_user = 'hunter_app'``: a login that merely inherits ``hunter_app``
      keeps its privileges while reporting its own name, and Astra walked an
      inherited role straight through the name test in the T3.1b review. The
      privilege side of the same fix is :data:`PAPER_LOCK_ONLY_TABLES`;
    - **``trading_day`` is strictly increasing**, and is never unset. Rewinding
      it (or clearing it) re-opens a day whose loss was already counted;
    - **``equity_day_start`` is settable once per ``trading_day``.** Unknown to
      known is the reference becoming available; known to anything else is an
      accounting reset — the day's loss measured from a baseline chosen after
      the loss;
    - **neither the peak nor the day reference may exceed the equity that was
      observed** (:data:`_OBSERVED_EQUITY`).

    **The ``INSERT`` half is a separate, deferred trigger, and that is not a
    style choice.** Checked ``BEFORE INSERT``, the ceiling was escapable with a
    data-modifying CTE that wrote the child *before* the parent (Astra
    reproduced it): the wallet did not exist yet, the guard had nothing to
    compare against, and the foreign key — verified at the end of the statement,
    when the parent did exist — was satisfied. Deferring the check to COMMIT
    fixes the ordering, and it also lets the guard *refuse* an invisible wallet
    instead of skipping: by COMMIT, RLS has already had its say on the insert
    itself, so a row that got this far belongs to a wallet the session can see.
    """
    _function(
        RISK_STATE_GUARD,
        f"""
    DECLARE ceiling numeric;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF {_CALLER_IS_THE_APP} OR NOT ({_MARKER_IS_SET}) THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'portfolio_risk_state for ' || OLD.portfolio_id
                        || ' may not be deleted by ' || current_user,
                    HINT = 'delete-and-insert is how a peak of 110 becomes a peak of 100 '
                        || 'without any UPDATE happening; tear a tenant down with '
                        || 'SET LOCAL {TEARDOWN_SETTING} = ''on'' as an operator role';
            END IF;
            RETURN OLD;
        END IF;
        IF TG_OP = 'INSERT' THEN
            RETURN NEW;   -- the ceiling is checked at COMMIT; see the note below
        END IF;
        IF NOT ({_CALLER_IS_THE_ENGINE}) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_risk_state for ' || OLD.portfolio_id
                    || ' may not be updated by ' || current_user,
                HINT = 'the lock row is the engine''s: the daily reference and the peak are '
                    || 'written by hunter_worker. The API moves the kill switch column and '
                    || 'writes its transition, and resuming redefines neither peak nor '
                    || 'losses. The only UPDATE this schema grants the API is of '
                    || 'updated_at, which exists so it can take SELECT ... FOR UPDATE on '
                    || 'the wallet lock (the 0005 lesson)';
        END IF;
        IF NEW.peak_equity < OLD.peak_equity THEN
            RAISE EXCEPTION USING
                MESSAGE = 'peak_equity for portfolio ' || OLD.portfolio_id
                    || ' would fall from ' || OLD.peak_equity || ' to ' || NEW.peak_equity,
                HINT = 'the historical peak is monotonic and is never reset — drawdown is '
                    || 'measured from it, and lowering it would erase a limit that fired';
        END IF;
        IF NEW.peak_equity > OLD.peak_equity
            OR (NEW.equity_day_start IS NOT NULL
                AND NEW.equity_day_start IS DISTINCT FROM OLD.equity_day_start) THEN
            ceiling := greatest({_OBSERVED_EQUITY}, OLD.peak_equity);
            IF greatest(NEW.peak_equity, coalesce(NEW.equity_day_start, 0)) > ceiling THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'portfolio ' || OLD.portfolio_id || ' would carry a peak of '
                        || NEW.peak_equity || ' and a day reference of '
                        || coalesce(NEW.equity_day_start::text, 'unknown')
                        || ', above every equity observed for it (' || ceiling || ')',
                    HINT = 'both are measurements, not settings: a peak above the curve '
                        || 'latches the wallet in a drawdown that never happened and can '
                        || 'never come back down, and a day reference above it invents the '
                        || 'loss of the day. Write the equity point first';
            END IF;
        END IF;
        IF NEW.last_admission_seq < OLD.last_admission_seq THEN
            RAISE EXCEPTION USING
                MESSAGE = 'last_admission_seq for portfolio ' || OLD.portfolio_id
                    || ' would fall from ' || OLD.last_admission_seq
                    || ' to ' || NEW.last_admission_seq,
                HINT = 'fifo_v1 is a durable order; rewinding it would hand an admitted '
                    || 'place in the queue to a second proposal';
        END IF;
        IF NEW.trading_day IS DISTINCT FROM OLD.trading_day
            AND OLD.trading_day IS NOT NULL
            AND (NEW.trading_day IS NULL OR NEW.trading_day <= OLD.trading_day) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'trading_day for portfolio ' || OLD.portfolio_id
                    || ' would move from ' || OLD.trading_day || ' to '
                    || coalesce(NEW.trading_day::text, 'unknown'),
                HINT = 'the trading day only advances: re-opening a day whose loss was '
                    || 'already counted is how the daily-loss limit is cleared without '
                    || 'anything being earned back';
        END IF;
        IF NEW.trading_day IS NOT DISTINCT FROM OLD.trading_day
            AND OLD.equity_day_start IS NOT NULL
            AND (NEW.equity_day_start IS DISTINCT FROM OLD.equity_day_start
                 OR NEW.day_reference_observed_at IS DISTINCT FROM
                    OLD.day_reference_observed_at) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'the day reference of portfolio ' || OLD.portfolio_id
                    || ' for ' || coalesce(OLD.trading_day::text, 'an unknown day')
                    || ' is already ' || OLD.equity_day_start
                    || ' and is set once per trading day',
                HINT = 'rewriting it re-bases today''s loss on a number chosen after the '
                    || 'loss — an accounting reset with no DELETE and no new day. Unknown '
                    || 'to known is allowed; known to anything else is not';
        END IF;
        IF NEW.portfolio_id IS DISTINCT FROM OLD.portfolio_id
            OR NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio_risk_state identity is frozen',
                HINT = 'moving the lock row to another wallet or another organization '
                    || 'carries the peak and the sequence with it';
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    op.execute(
        f"CREATE TRIGGER {RISK_STATE_GUARD} "
        f"BEFORE INSERT OR UPDATE OR DELETE ON portfolio_risk_state "
        f"FOR EACH ROW EXECUTE FUNCTION {RISK_STATE_GUARD}()"
    )
    _function(
        RISK_STATE_OPENS_HONESTLY,
        f"""
    DECLARE ceiling numeric;
    BEGIN
        ceiling := {_OBSERVED_EQUITY};
        IF NOT EXISTS (SELECT 1 FROM portfolios p WHERE p.id = NEW.portfolio_id) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.portfolio_id || ' does not exist, or is not '
                    || 'visible to ' || current_user || ', so its lock row cannot be opened',
                HINT = 'write the wallet first; a lock row whose wallet the writer cannot see '
                    || 'has no capital to be measured against';
        END IF;
        IF greatest(NEW.peak_equity, coalesce(NEW.equity_day_start, 0)) > ceiling THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.portfolio_id || ' opens with a peak of '
                    || NEW.peak_equity || ' and a day reference of '
                    || coalesce(NEW.equity_day_start::text, 'unknown')
                    || ', above every equity this wallet has shown (' || ceiling || ')',
                HINT = 'a wallet opens at the capital its anchor credits; a peak above that '
                    || 'latches a drawdown nobody measured, and the peak never falls again';
        END IF;
        RETURN NEW;
    END;
""",  # noqa: S608
    )
    op.execute(
        f"CREATE CONSTRAINT TRIGGER {RISK_STATE_OPENS_HONESTLY} "
        f"AFTER INSERT ON portfolio_risk_state "
        f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        f"EXECUTE FUNCTION {RISK_STATE_OPENS_HONESTLY}()"
    )


def drop_risk_state_guards() -> None:
    _drop(RISK_STATE_OPENS_HONESTLY, "portfolio_risk_state")
    _drop(RISK_STATE_GUARD, "portfolio_risk_state")


def create_permanence_guards() -> None:
    """An anchored principal wallet cannot be deleted, nor moved out of scope."""
    frozen = " OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in _FROZEN_PORTFOLIO_COLUMNS
    )
    _function(
        PORTFOLIO_PERMANENCE,
        f"""
    DECLARE anchored boolean;
    BEGIN
        {_IS_ANCHORED}
        IF NOT anchored THEN
            RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
        END IF;
        IF TG_OP = 'DELETE' THEN
            IF {_CALLER_IS_THE_APP} OR NOT ({_MARKER_IS_SET}) THEN
                RAISE EXCEPTION USING
                    MESSAGE = 'portfolio ' || OLD.id || ' is an opened wallet and may not '
                        || 'be deleted by ' || current_user,
                    HINT = 'deleting the wallet and opening another one restarts the '
                        || 'equity, the peak and a latched kill switch — the reset the '
                        || 'directive forbids. An operator role removing a tenant '
                        || 'declares SET LOCAL {TEARDOWN_SETTING} = ''on''';
            END IF;
            RETURN OLD;
        END IF;
        IF {frozen} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || OLD.id || ' is anchored: its scope and its '
                    || 'opening capital are frozen',
                HINT = 'moving it to another workspace, flipping is_arena, changing its '
                    || 'type or rewriting its opening capital would free a second '
                    || 'principal wallet without deleting anything';
        END IF;
        RETURN NEW;
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {PORTFOLIO_PERMANENCE} BEFORE UPDATE OR DELETE ON portfolios "
        f"FOR EACH ROW EXECUTE FUNCTION {PORTFOLIO_PERMANENCE}()"
    )


def create_cascade_guard() -> None:
    """Refuse the *origin* of the cascade, where the caller is still the caller.

    Reproduced, not theorised: ``hunter_app`` holds ``DELETE`` on ``workspaces``
    and ``workspaces -> portfolios`` is ``ON DELETE CASCADE``, so

        SET LOCAL ROLE hunter_app;
        SET LOCAL app.portfolio_teardown = 'on';
        DELETE FROM workspaces WHERE id = ...;

    took the opened wallet with it and reported ``DELETE 1``. The reason is that
    a referential action runs the cascading delete as the **owner** of the
    referencing table, so by the time ``portfolios_permanence`` fires,
    ``current_user`` is no longer ``hunter_app`` and the role half of the check
    no longer bites. The probe is unambiguous: without the marker the same
    statement failed with *"may not be deleted by hunter"* — the owner, not the
    caller (Astra, diff review).

    Guarding here closes it before the identity changes. Same rule, one table
    earlier.
    """
    _function(
        WORKSPACE_PERMANENCE,
        f"""
    BEGIN
        IF EXISTS (
            SELECT 1 FROM portfolios p
            JOIN portfolio_currency_anchor a ON a.portfolio_id = p.id
            WHERE p.workspace_id = OLD.id
        ) AND ({_CALLER_IS_THE_APP} OR NOT ({_MARKER_IS_SET})) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'workspace ' || OLD.id || ' holds an opened wallet and may not '
                    || 'be deleted by ' || current_user,
                HINT = 'the cascade would take the wallet, its anchor and its peak, and '
                    || 'a referential action runs as the table owner, so the guard on '
                    || 'portfolios never sees who asked. An operator role declares '
                    || 'SET LOCAL {TEARDOWN_SETTING} = ''on''';
        END IF;
        RETURN OLD;
    END;
""",  # noqa: S608
    )
    op.execute(
        f"CREATE TRIGGER {WORKSPACE_PERMANENCE} BEFORE DELETE ON workspaces "
        f"FOR EACH ROW EXECUTE FUNCTION {WORKSPACE_PERMANENCE}()"
    )


def _audited_move_body(*, subject: str, scope: str, organization: str) -> str:
    """The body of an audited-kill-switch guard, for one scope.

    Written once and instantiated twice because the hole is the same on both
    tables and a second, hand-copied trigger is how the two drift apart.
    """
    return f"""
    DECLARE latest record;
    BEGIN
        SELECT t.from_state, t.to_state, t.xmin INTO latest
        FROM kill_switch_transitions t
        WHERE t.scope = '{scope}' AND t.scope_id = NEW.id
          AND t.organization_id = {organization}
        ORDER BY t.created_at DESC, t.id DESC
        LIMIT 1;
        IF NOT FOUND
            OR latest.from_state IS DISTINCT FROM OLD.kill_switch_state
            OR latest.to_state IS DISTINCT FROM NEW.kill_switch_state THEN
            RAISE EXCEPTION USING
                MESSAGE = '{subject} ' || NEW.id || ' moved its kill switch from '
                    || OLD.kill_switch_state || ' to ' || NEW.kill_switch_state
                    || ' without an audited transition',
                HINT = 'write the kill_switch_transitions row in the same transaction, and '
                    || 'let it be the newest one for this scope: the state the workers read '
                    || 'and the history a human reads may not disagree, and leaving a '
                    || 'latched block needs a named person';
        END IF;
        IF latest.xmin IS DISTINCT FROM pg_current_xact_id()::xid THEN
            RAISE EXCEPTION USING
                MESSAGE = '{subject} ' || NEW.id || ' moved its kill switch from '
                    || OLD.kill_switch_state || ' to ' || NEW.kill_switch_state
                    || ' citing a transition written by an earlier transaction',
                HINT = 'one move, one row, one transaction: a transition banked earlier '
                    || 'would unblock this wallet again every time it is latched. Write '
                    || 'the row and the column together';
        END IF;
        RETURN NEW;
    END;
"""  # noqa: S608


def create_kill_switch_audit_guard() -> None:
    """Moving an effective kill switch requires the transition that explains it.

    The CHECK on ``kill_switch_transitions`` makes an *unaudited* resumption
    unrepresentable in the history; on its own it says nothing about the columns
    the workers actually read. ``UPDATE portfolios SET kill_switch_state =
    'ACTIVE'`` was a complete, silent unblock — no row, no actor, no evidence
    (Astra, diff review).

    A **deferred constraint trigger** closes that without dictating statement
    order: at COMMIT, every change of ``kill_switch_state`` must have a matching
    transition written in the same transaction. The CHECK then applies
    transitively, so leaving TRADING_DISABLED or EMERGENCY needs a named person
    there too.

    **Three things the first version got wrong, all from the security review.**

    1. *(blocking 1)* It asked ``EXISTS`` on ``(scope, scope_id, organization_id,
       from_state, to_state)`` — any row, ever. So after one legitimate
       latch-and-resume cycle the pair ``(TRADING_DISABLED, ACTIVE)`` existed for
       good, and every later ``UPDATE portfolios SET kill_switch_state =
       'ACTIVE'`` passed with no row, no actor and no evidence (reproduced: three
       transitions for four movements). The variant is worse, because it needs no
       cycle at all: ``actor_id`` has no foreign key, so writing **one** row
       ``EMERGENCY -> ACTIVE`` naming a user id that never existed unlatched the
       wallet for ever after. Two conditions replace it: the transition has to be
       the **newest** one of that scope *and* to have been written **in this
       transaction** (``xmin = pg_current_xact_id()``). Being newest alone is not
       enough — the row can be banked in an earlier transaction, which is exactly
       the nonexistent-actor variant; being same-transaction alone is not enough
       either, because a transaction may write a matching row for a move it is
       not making.
    2. *(must-fix 3)* Only ``portfolios`` had it, while
       ``organizations.kill_switch_state`` is read as blocking by the API
       (``radar_org_derivation.py``) and moved without any transition at all. The
       same trigger now guards it with ``scope = 'organization'``.
    3. The failure mode of the ``xmin`` test is a **false refusal**, never a
       false pass, and it has one shape: a transition inserted inside a
       ``SAVEPOINT`` carries the sub-transaction's xid, not the top level's. The
       single write path (``hunter_core.risk.transitions.record_transition``)
       does not use one; the rule for T3.4/T3.6/T3.12 is written down in
       DATABASE.md §18.7 rather than left to be discovered.

    What this still does not prove is *which* person, and it does not try to:
    ``actor_id`` carries no foreign key on purpose (a user removed later must not
    be able to invalidate the trail), so authenticating the identity stays the
    API's job in T3.6. What the schema guarantees is that the move is recorded,
    once, attributed to a kind of actor, and explained.
    """
    _function(
        KILL_SWITCH_AUDITED,
        _audited_move_body(
            subject="portfolio", scope="portfolio", organization="NEW.organization_id"
        ),
    )
    op.execute(
        f"CREATE CONSTRAINT TRIGGER {KILL_SWITCH_AUDITED} AFTER UPDATE ON portfolios "
        f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        f"WHEN (OLD.kill_switch_state IS DISTINCT FROM NEW.kill_switch_state) "
        f"EXECUTE FUNCTION {KILL_SWITCH_AUDITED}()"
    )
    _function(
        ORG_KILL_SWITCH_AUDITED,
        _audited_move_body(subject="organization", scope="organization", organization="NEW.id"),
    )
    op.execute(
        f"CREATE CONSTRAINT TRIGGER {ORG_KILL_SWITCH_AUDITED} AFTER UPDATE ON organizations "
        f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        f"WHEN (OLD.kill_switch_state IS DISTINCT FROM NEW.kill_switch_state) "
        f"EXECUTE FUNCTION {ORG_KILL_SWITCH_AUDITED}()"
    )


def create_participation_guards() -> None:
    """A release gives back what was reserved, never more (security review, 8).

    ``notional > 0`` was the only bound on a ``released`` entry, so a release of
    900 against a reservation of 80 was accepted and the budget formula of §18.5
    — ``Σ(reserved − executed − released)`` — handed a market 820 USDT of the
    minute it never had. A CHECK cannot reach ``trade_proposals``, so this is a
    trigger; and a release against a proposal that never quantified a reservation
    is refused outright, because there is nothing for it to give back.
    """
    _function(
        PARTICIPATION_RELEASE,
        """
    DECLARE reserved numeric;
    BEGIN
        IF NEW.kind <> 'released' THEN
            RETURN NEW;
        END IF;
        SELECT reserved_notional INTO reserved
        FROM trade_proposals WHERE id = NEW.proposal_id;
        IF reserved IS NULL THEN
            RAISE EXCEPTION USING
                MESSAGE = 'participation release of ' || NEW.notional || ' names proposal '
                    || NEW.proposal_id || ', which never quantified a reservation',
                HINT = 'a release returns a commitment that was made; without a '
                    || 'reserved_notional there is nothing to give back to the market''s '
                    || 'minute';
        END IF;
        IF NEW.notional > reserved THEN
            RAISE EXCEPTION USING
                MESSAGE = 'participation release of ' || NEW.notional || ' for proposal '
                    || NEW.proposal_id || ' is larger than the ' || reserved
                    || ' that proposal reserved',
                HINT = 'the budget is Σ(reserved − executed − released); releasing more '
                    || 'than was reserved hands the market a minute it never had';
        END IF;
        RETURN NEW;
    END;
""",
    )
    op.execute(
        f"CREATE TRIGGER {PARTICIPATION_RELEASE} BEFORE INSERT ON participation_consumptions "
        f"FOR EACH ROW EXECUTE FUNCTION {PARTICIPATION_RELEASE}()"
    )


def drop_participation_guards() -> None:
    _drop(PARTICIPATION_RELEASE, "participation_consumptions")


def drop_permanence_guards() -> None:
    _drop(ORG_KILL_SWITCH_AUDITED, "organizations")
    _drop(KILL_SWITCH_AUDITED, "portfolios")
    _drop(WORKSPACE_PERMANENCE, "workspaces")
    _drop(PORTFOLIO_PERMANENCE, "portfolios")


def _refuse(count_sql: str, message: str, hint: str) -> None:
    """``RAISE EXCEPTION`` when ``count_sql`` finds anything, naming how many.

    ``USING MESSAGE`` rather than a ``%`` format string, for the reason
    :mod:`ddl.shadow` records: the placeholders of ``RAISE EXCEPTION 'x %', y``
    have to survive SQLAlchemy's own percent handling on the way to the server.
    """
    # Doubled apostrophes: these messages are prose, and "today''s equity" inside
    # a single-quoted SQL literal is a syntax error the migration would only hit
    # on the *downgrade* of a populated database - which is exactly the moment
    # nobody wants to discover it. ``ddl.analysis`` doubles them by hand in the
    # literals; doing it here means a future guard cannot forget.
    safe_message = message.replace("'", "''")
    safe_hint = hint.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({count_sql}) AS offending; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
        f"HINT = '{safe_hint}'; END IF; END $$;"
    )


_UPGRADE_GUARDS: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT organization_id FROM portfolios WHERE type = 'paper' AND NOT is_arena "
        "GROUP BY organization_id HAVING count(*) > 1",
        "organizations already hold more than one principal paper wallet; "
        "0006_paper_wallet makes that unique per organization and cannot choose which of "
        "them is the permanent one",
        "keep the wallet whose history is the real one, mark the others is_arena = true "
        "(an explicitly labelled experiment), and re-run the migration",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions WHERE actor_type = 'system'",
        "kill_switch_transitions rows were written by an automatic actor before "
        "0006_paper_wallet added the evidence column, so they carry the '{}' default; "
        "the revision requires an automatic move to publish the numbers that justified "
        "it and cannot invent them",
        "attach the evidence each automatic move was based on (daily loss, drawdown, "
        "equity, peak, trading day and the thresholds in force), or remove the rows, "
        "and re-run the migration",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions WHERE actor_type NOT IN ('user', 'system')",
        "kill_switch_transitions rows carry an actor_type outside (user, system); "
        "0006_paper_wallet closes that column to the two the contract defines",
        "rewrite those rows to the actor that really moved the switch and re-run",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions WHERE from_state = to_state",
        "kill_switch_transitions rows record a move that goes nowhere",
        "delete or correct the rows whose from_state equals their to_state; a "
        "transition that did not move is not a transition",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions "
        "WHERE from_state IN ('TRADING_DISABLED', 'EMERGENCY') "
        "AND to_state IN ('ACTIVE', 'WARNING') "
        "AND (actor_type <> 'user' OR actor_id IS NULL)",
        "kill_switch_transitions rows leave a blocked state without naming a person; "
        "0006_paper_wallet makes resumption an authenticated act and will not invent "
        "the identity that authorised it",
        "attribute each resumption to the user who authorised it, or remove the rows "
        "that never were one, and re-run the migration",
    ),
    (
        "SELECT 1 FROM orders o JOIN trade_proposals p ON p.id = o.proposal_id "
        "WHERE o.organization_id <> p.organization_id OR o.portfolio_id <> p.portfolio_id",
        "orders name a proposal of another organization or another wallet; the "
        "composite foreign key 0006_paper_wallet installs makes that unrepresentable "
        "and no inference can say which of the two scopes was the true one",
        "correct the divergent rows (or clear proposal_id where the link is wrong) "
        "and re-run the migration",
    ),
    (
        "SELECT 1 FROM fills f JOIN orders o ON o.id = f.order_id "
        "WHERE f.organization_id <> o.organization_id OR f.portfolio_id <> o.portfolio_id",
        "fills name an order of another organization or another wallet; same composite "
        "key, same refusal to guess",
        "correct the divergent rows and re-run the migration",
    ),
)


def refuse_rows_the_new_invariants_cannot_describe() -> None:
    """Stop the upgrade on data no derivation could honestly repair.

    ``0002`` set the precedent and the boundary: backfill what already-present
    columns *imply*, refuse what they merely suggest. On every database today
    each of these counts zero — nothing in production writes a proposal, an
    order or a fill yet (``docs/plans/M3.md``, "O que não existe").
    """
    for count_sql, message, hint in _UPGRADE_GUARDS:
        _refuse(count_sql, message, hint)


_BETA_REFERENCES = (
    "SELECT 1 FROM trade_proposals WHERE risk_decision -> 'beta' ->> 'revision_id' IS NOT NULL"
)
"""Decisions that name the exact beta revision they consumed.

The path is the contract this revision fixes for T3.2: a ``RiskDecision``
records the revision it used at ``risk_decision.beta.revision_id``. The M3
acceptance for T3.7 is "a decisão aponta a revisão usada", and a downgrade that
drops the table would leave those decisions naming nothing.
"""

_DOWNGRADE_GUARDS: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT 1 FROM risk_profiles WHERE preset = 'paper_v1'",
        "risk_profiles rows use the paper_v1 preset, which only 0006_paper_wallet "
        "defines; Postgres cannot drop an enum label, so downgrading would have to "
        "delete the profile the virtual wallet decides by",
        "point the wallet at another profile and remove the paper_v1 rows first, "
        "accepting that the seeded preset goes with them",
    ),
    (
        "SELECT 1 FROM risk_events WHERE type IN "
        "('proposal_unavailable_input', 'participation_capped', 'beta_missing')",
        "risk_events use a type only 0006_paper_wallet defines; downgrading would "
        "have to delete or reclassify audit rows to rebuild the enum",
        "export those events, then reclassify or remove them, before downgrading",
    ),
    (
        "SELECT 1 FROM portfolio_currency_anchor",
        "wallets are anchored to an opening rate; dropping the anchor destroys the "
        "F0 and E0 that every BRL number is measured from, and the directive "
        "forbids opening the wallet again to recreate them",
        "export the anchors (and the fx_observations they name) before downgrading; "
        "there is no honest way to recompute an opening that already happened",
    ),
    (
        "SELECT 1 FROM portfolio_risk_state",
        "wallets carry a durable peak and a trading-day reference; dropping them "
        "makes the next start recompute a peak from today's equity, which silently "
        "moves the drawdown limit",
        "export portfolio_risk_state before downgrading, and be explicit that the "
        "kill switch will be measured from a new peak afterwards",
    ),
    (
        "SELECT 1 FROM portfolio_exit_intents WHERE state IN ('open', 'blocked_residual')",
        "positions are protected by a durable exit intention that is still live; "
        "dropping the table ends the intention without liquidating anything, which "
        "is the silently unprotected position of RISK_ENGINE.md §10",
        "let the intentions terminate (fulfilled, superseded or voided) before "
        "downgrading; a stop that found 4 of 10 units still owes the other 6",
    ),
    (
        "SELECT 1 FROM trade_proposals WHERE reservation_state = 'held'",
        "proposals still hold a reservation; dropping the columns releases cash, "
        "risk, exposure and a slot that nobody released, and nothing afterwards "
        "knows they were ever held",
        "let the reservations be consumed, released or expired, then downgrade",
    ),
    (
        "SELECT 1 FROM participation_consumptions e WHERE e.kind = 'executed' "
        "AND e.occurred_at > now() - interval '60 seconds'",
        "participation entries were executed inside the last 60 seconds; dropping "
        "the ledger hands that market's minute back and lets the next entry exceed "
        "the 1 % the directive fixes",
        "wait for the rolling window to pass (60 s) and downgrade then",
    ),
    (
        "SELECT 1 FROM participation_consumptions c JOIN trade_proposals p "
        "ON p.id = c.proposal_id WHERE p.reservation_state = 'held'",
        "participation reservations are still outstanding in the ledger",
        "let the reservations settle, then downgrade",
    ),
    (
        "SELECT 1 FROM portfolio_equity_snapshots WHERE fx_observation_id IS NOT NULL",
        "equity points name the fx observation that explains their BRL value; "
        "dropping the column keeps the curve and loses the reason it says what it "
        "says",
        "export the snapshot-to-observation mapping before downgrading",
    ),
    (
        _BETA_REFERENCES,
        "preserved decisions name the market_betas revision they consumed; dropping "
        "the table would leave those decisions citing an explanation that no longer "
        "exists. Beta is recomputable from candles, but its availability at the "
        "moment of the decision is not",
        "export the referenced revisions before downgrading",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions t WHERE t.organization_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM organizations o WHERE o.id = t.organization_id)",
        "kill switch transitions outlived the organization they belong to, which is what "
        "0006_paper_wallet dropping the cascading foreign key is for; restoring that key "
        "cannot represent them and reverting would have to delete the trail",
        "export those transitions before downgrading, and be explicit that the record of "
        "a removed tenant's latch goes with them",
    ),
    (
        "SELECT 1 FROM kill_switch_transitions WHERE evidence <> '{}'::jsonb",
        "kill switch transitions carry the numbers that justified them; dropping "
        "the column keeps the move and loses the reason - and a system-scope "
        "transition trips none of the wallet guards above",
        "export the evidence column before downgrading",
    ),
    (
        "SELECT 1 FROM fills WHERE execution_key <> id::text",
        "fills carry a real execution idempotency key; dropping the column makes a "
        "redelivered execution a second fill again",
        "export the keys before downgrading, and expect duplicate-fill protection "
        "to fall back to whatever the adapter does in memory",
    ),
    (
        "SELECT 1 FROM trade_proposals WHERE admission_seq IS NOT NULL",
        "proposals carry a fifo_v1 admission place; dropping the column loses the "
        "order the wallet actually admitted them in",
        "export the sequence before downgrading",
    ),
    (
        "SELECT 1 FROM orders WHERE exit_intent_id IS NOT NULL",
        "orders record which durable intention they were an attempt at; dropping "
        "the column leaves attempts that no longer explain what they were for",
        "export the attempt-to-intention mapping before downgrading",
    ),
)
"""Reversing a schema is allowed; losing an obligation or its evidence is not.

Every entry is a *specific* loss that "the migration reversed cleanly" would
otherwise be the only report of. What is deliberately **not** guarded:
``market_betas`` revisions no preserved decision names and ``fx_observations`` no
anchor or snapshot names — both are recomputable or re-collectable, and refusing
on them would make the downgrade impossible on any database the collectors have
ever touched. That is accepted, recoverable loss, written down here rather than
discovered later (the §17.7 boundary).
"""


def refuse_a_downgrade_that_would_discard_durable_state() -> None:
    for count_sql, message, hint in _DOWNGRADE_GUARDS:
        _refuse(count_sql, message, hint)


def grant_paper_privileges() -> None:
    """Read for the API where the workers write; append where facts accumulate."""
    for table in PAPER_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in PAPER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}, {WORKER_ROLE}")
    for table in PAPER_NO_DELETE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}, {WORKER_ROLE}")
    for table in PAPER_LOCK_ONLY_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}, {WORKER_ROLE}")
        op.execute(f"GRANT UPDATE ({LOCK_COLUMN}) ON {table} TO {APP_ROLE}")
        op.execute(f"GRANT UPDATE ON {table} TO {WORKER_ROLE}")
    for table in PAPER_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")
    for table in PAPER_WORKER_SUPERSEDE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")


def revoke_paper_privileges() -> None:
    for table in (
        *PAPER_APP_READ_ONLY_TABLES,
        *PAPER_APPEND_TABLES,
        *PAPER_NO_DELETE_TABLES,
        *PAPER_LOCK_ONLY_TABLES,
        *PAPER_WORKER_APPEND_TABLES,
        *PAPER_WORKER_SUPERSEDE_TABLES,
    ):
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}, {WORKER_ROLE}")


def enable_paper_row_level_security() -> None:
    """Enable, force and police every tenant table this revision adds."""
    for table in PAPER_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {TENANT_POLICY} ON {table} USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})"
        )


def disable_paper_row_level_security() -> None:
    for table in PAPER_TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


_ENUM_COLUMNS: Mapping[str, tuple[tuple[str, str, str | None], ...]] = {
    "risk_preset": (("risk_profiles", "preset", "balanced"),),
    "risk_event_type": (("risk_events", "type", None),),
}
"""``type -> ((table, column, server default or None), ...)`` for the downgrade.

Every column that has to be retyped to reverse an ``ADD VALUE``. Defaults are
dropped and restored around the retype because a stored default is already
coerced to the old type and would block it — the ``0003`` recipe, unchanged.
"""


def restore_frozen_enum_labels() -> None:
    """Rebuild ``risk_preset`` and ``risk_event_type`` with the labels ``0001`` froze.

    Postgres has no ``ALTER TYPE ... DROP VALUE``, so reversing an ``ADD VALUE``
    means renaming the type, recreating it from :data:`ddl.enums.INITIAL_ENUMS`,
    retyping every column with ``USING x::text::type`` and dropping the old one.
    :func:`refuse_a_downgrade_that_would_discard_durable_state` has already
    refused if any row still carries a label that is about to disappear, so a
    cast can never fail here with "invalid input value for enum".
    """
    for type_name, columns in _ENUM_COLUMNS.items():
        previous = f"{type_name}__pre0006"
        rendered = ", ".join(f"'{label}'" for label in INITIAL_ENUMS[type_name])
        op.execute(f"ALTER TYPE {type_name} RENAME TO {previous}")
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({rendered})")
        for table, column, default in columns:
            if default is not None:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} "
                f"USING {column}::text::{type_name}"
            )
            if default is not None:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
        op.execute(f"DROP TYPE {previous}")
