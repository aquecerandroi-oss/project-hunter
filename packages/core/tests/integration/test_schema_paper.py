"""The paper wallet's schema really holds — DATABASE.md §18, RISK_ENGINE.md v2.

Everything here is asserted against a live Postgres, and everything that is about
a *privilege* or a *policy* is asserted **as the role**, never by asking
``has_table_privilege``: the lesson ``0002``'s sequence grant and ``0005``'s row
lock both paid for is that a catalogue answer and a statement are different
questions.

Four groups, matching the four promises T3.1 is accepted on:

- **permanence** — one principal paper wallet per ``(organization, workspace)``,
  including a paused, archived or soft-deleted one, and an opened wallet that
  cannot be deleted or edited out of its own scope;
- **immutability** — the opening rate, the anchor and a beta revision are
  written once, refused for every role by trigger and not merely by a revoke;
- **identity** — composite foreign keys that make "organization A's order
  pointing at organization B's proposal" unrepresentable, and the idempotency
  keys that make a redelivered execution a no-op;
- **isolation** — organization A cannot read organization B, on every one of the
  four tenant tables this revision adds.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql.elements import TextClause

from hunter_core.domain.types import uuid7
from hunter_risk.limits import PAPER_V1, RiskLimits

from .conftest import SCRIPTS_DIR

pytestmark = pytest.mark.integration

_AS_APP = text("SET LOCAL ROLE hunter_app")
_AS_WORKER = text("SET LOCAL ROLE hunter_worker")
_DENIED = "permission denied"
_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class Wallet:
    """One organization with a workspace, a market and a principal paper wallet."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.portfolio_id = uuid7()
        self.market_id = uuid7()
        self.exchange_id = uuid7()
        self.fx_id = uuid7()


async def _insert_wallet(connection: AsyncConnection, wallet: Wallet) -> None:
    """Build the tenant as the owner, which RLS does not constrain."""
    await connection.execute(
        text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
        {"id": wallet.org_id, "slug": wallet.slug},
    )
    await connection.execute(
        text(
            "INSERT INTO workspaces (id, organization_id, name, objective) "
            "VALUES (:id, :org, :name, 'paper_trading')"
        ),
        {"id": wallet.workspace_id, "org": wallet.org_id, "name": f"ws-{wallet.slug}"},
    )
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')"),
        {"id": wallet.exchange_id, "code": f"probe-{wallet.slug[:20]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, :symbol, 'spot')"
        ),
        {
            "id": wallet.market_id,
            "exchange": wallet.exchange_id,
            "symbol": f"BTC{uuid.uuid4().hex[:6].upper()}",
        },
    )
    await connection.execute(
        text(
            "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
            # The wallet declares exactly what the anchor credits: the trigger
            # refuses two persisted numbers disagreeing about the opening.
            "initial_capital) VALUES (:id, :org, :ws, :name, 'paper', 19999.9999999999)"
        ),
        {
            "id": wallet.portfolio_id,
            "org": wallet.org_id,
            "ws": wallet.workspace_id,
            "name": f"pf-{wallet.slug}",
        },
    )


async def _open_wallet(connection: AsyncConnection, wallet: Wallet) -> None:
    """Credit the wallet: the risk state, the FX observation and the anchor.

    The order is the one the trigger enforces — the lock row exists before the
    anchor, because ``SELECT FOR UPDATE`` on a row that does not exist
    serialises nothing.
    """
    await connection.execute(
        text(
            "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, peak_equity, "
            "peak_equity_at) VALUES (:org, :pf, 19999.9999999999, :ts)"
        ),
        {"org": wallet.org_id, "pf": wallet.portfolio_id, "ts": _NOW},
    )
    await connection.execute(
        text(
            "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
            "VALUES (:id, 'USDTBRL', 5.0000000000, :source, :ts, :ts)"
        ),
        # The source is per wallet because ``uq_fx_observations_observation`` is
        # (pair, source, observed_at) and observations are never deleted - two
        # wallets, and a second run of this module, would collide otherwise.
        {"id": wallet.fx_id, "ts": _NOW, "source": f"binance.spot.ticker#{wallet.slug}"},
    )
    # R$100.000 at 5.0 credits 19999.9999999999 USDT and leaves 0.0000000005 BRL
    # the rounding policy could not convert: 19999.9999999999 x 5 + 0.0000000005
    # is exactly 100000, which is what ``conversion_is_exact`` proves.
    await connection.execute(
        text(
            "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
            "origin_amount, credited_amount, fx_observation_id, rate, conversion_residual, "
            "rounding_policy) VALUES (:id, :org, :pf, 100000, 19999.9999999999, :fx, "
            "5.0000000000, :residual, 'floor_10dp_v1')"
        ),
        {
            "id": uuid7(),
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "fx": wallet.fx_id,
            "residual": "0.0000000005",
        },
    )


@pytest_asyncio.fixture
async def wallets(schema_engine: AsyncEngine) -> AsyncIterator[tuple[Wallet, Wallet]]:
    """Two organizations, each with an opened principal wallet."""
    first = Wallet(f"pw-a-{uuid.uuid4().hex[:8]}")
    second = Wallet(f"pw-b-{uuid.uuid4().hex[:8]}")
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_app TO CURRENT_USER"))
        await connection.execute(text("GRANT hunter_worker TO CURRENT_USER"))
        for wallet in (first, second):
            await _insert_wallet(connection, wallet)
            await _open_wallet(connection, wallet)
    try:
        yield first, second
    finally:
        async with schema_engine.begin() as connection:
            await connection.execute(text(f"SET LOCAL {_TEARDOWN} = 'on'"))
            for wallet in (first, second):
                # The observations stay: they are global, immutable evidence and
                # the trigger refuses to delete one for any role at all.
                await connection.execute(
                    text("DELETE FROM organizations WHERE id = :id"), {"id": wallet.org_id}
                )


_TEARDOWN = "app.portfolio_teardown"
"""The operator's declaration. Not an authorisation — see the delete tests."""


async def _as(
    engine: AsyncEngine, role: TextClause, org: uuid.UUID | None = None
) -> AsyncConnection:
    connection = await engine.connect()
    await connection.begin()
    if org is not None:
        await connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org)}
        )
    await connection.execute(role)
    return connection


# --------------------------------------------------------------------------
# Permanence — the directive's "no reset", expressed as schema
# --------------------------------------------------------------------------


async def test_the_principal_wallet_index_is_keyed_on_the_organization_alone(
    schema_engine: AsyncEngine,
) -> None:
    """The key *and* the predicate, read back from Postgres, not from the model.

    Alembic compares the *columns* of an index and not its ``WHERE`` (§17.3), so
    an index left with the wrong predicate reports no drift while enforcing the
    wrong invariant. The joint M3 decision is explicit about both halves: the
    predicate must not mention ``status`` and must not exclude a filled
    ``deleted_at`` — archiving or soft-deleting the wallet and opening another
    one is the substitution the directive forbids.

    The **key** is the security review's blocking finding 2. With
    ``(organization_id, workspace_id)`` the index was permanence against nothing
    a user cannot undo: creating a workspace is an ordinary product action, and
    the wallet inside it is a fresh R$100.000. D7 is one principal wallet, so the
    key is the organization.
    """
    async with schema_engine.connect() as connection:
        definition: str | None = await connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": "uq_portfolios_principal_paper"},
        )
    assert definition is not None, "the principal-wallet index is missing"
    assert "UNIQUE INDEX" in definition
    assert "(organization_id)" in definition
    assert "workspace_id" not in definition, (
        "keyed on the workspace, a second principal wallet is one CREATE WORKSPACE away"
    )
    assert "type = 'paper'" in definition
    assert "NOT is_arena" in definition
    assert "status" not in definition, "the index must not depend on status"
    assert "deleted_at" not in definition, "the index must not exclude a soft-deleted wallet"


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "'archived'"), ("status", "'paused'"), ("deleted_at", "now()")],
)
async def test_a_second_principal_wallet_is_refused_however_the_first_is_retired(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet], column: str, value: str
) -> None:
    """Archiving, pausing or soft-deleting the first does not free the scope."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(f"UPDATE portfolios SET {column} = {value} WHERE id = :id"),  # noqa: S608
            {"id": wallet.portfolio_id},
        )
    with pytest.raises(IntegrityError, match="uq_portfolios_principal_paper"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "initial_capital) VALUES (:id, :org, :ws, 'second', 'paper', 100000)"
                ),
                {"id": uuid7(), "org": wallet.org_id, "ws": wallet.workspace_id},
            )


async def test_an_arena_wallet_may_share_the_scope(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """A labelled experiment is allowed — it just is not the principal wallet."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'arena', 'paper', true, 1000)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "ws": wallet.workspace_id},
        )


async def test_the_app_role_cannot_delete_an_opened_wallet_even_with_the_marker(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``hunter_app`` holds ``DELETE`` on ``portfolios``; the trigger is the fix.

    The hole this closes: one ``DELETE FROM portfolios`` erases the wallet, the
    anchor and the peak, and the next request opens a fresh R$100.000 — the reset
    the directive forbids, reachable from a request handler. And a
    ``SET LOCAL`` marker authorises nobody, so the application role is refused
    *with* the marker set, not merely without it (Astra's counter-example).
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        await connection.execute(text(f"SET LOCAL {_TEARDOWN} = 'on'"))
        with pytest.raises(DBAPIError, match="may not be deleted by"):
            await connection.execute(
                text("DELETE FROM portfolios WHERE id = :id"), {"id": wallet.portfolio_id}
            )
    finally:
        await connection.rollback()
        await connection.close()


async def test_deleting_an_opened_wallet_without_the_marker_is_refused_for_the_owner(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Even the table owner has to declare a teardown. Removal is an act."""
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="may not be deleted by"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM portfolios WHERE id = :id"), {"id": wallet.portfolio_id}
            )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("is_arena", "true"),
        ("type", "'shadow'"),
        ("workspace_id", "gen_random_uuid()"),
        ("initial_capital", "999999"),
        ("base_currency", "'BRL'"),
    ],
)
async def test_an_opened_wallet_cannot_be_edited_out_of_its_own_scope(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet], column: str, value: str
) -> None:
    """The delete trigger alone would be defeated by an ``UPDATE``.

    Flip ``is_arena`` and the row leaves the partial unique index; a new
    principal wallet with a fresh R$100.000 can then be created and no ``DELETE``
    ever happened. Same for moving it to another workspace or rewriting the
    opening capital the anchor claims to describe.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="is anchored"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(f"UPDATE portfolios SET {column} = {value} WHERE id = :id"),  # noqa: S608
                {"id": wallet.portfolio_id},
            )


async def test_an_unanchored_portfolio_is_still_freely_editable(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The permanence trigger only binds a wallet that was actually opened."""
    wallet, _other = wallets
    experiment = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'exp', 'paper', true, 500)"
            ),
            {"id": experiment, "org": wallet.org_id, "ws": wallet.workspace_id},
        )
        await connection.execute(
            text("UPDATE portfolios SET initial_capital = 600 WHERE id = :id"), {"id": experiment}
        )
        await connection.execute(text("DELETE FROM portfolios WHERE id = :id"), {"id": experiment})


# --------------------------------------------------------------------------
# Immutability — evidence, not cache
# --------------------------------------------------------------------------


async def test_an_fx_observation_can_never_be_updated_or_deleted(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Refused for the *owner*, which is more than any ``REVOKE`` can promise."""
    wallet, _other = wallets
    for statement in (
        "UPDATE fx_observations SET rate = 1 WHERE id = :id",
        "DELETE FROM fx_observations WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="is immutable"):
            async with schema_engine.begin() as connection:
                await connection.execute(text(statement), {"id": wallet.fx_id})


async def test_the_currency_anchor_can_never_be_updated(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="is immutable"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE portfolio_currency_anchor SET credited_amount = 99 WHERE "
                    "portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )


async def test_the_anchor_rate_must_agree_with_the_observation_it_names(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The copied ``F0`` is what lets ``conversion_is_exact`` be a CHECK at all.

    A CHECK cannot reach another table, so the rate is duplicated onto the
    anchor — and a duplicate that may disagree with its source is worse than no
    duplicate, which is what the trigger closes.
    """
    wallet, _other = wallets
    portfolio = uuid7()
    with pytest.raises(DBAPIError, match="does not match fx_observation"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "is_arena, initial_capital) VALUES (:id, :org, :ws, 'x', 'paper', true, 1)"
                ),
                {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at) VALUES (:org, :pf, 1, :ts)"
                ),
                {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
                    "origin_amount, credited_amount, fx_observation_id, rate, "
                    "conversion_residual, rounding_policy) "
                    "VALUES (:id, :org, :pf, 10, 5, :fx, 2, 0, 'x')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": portfolio, "fx": wallet.fx_id},
            )


async def test_a_wallet_cannot_be_anchored_without_its_lock_row(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Opening is atomic: the anchor refuses a wallet with no risk state."""
    wallet, _other = wallets
    portfolio = uuid7()
    with pytest.raises(DBAPIError, match="has no portfolio_risk_state"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "is_arena, initial_capital) VALUES "
                    "(:id, :org, :ws, 'y', 'paper', true, 19999.9999999999)"
                ),
                {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
                    "origin_amount, credited_amount, fx_observation_id, rate, "
                    "conversion_residual, rounding_policy) VALUES "
                    "(:id, :org, :pf, 100000, 19999.9999999999, :fx, 5.0, 0.0000000005, 'p')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": portfolio, "fx": wallet.fx_id},
            )


async def test_the_peak_only_rises_and_the_admission_sequence_only_advances(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Drawdown is measured from the peak; lowering it erases a limit that fired."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        # The peak may only rise as far as the curve went (T3.1b, must-fix 5), so
        # the rise this test needs has to be an observation first.
        await connection.execute(
            text(
                "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                "realized_pnl_cum, peak_equity) VALUES "
                "(:org, :pf, '1m', :ts, 0, 25000, 0, 0, 0, 25000)"
            ),
            {"org": wallet.org_id, "pf": wallet.portfolio_id, "ts": _NOW},
        )
        await connection.execute(
            text("UPDATE portfolio_risk_state SET peak_equity = 25000 WHERE portfolio_id = :id"),
            {"id": wallet.portfolio_id},
        )
        await connection.execute(
            text("UPDATE portfolio_risk_state SET last_admission_seq = 3 WHERE portfolio_id = :id"),
            {"id": wallet.portfolio_id},
        )
    for statement, message in (
        (
            "UPDATE portfolio_risk_state SET peak_equity = 100 WHERE portfolio_id = :id",
            "would fall",
        ),
        (
            "UPDATE portfolio_risk_state SET last_admission_seq = 1 WHERE portfolio_id = :id",
            "would fall",
        ),
    ):
        with pytest.raises(DBAPIError, match=message):
            async with schema_engine.begin() as connection:
                await connection.execute(text(statement), {"id": wallet.portfolio_id})


async def test_the_risk_state_cannot_be_deleted_and_recreated_lower(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """A peak of 110 becoming 100 with no ``UPDATE`` ever happening."""
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="may not be deleted by"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM portfolio_risk_state WHERE portfolio_id = :id"),
                {"id": wallet.portfolio_id},
            )


# --------------------------------------------------------------------------
# market_betas — the archive, and which revision is in force
# --------------------------------------------------------------------------


async def _beta(
    connection: AsyncConnection,
    market: uuid.UUID,
    *,
    digest: str,
    as_of: datetime = _NOW,
) -> uuid.UUID:
    beta_id = uuid7()
    await connection.execute(
        text(
            "INSERT INTO market_betas (id, market_id, reference_market_id, as_of, window_start, "
            "window_end, input_start, valid_until, available_at, computed_at, beta_version, "
            "estimator, beta, n, contiguous_bars, valid, input_digest) VALUES "
            "(:id, :m, :m, :as_of, :ws, :we, :ins, :until, :as_of, :as_of, 'beta_v1', "
            "'ols_with_intercept', 1.25, 480, 480, true, :d)"
        ),
        {
            "id": beta_id,
            "m": market,
            "as_of": as_of,
            "ws": as_of - timedelta(days=30),
            "we": as_of - timedelta(hours=1),
            "ins": as_of - timedelta(days=30, hours=1),
            "until": as_of,
            "d": digest,
        },
    )
    return beta_id


async def test_only_one_beta_revision_per_cut_may_be_in_force(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """ "Current" is decided by the database, not by a reading convention.

    Writing a corrected revision without retiring the previous one in the same
    transaction is refused, so the ambiguity Astra named — a later revision that
    records *invalidity*, where filtering on ``valid`` resurrects the earlier
    one — cannot be represented at all.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        first = await _beta(connection, wallet.market_id, digest="digest-a")
    with pytest.raises(IntegrityError, match="uq_market_betas_current"):
        async with schema_engine.begin() as connection:
            await _beta(connection, wallet.market_id, digest="digest-b")
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("UPDATE market_betas SET superseded_at = :ts WHERE id = :id"),
            {"ts": _NOW, "id": first},
        )
        await _beta(connection, wallet.market_id, digest="digest-b")


async def test_a_beta_retry_with_the_same_inputs_is_a_no_op_not_a_new_revision(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``input_digest`` in the key is what separates a retry from a recomputation.

    ``computed_at`` — what the T3.7 sketch proposed — would have made a
    byte-identical rerun a brand new revision of the same cut.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await _beta(connection, wallet.market_id, digest="same")
    with pytest.raises(IntegrityError, match="uq_market_betas_revision"):
        async with schema_engine.begin() as connection:
            await _beta(connection, wallet.market_id, digest="same")


async def test_a_beta_revision_accepts_only_the_supersession_update(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The declared exception to "only INSERT", and nothing wider than it."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        beta_id = await _beta(connection, wallet.market_id, digest="one")

    with pytest.raises(DBAPIError, match="immutable except for"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE market_betas SET beta = 9, superseded_at = :ts WHERE id = :id"),
                {"ts": _NOW, "id": beta_id},
            )
    with pytest.raises(DBAPIError, match="is never deleted"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM market_betas WHERE id = :id"), {"id": beta_id}
            )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("UPDATE market_betas SET superseded_at = :ts WHERE id = :id"),
            {"ts": _NOW, "id": beta_id},
        )
    with pytest.raises(DBAPIError, match="already superseded"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE market_betas SET superseded_at = :ts WHERE id = :id"),
                {"ts": _NOW + timedelta(hours=1), "id": beta_id},
            )


async def test_the_temporal_read_returns_the_revision_that_was_in_force_then(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The canonical query of §18.6, on the scenario that broke the naive one.

    Revision A is available at 10:00 and a decision is taken at 10:05; revision B
    arrives at 10:10 and supersedes A. Asking again for 10:05 must still return
    A: ``superseded_at IS NULL`` alone would return nothing, because A is retired
    and B did not exist yet.
    """
    wallet, _other = wallets
    ten = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    async with schema_engine.begin() as connection:
        first = await _beta(connection, wallet.market_id, digest="a", as_of=ten)
        await connection.execute(
            text("UPDATE market_betas SET superseded_at = :ts WHERE id = :id"),
            {"ts": ten + timedelta(minutes=10), "id": first},
        )
        second = await _beta(
            connection, wallet.market_id, digest="b", as_of=ten + timedelta(minutes=10)
        )

    async with schema_engine.connect() as connection:
        chosen = await connection.scalar(
            text(
                "SELECT id FROM market_betas WHERE market_id = :m AND beta_version = 'beta_v1' "
                "AND available_at <= :t AND (superseded_at IS NULL OR superseded_at > :t) "
                "ORDER BY as_of DESC, available_at DESC, id DESC LIMIT 1"
            ),
            {"m": wallet.market_id, "t": ten + timedelta(minutes=5)},
        )
        assert chosen == first, "a historical replay must see the revision of its own moment"
        latest = await connection.scalar(
            text(
                "SELECT id FROM market_betas WHERE market_id = :m AND beta_version = 'beta_v1' "
                "AND available_at <= :t AND (superseded_at IS NULL OR superseded_at > :t) "
                "ORDER BY as_of DESC, available_at DESC, id DESC LIMIT 1"
            ),
            {"m": wallet.market_id, "t": ten + timedelta(hours=1)},
        )
        assert latest == second


# --------------------------------------------------------------------------
# Identity — composite keys and idempotency
# --------------------------------------------------------------------------


async def _proposal(connection: AsyncConnection, wallet: Wallet) -> uuid.UUID:
    proposal = uuid7()
    await connection.execute(
        text(
            "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
            "direction, idempotency_key) VALUES (:id, :org, :pf, :m, 'long', :key)"
        ),
        {
            "id": proposal,
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "m": wallet.market_id,
            "key": uuid.uuid4().hex,
        },
    )
    return proposal


async def test_an_order_cannot_claim_another_organizations_proposal(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """With a single-column FK the row is legal and RLS never looks at the parent."""
    first, second = wallets
    async with schema_engine.begin() as connection:
        foreign = await _proposal(connection, second)
    with pytest.raises(IntegrityError, match="fk_orders_proposal_id_trade_proposals"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO orders (id, organization_id, portfolio_id, proposal_id, "
                    "market_id, client_order_id, side, type, purpose, qty) VALUES "
                    "(:id, :org, :pf, :proposal, :m, :coid, 'buy', 'market', 'entry', 1)"
                ),
                {
                    "id": uuid7(),
                    "org": first.org_id,
                    "pf": first.portfolio_id,
                    "proposal": foreign,
                    "m": first.market_id,
                    "coid": uuid.uuid4().hex,
                },
            )


async def test_an_exit_intent_cannot_name_a_position_of_another_wallet_or_market(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Astra's counter-example: right position, wrong wallet and wrong market.

    Every single-column foreign key is satisfied; the worker locks the other
    wallet and holds the wrong market in collection. The quadruple makes it
    unrepresentable.
    """
    wallet, _other = wallets
    position = uuid7()
    other_market = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                "VALUES (:id, :exchange, :symbol, 'spot')"
            ),
            {
                "id": other_market,
                "exchange": wallet.exchange_id,
                "symbol": f"ETH{uuid.uuid4().hex[:6].upper()}",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 10, 100)"
            ),
            {
                "id": position,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "m": wallet.market_id,
            },
        )
    with pytest.raises(IntegrityError, match="fk_portfolio_exit_intents_position_id_positions"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                    "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                    "(:id, :org, :pf, :pos, :m, 'stop', 'stop', 10)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "pos": position,
                    "m": other_market,
                },
            )


async def test_two_take_profit_levels_coexist_but_two_stops_do_not(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """One live intention per *protection*, not per reason.

    A position of 10 with a target of 4 and a target of 6 is two ``target``
    intentions at different prices, and §10 never asks for a single target — it
    asks that the same unit is not sold twice, which the shared lock does. A
    second ``stop`` for the same position is a different thing and is refused.
    """
    wallet, _other = wallets
    position = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 10, 100)"
            ),
            {
                "id": position,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "m": wallet.market_id,
            },
        )
        for key, reason, qty in (("target:1", "target", 4), ("target:2", "target", 6)):
            await connection.execute(
                text(
                    "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                    "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                    "(:id, :org, :pf, :pos, :m, :reason, :key, :qty)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "pos": position,
                    "m": wallet.market_id,
                    "reason": reason,
                    "key": key,
                    "qty": qty,
                },
            )
        await connection.execute(
            text(
                "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                "(:id, :org, :pf, :pos, :m, 'stop', 'stop', 10)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "pos": position,
                "m": wallet.market_id,
            },
        )
    with pytest.raises(IntegrityError, match="uq_portfolio_exit_intents_live"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                    "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                    "(:id, :org, :pf, :pos, :m, 'stop', 'stop', 10)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "pos": position,
                    "m": wallet.market_id,
                },
            )


async def test_a_redelivered_execution_cannot_become_a_second_fill(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``execution_key`` is per tenant: two organizations may mint the same one."""
    first, second = wallets
    key = f"exec-{uuid.uuid4().hex}"

    async def place(wallet: Wallet) -> None:
        async with schema_engine.begin() as connection:
            order = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO orders (id, organization_id, portfolio_id, market_id, "
                    "client_order_id, side, type, purpose, qty) VALUES "
                    "(:id, :org, :pf, :m, :coid, 'buy', 'market', 'entry', 1)"
                ),
                {
                    "id": order,
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "m": wallet.market_id,
                    "coid": uuid.uuid4().hex,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO fills (id, organization_id, portfolio_id, order_id, "
                    "execution_key, qty, price) VALUES (:id, :org, :pf, :order, :key, 1, 100)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "order": order,
                    "key": key,
                },
            )

    await place(first)
    await place(second)  # same key, other tenant: legal
    with pytest.raises(IntegrityError, match="uq_fills_execution_key"):
        await place(first)


async def test_a_participation_execution_is_recorded_once_per_fill(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Idempotency by logical effect, so a replay cannot spend the minute twice."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        proposal = await _proposal(connection, wallet)
        await connection.execute(
            text(
                "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
                "market_id, proposal_id, kind, notional, occurred_at) VALUES "
                "(:id, :org, :pf, :m, :p, 'reserved', 80, :ts)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "m": wallet.market_id,
                "p": proposal,
                "ts": _NOW,
            },
        )
    with pytest.raises(IntegrityError, match="uq_participation_reserved"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
                    "market_id, proposal_id, kind, notional, occurred_at) VALUES "
                    "(:id, :org, :pf, :m, :p, 'reserved', 80, :ts)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "m": wallet.market_id,
                    "p": proposal,
                    "ts": _NOW,
                },
            )


@pytest.mark.parametrize(
    ("columns", "values", "constraint"),
    [
        (
            "reservation_state",
            "'held'",
            "ck_trade_proposals_a_reservation_is_quantified",
        ),
        (
            "reserved_slot",
            "true",
            "ck_trade_proposals_a_slot_is_held_or_gone",
        ),
        (
            "reserved_notional",
            "10",
            "ck_trade_proposals_an_unreserved_proposal_holds_nothing",
        ),
    ],
)
async def test_a_reservation_is_quantified_or_it_does_not_exist(
    schema_engine: AsyncEngine,
    wallets: tuple[Wallet, Wallet],
    columns: str,
    values: str,
    constraint: str,
) -> None:
    """Held means cash, risk and a deadline; a slot exists only while held."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        proposal = await _proposal(connection, wallet)
    with pytest.raises(IntegrityError, match=constraint):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(f"UPDATE trade_proposals SET {columns} = {values} WHERE id = :id"),  # noqa: S608
                {"id": proposal},
            )


async def test_leaving_a_blocked_kill_switch_needs_a_named_person(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """No automatic path can write the row that unblocks the wallet."""
    wallet, _other = wallets
    with pytest.raises(IntegrityError, match="resuming_a_block_is_authenticated"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                    "from_state, to_state, actor_type, evidence) VALUES "
                    "(:id, :org, 'portfolio', :pf, 'TRADING_DISABLED', 'ACTIVE', 'system', "
                    ":evidence)"
                ),
                # Carrying evidence on purpose, so the CHECK under test is the
                # only one that can fire: an automatic move with an empty
                # ``evidence`` is refused by a *different* constraint since T3.1b.
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "evidence": '{"daily_loss_pct": "0.005"}',
                },
            )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, actor_id, evidence) VALUES "
                "(:id, :org, 'portfolio', :pf, 'TRADING_DISABLED', 'ACTIVE', 'user', :actor, "
                ":evidence)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "actor": uuid7(),
                "evidence": '{"peak_equity": "19000", "daily_loss_pct": "0.021"}',
            },
        )


# --------------------------------------------------------------------------
# Isolation and privileges, proved as the role
# --------------------------------------------------------------------------


_TENANT_PROBES = (
    ("portfolio_currency_anchor", "portfolio_id"),
    ("portfolio_risk_state", "portfolio_id"),
)


@pytest.mark.parametrize(("table", "column"), _TENANT_PROBES)
async def test_org_a_cannot_read_org_b(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet], table: str, column: str
) -> None:
    """The isolation test, on the tables this revision adds."""
    first, second = wallets
    connection = await _as(schema_engine, _AS_APP, first.org_id)
    try:
        mine = await connection.scalar(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :pf"),  # noqa: S608
            {"pf": first.portfolio_id},
        )
        theirs = await connection.scalar(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :pf"),  # noqa: S608
            {"pf": second.portfolio_id},
        )
        assert mine == 1
        assert theirs == 0, f"{table} leaked another organization's row"
    finally:
        await connection.rollback()
        await connection.close()


async def test_without_current_org_the_new_tables_return_nothing(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """No setting means zero rows — never all rows (§15.4, the pooler's ``''``)."""
    connection = await _as(schema_engine, _AS_APP)
    try:
        for table, _column in _TENANT_PROBES:
            count = await connection.scalar(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            assert count == 0, f"{table} is readable without app.current_org"
    finally:
        await connection.rollback()
        await connection.close()


async def test_writing_another_orgs_row_fails_the_with_check(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    first, second = wallets
    connection = await _as(schema_engine, _AS_APP, first.org_id)
    try:
        with pytest.raises(ProgrammingError, match="row-level security"):
            await connection.execute(
                text(
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at) VALUES (:org, :pf, 1, now())"
                ),
                {"org": second.org_id, "pf": second.portfolio_id},
            )
    finally:
        await connection.rollback()
        await connection.close()


@pytest.mark.parametrize(
    ("statement", "table"),
    [
        ("UPDATE portfolio_currency_anchor SET rate = 1", "portfolio_currency_anchor"),
        ("DELETE FROM portfolio_currency_anchor", "portfolio_currency_anchor"),
        ("DELETE FROM participation_consumptions", "participation_consumptions"),
        ("UPDATE participation_consumptions SET notional = 1", "participation_consumptions"),
        ("DELETE FROM portfolio_exit_intents", "portfolio_exit_intents"),
        ("DELETE FROM portfolio_risk_state", "portfolio_risk_state"),
        (
            "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
            "VALUES (gen_random_uuid(), 'X', 1, 's', now(), now())",
            "fx_observations",
        ),
        ("UPDATE market_betas SET superseded_at = now()", "market_betas"),
    ],
)
async def test_the_app_role_is_refused_the_writes_the_classes_withhold(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet], statement: str, table: str
) -> None:
    """Run as ``hunter_app``, not asked of ``has_table_privilege``."""
    first, _second = wallets
    connection = await _as(schema_engine, _AS_APP, first.org_id)
    try:
        with pytest.raises(ProgrammingError, match=_DENIED):
            await connection.execute(text(statement))
    finally:
        await connection.rollback()
        await connection.close()


async def test_the_worker_can_write_the_two_global_archives(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The collectors' own role, including the supersession ``UPDATE``."""
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_WORKER)
    try:
        await connection.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
                "VALUES (gen_random_uuid(), 'USDTBRL', 5.5, 'binance.spot.ticker', now(), now())"
            )
        )
        beta_id = await _beta(connection, wallet.market_id, digest="worker")
        await connection.execute(
            text("UPDATE market_betas SET superseded_at = now() WHERE id = :id"), {"id": beta_id}
        )
    finally:
        await connection.rollback()
        await connection.close()


async def test_deleting_the_workspace_does_not_take_the_wallet_with_it(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The cascade Astra found, and the guard that closes it.

    ``hunter_app`` holds ``DELETE`` on ``workspaces`` and ``workspaces ->
    portfolios`` is ``ON DELETE CASCADE``. Reproduced before the fix: with the
    teardown marker set, ``DELETE FROM workspaces`` reported ``DELETE 1`` and
    the opened wallet was gone — because a referential action runs the cascading
    delete as the **owner** of the referencing table, so
    ``portfolios_permanence`` saw ``current_user = hunter`` and the role half of
    its check never applied. The guard now sits on the origin of the cascade,
    where the caller is still the caller.
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        await connection.execute(text(f"SET LOCAL {_TEARDOWN} = 'on'"))
        with pytest.raises(DBAPIError, match="holds an opened wallet"):
            await connection.execute(
                text("DELETE FROM workspaces WHERE id = :id"), {"id": wallet.workspace_id}
            )
    finally:
        await connection.rollback()
        await connection.close()


async def test_the_anchor_must_agree_with_the_capital_the_wallet_declares(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Two persisted sources may not disagree about the opening capital.

    ``portfolios.initial_capital`` and ``portfolio_currency_anchor.credited_amount``
    both claim to say what the wallet started with. A reconstruction that reads
    the first while the attribution reads the second starts from a number nobody
    credited (Astra, diff review).
    """
    wallet, _other = wallets
    portfolio = uuid7()
    with pytest.raises(DBAPIError, match="says it opened with"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "is_arena, initial_capital) VALUES (:id, :org, :ws, 'z', 'paper', true, 100)"
                ),
                {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at) VALUES (:org, :pf, 100, :ts)"
                ),
                {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
                    "origin_amount, credited_amount, fx_observation_id, rate, "
                    "conversion_residual, rounding_policy) "
                    "VALUES (:id, :org, :pf, 250, 50, :fx, 5, 0, 'floor_10dp_v1')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": portfolio, "fx": wallet.fx_id},
            )


async def test_participation_cannot_be_charged_to_the_wrong_market(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """An 80-USDT BTC execution booked against the ETH budget.

    Uniqueness per fill does not correct a wrong attribution: the 80 stay
    available to the next BTC entry, and the market's minute has been handed to
    another market (Astra, diff review). The ledger's foreign keys now pin the
    entry to the proposal's market.
    """
    wallet, _other = wallets
    other_market = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                "VALUES (:id, :exchange, :symbol, 'spot')"
            ),
            {
                "id": other_market,
                "exchange": wallet.exchange_id,
                "symbol": f"ETH{uuid.uuid4().hex[:6].upper()}",
            },
        )
        proposal = await _proposal(connection, wallet)
    with pytest.raises(
        IntegrityError, match="fk_participation_consumptions_proposal_id_trade_proposals"
    ):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
                    "market_id, proposal_id, kind, notional, occurred_at) VALUES "
                    "(:id, :org, :pf, :m, :p, 'reserved', 80, :ts)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "m": other_market,
                    "p": proposal,
                    "ts": _NOW,
                },
            )


async def test_the_kill_switch_state_cannot_move_without_an_audited_transition(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The CHECK guards the history; this guards the column the workers read.

    ``UPDATE portfolios SET kill_switch_state = 'ACTIVE'`` on a blocked wallet
    was a complete, silent unblock: no row, no actor, no evidence (Astra, diff
    review). The deferred constraint trigger makes the state and its explanation
    inseparable, which is what makes the CHECK on transitions bite here too.
    """
    wallet, _other = wallets

    async def move(to_state: str, *, audited: bool, actor: str = "user") -> None:
        async with schema_engine.begin() as connection:
            current = await connection.scalar(
                text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = :to WHERE id = :id"),
                {"to": to_state, "id": wallet.portfolio_id},
            )
            if audited:
                await connection.execute(
                    text(
                        "INSERT INTO kill_switch_transitions (id, organization_id, scope, "
                        "scope_id, from_state, to_state, actor_type, actor_id, evidence) VALUES "
                        "(:id, :org, 'portfolio', :pf, :frm, :to, :actor, :actor_id, :evidence)"
                    ),
                    {
                        "id": uuid7(),
                        "org": wallet.org_id,
                        "pf": wallet.portfolio_id,
                        "frm": current,
                        "to": to_state,
                        "actor": actor,
                        "actor_id": uuid7() if actor == "user" else None,
                        "evidence": '{"daily_loss_pct": "0.021"}',
                    },
                )

    await move("TRADING_DISABLED", audited=True, actor="system")
    with pytest.raises(DBAPIError, match="without an audited transition"):
        await move("ACTIVE", audited=False)
    # and the audited resumption still has to name a person, by the CHECK
    with pytest.raises(IntegrityError, match="resuming_a_block_is_authenticated"):
        await move("ACTIVE", audited=True, actor="system")
    await move("ACTIVE", audited=True)


async def test_a_protection_can_be_substituted_under_the_same_key(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The deferred successor FK is what makes the substitution writable.

    Replacing A with B under the same ``protection_key`` has no legal order
    while the FK is immediate: inserting B first hits the live partial unique,
    and retiring A first points at a B that does not exist. Deferred to COMMIT,
    the protocol is retire-then-insert, using B's application-generated id.
    """
    wallet, _other = wallets
    position, first, second = uuid7(), uuid7(), uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 10, 100)"
            ),
            {
                "id": position,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "m": wallet.market_id,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                "(:id, :org, :pf, :pos, :m, 'stop', 'stop', 10)"
            ),
            {
                "id": first,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "pos": position,
                "m": wallet.market_id,
            },
        )

    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE portfolio_exit_intents SET state = 'superseded', "
                "superseded_by_id = :second, closed_at = now(), closed_reason = 'stop moved' "
                "WHERE id = :first"
            ),
            {"second": second, "first": first},
        )
        await connection.execute(
            text(
                "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                "position_id, market_id, reason, protection_key, intended_qty, trigger_price) "
                "VALUES (:id, :org, :pf, :pos, :m, 'stop', 'stop', 10, 95)"
            ),
            {
                "id": second,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "pos": position,
                "m": wallet.market_id,
            },
        )

    async with schema_engine.connect() as connection:
        live = await connection.scalar(
            text(
                "SELECT id FROM portfolio_exit_intents WHERE position_id = :pos "
                "AND state IN ('open', 'blocked_residual')"
            ),
            {"pos": position},
        )
    assert live == second, "the successor is the live protection"


# --------------------------------------------------------------------------
# T3.1b — the security review of `11faba8`, one test per finding
#
# Every one of these ran green against the revision as written: what they assert
# is a refusal the database did not make. They are here as regressions, and the
# docstring of each names the finding and the scenario it reproduced.
# --------------------------------------------------------------------------


async def _latch(engine: AsyncEngine, wallet: Wallet, to_state: str, *, actor: str) -> None:
    """Move the wallet's kill switch the audited way: one row, one column, one
    transaction — which is exactly what the guard now requires."""
    async with engine.begin() as connection:
        current = await connection.scalar(
            text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, actor_id, evidence) VALUES "
                "(:id, :org, 'portfolio', :pf, :frm, :to, :actor, :actor_id, :evidence)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "frm": current,
                "to": to_state,
                "actor": actor,
                "actor_id": uuid7() if actor == "user" else None,
                "evidence": '{"equity": "18000", "peak_equity": "20000"}',
            },
        )
        await connection.execute(
            text("UPDATE portfolios SET kill_switch_state = :to WHERE id = :id"),
            {"to": to_state, "id": wallet.portfolio_id},
        )


async def test_a_banked_transition_cannot_unlock_the_wallet_a_second_time(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **blocking 1** — two full cycles, then the bare UPDATE.

    The guard asked ``EXISTS`` on ``(scope, scope_id, organization_id,
    from_state, to_state)`` with no notion of *when*. So the first honest
    resumption minted the pair ``(TRADING_DISABLED, ACTIVE)`` and from then on
    ``UPDATE portfolios SET kill_switch_state = 'ACTIVE'`` was a complete, silent
    unblock — reproduced as three transitions covering four movements.

    Two cycles is the smallest test that sees it: the first is honest, and the
    second is where the banked row would be spent.
    """
    wallet, _other = wallets
    await _latch(schema_engine, wallet, "TRADING_DISABLED", actor="system")
    await _latch(schema_engine, wallet, "ACTIVE", actor="user")
    await _latch(schema_engine, wallet, "TRADING_DISABLED", actor="system")

    with pytest.raises(DBAPIError, match="without an audited transition"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = 'ACTIVE' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )

    async with schema_engine.connect() as connection:
        state = await connection.scalar(
            text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
        moves = await connection.scalar(
            text("SELECT count(*) FROM kill_switch_transitions WHERE scope_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
    assert state == "TRADING_DISABLED", "the wallet stayed latched"
    assert moves == 3, "three transitions, three movements — never four movements for three"

    await _latch(schema_engine, wallet, "ACTIVE", actor="user")


async def test_a_transition_banked_in_an_earlier_transaction_is_refused(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **blocking 1, the nonexistent-actor variant**.

    ``actor_id`` has no foreign key on purpose (a user removed later must not
    invalidate the trail), so nothing stops a row ``EMERGENCY -> ACTIVE``
    attributed to a UUID that was never a user. Written **once**, it satisfied
    the old ``EXISTS`` for ever. Being the newest transition of the scope is not
    enough on its own either — this test banks the row *after* the latch, so it
    is the newest one, and it is still refused because it belongs to another
    transaction.
    """
    wallet, _other = wallets
    await _latch(schema_engine, wallet, "EMERGENCY", actor="system")
    ghost = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, actor_id) VALUES "
                "(:id, :org, 'portfolio', :pf, 'EMERGENCY', 'ACTIVE', 'user', :ghost)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "pf": wallet.portfolio_id, "ghost": ghost},
        )
    async with schema_engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT count(*) FROM users WHERE id = :id"), {"id": ghost}
        )
    assert exists == 0, "the actor this row names never existed, and the schema allows that"

    with pytest.raises(DBAPIError, match="written by an earlier transaction"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = 'ACTIVE' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )


async def test_an_organization_cannot_move_its_kill_switch_unaudited(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 3** — the org scope had no guard at all.

    ``organizations.kill_switch_state`` is read as blocking by the API
    (``radar_org_derivation.py``), and only ``portfolios`` carried the constraint
    trigger, so an organization-wide block could be lifted with one ``UPDATE``
    and no history whatsoever.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="without an audited transition"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE organizations SET kill_switch_state = 'EMERGENCY' WHERE id = :id"),
                {"id": wallet.org_id},
            )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, evidence) VALUES "
                "(:id, :org, 'organization', :org, 'ACTIVE', 'EMERGENCY', 'system', :evidence)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "evidence": '{"drawdown_pct": "0.09"}'},
        )
        await connection.execute(
            text("UPDATE organizations SET kill_switch_state = 'EMERGENCY' WHERE id = :id"),
            {"id": wallet.org_id},
        )
    with pytest.raises(DBAPIError, match="without an audited transition"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE organizations SET kill_switch_state = 'ACTIVE' WHERE id = :id"),
                {"id": wallet.org_id},
            )


async def test_a_new_workspace_does_not_free_a_second_principal_wallet(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **blocking 2** — reproduced end to end as ``hunter_app``.

    The application role holds ``INSERT`` on ``workspaces`` and on
    ``portfolios``: it created a workspace, a wallet, a lock row and an anchor
    with R$100.000 of new money, and no ``DELETE`` and no audit entry ever
    happened, because the unique index was keyed on the pair the second insert
    changed.
    """
    wallet, _other = wallets
    second_workspace = uuid7()
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, 'a second workspace', 'paper_trading')"
            ),
            {"id": second_workspace, "org": wallet.org_id},
        )
        with pytest.raises(IntegrityError, match="uq_portfolios_principal_paper"):
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "initial_capital) VALUES (:id, :org, :ws, 'second', 'paper', 100000)"
                ),
                {"id": uuid7(), "org": wallet.org_id, "ws": second_workspace},
            )
    finally:
        await connection.rollback()
        await connection.close()


@pytest.mark.parametrize(
    ("table", "columns", "constraint"),
    [
        (
            "orders",
            "(id, organization_id, portfolio_id, market_id, position_id, client_order_id, "
            "side, type, purpose, qty) VALUES (:id, :org, :pf, :m, :pos, :key, 'sell', "
            "'market', 'exit', 1)",
            "fk_orders_position_id_positions",
        ),
        (
            "trades",
            "(id, organization_id, portfolio_id, market_id, position_id, execution_mode, "
            "direction, entry_price, exit_price, qty, pnl, opened_at, closed_at) VALUES "
            "(:id, :org, :pf, :m, :pos, 'paper', 'long', 100, 110, 1, 10, now(), now())",
            "fk_trades_position_id_positions",
        ),
    ],
)
async def test_a_row_cannot_claim_another_organizations_position(
    schema_engine: AsyncEngine,
    wallets: tuple[Wallet, Wallet],
    table: str,
    columns: str,
    constraint: str,
) -> None:
    """Security review, **must-fix 4** — ``position_id`` was a bare foreign key.

    ``orders`` and ``trades`` both pointed at ``positions(id)`` alone, so an
    order (or the closed-trade row analytics treats as the truth) could name
    another organization's position: the foreign key was satisfied and RLS only
    ever reads the row's own ``organization_id``.
    """
    first, second = wallets
    foreign_position = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 10, 100)"
            ),
            {
                "id": foreign_position,
                "org": second.org_id,
                "pf": second.portfolio_id,
                "m": second.market_id,
            },
        )
    with pytest.raises(IntegrityError, match=constraint):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(f"INSERT INTO {table} {columns}"),
                {
                    "id": uuid7(),
                    "org": first.org_id,
                    "pf": first.portfolio_id,
                    "m": first.market_id,
                    "pos": foreign_position,
                    "key": uuid.uuid4().hex,
                },
            )


async def test_a_trade_cannot_claim_another_organizations_proposal(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 4**, the ``trades.proposal_id`` half.

    ``orders`` got the composite key in ``0006``; ``trades`` kept the
    single-column one, so the row that explains a realised PnL could cite a
    decision belonging to another tenant, another wallet or another market.
    """
    first, second = wallets
    async with schema_engine.begin() as connection:
        foreign = await _proposal(connection, second)
    with pytest.raises(IntegrityError, match="fk_trades_proposal_id_trade_proposals"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO trades (id, organization_id, portfolio_id, market_id, "
                    "proposal_id, execution_mode, direction, entry_price, exit_price, qty, "
                    "pnl, opened_at, closed_at) VALUES (:id, :org, :pf, :m, :proposal, 'paper', "
                    "'long', 100, 110, 1, 10, now(), now())"
                ),
                {
                    "id": uuid7(),
                    "org": first.org_id,
                    "pf": first.portfolio_id,
                    "m": first.market_id,
                    "proposal": foreign,
                },
            )


async def test_an_exit_attempt_and_its_intention_must_name_the_same_position(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 4**, the last half: the two could disagree.

    ``exit_intent_id`` carried the quadruple and ``position_id`` carried
    nothing, so both were satisfiable by *different* positions of the same wallet
    and market: the fill would reduce one position while the intention's
    ``filled_qty`` credited the protection of another — six units silently
    unprotected, which is the whole point of §10.
    """
    wallet, _other = wallets
    protected, other_position, intent = uuid7(), uuid7(), uuid7()
    async with schema_engine.begin() as connection:
        for position in (protected, other_position):
            await connection.execute(
                text(
                    "INSERT INTO positions (id, organization_id, portfolio_id, market_id, "
                    "direction, qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 10, 100)"
                ),
                {
                    "id": position,
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "m": wallet.market_id,
                },
            )
        await connection.execute(
            text(
                "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, "
                "position_id, market_id, reason, protection_key, intended_qty) VALUES "
                "(:id, :org, :pf, :pos, :m, 'stop', 'stop', 10)"
            ),
            {
                "id": intent,
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "pos": protected,
                "m": wallet.market_id,
            },
        )

    def _order(position: uuid.UUID | None) -> dict[str, object]:
        return {
            "id": uuid7(),
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "m": wallet.market_id,
            "intent": intent,
            "pos": position,
            "key": uuid.uuid4().hex,
        }

    statement = text(
        "INSERT INTO orders (id, organization_id, portfolio_id, market_id, exit_intent_id, "
        "position_id, client_order_id, side, type, purpose, qty) VALUES "
        "(:id, :org, :pf, :m, :intent, :pos, :key, 'sell', 'market', 'exit', 4)"
    )
    with pytest.raises(IntegrityError, match="fk_orders_exit_intent_matches_position"):
        async with schema_engine.begin() as connection:
            await connection.execute(statement, _order(other_position))
    with pytest.raises(IntegrityError, match="an_exit_attempt_names_its_position"):
        async with schema_engine.begin() as connection:
            await connection.execute(statement, _order(None))
    async with schema_engine.begin() as connection:
        await connection.execute(statement, _order(protected))


async def test_the_app_role_can_lock_the_wallet_row_and_never_write_it(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 5** — and the ``0005`` lesson, kept.

    ``hunter_app`` held ``SELECT``/``INSERT``/``UPDATE`` on the lock row, so a
    request handler could rewrite ``trading_day`` and ``equity_day_start`` (an
    accounting reset that zeroes the day's loss) or write ``peak_equity =
    999999`` and latch the wallet in a permanent drawdown. It cannot simply lose
    ``UPDATE``: PostgreSQL charges ``ACL_UPDATE`` for ``SELECT ... FOR UPDATE``
    and that lock is what T3.6's resume takes on the way in (§17.2).

    What it has instead is ``UPDATE (updated_at)`` — measured to be exactly
    enough for the row mark and not enough to write a value (Astra's proposal in
    the T3.1b diff review, which is also what makes the guard survive role
    inheritance, since a privilege is inherited and a name is not). All three
    layers are asserted here, as the role: the lock works, the privilege refuses
    a risk column, and the trigger refuses even the column the grant allows.
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        locked = await connection.scalar(
            text(
                "SELECT peak_equity FROM portfolio_risk_state WHERE portfolio_id = :id FOR UPDATE"
            ),
            {"id": wallet.portfolio_id},
        )
        assert locked is not None, "the wallet lock is what serialises every evaluation"
    finally:
        await connection.rollback()
        await connection.close()

    for statement, message in (
        (
            "UPDATE portfolio_risk_state SET peak_equity = 999999 WHERE portfolio_id = :id",
            _DENIED,
        ),
        (
            "UPDATE portfolio_risk_state SET equity_day_start = 1, "
            "day_reference_observed_at = now() WHERE portfolio_id = :id",
            _DENIED,
        ),
        (
            "UPDATE portfolio_risk_state SET last_admission_seq = 9 WHERE portfolio_id = :id",
            _DENIED,
        ),
        # The one column the grant does allow, so this is the trigger speaking.
        (
            "UPDATE portfolio_risk_state SET updated_at = now() WHERE portfolio_id = :id",
            "may not be updated by",
        ),
    ):
        connection = await _as(schema_engine, _AS_APP, wallet.org_id)
        try:
            with pytest.raises(DBAPIError, match=message):
                await connection.execute(text(statement), {"id": wallet.portfolio_id})
        finally:
            await connection.rollback()
            await connection.close()


async def test_a_role_that_merely_inherits_the_app_cannot_write_the_lock_row_either(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Astra's escape from the T3.1b diff review, closed twice over.

    The first fix compared ``current_user = 'hunter_app'``. A login that merely
    *inherits* ``hunter_app`` keeps every privilege of the role while reporting
    its own name, so the guard did not recognise it and the peak went to 999999.
    Two things close it and both are asserted: the privilege it inherits is now
    ``UPDATE (updated_at)`` and nothing more, and the trigger asks
    ``pg_has_role`` instead of comparing a string.
    """
    wallet, _other = wallets
    probe = f"probe_inherits_{uuid.uuid4().hex[:8]}"
    async with schema_engine.begin() as connection:
        await connection.execute(text(f"CREATE ROLE {probe} NOLOGIN INHERIT"))
        await connection.execute(text(f"GRANT hunter_app TO {probe}"))
    try:
        connection = await _as(schema_engine, text(f"SET LOCAL ROLE {probe}"), wallet.org_id)
        try:
            with pytest.raises(DBAPIError, match=_DENIED):
                await connection.execute(
                    text(
                        "UPDATE portfolio_risk_state SET peak_equity = 999999 "
                        "WHERE portfolio_id = :id"
                    ),
                    {"id": wallet.portfolio_id},
                )
        finally:
            await connection.rollback()
            await connection.close()
        connection = await _as(schema_engine, text(f"SET LOCAL ROLE {probe}"), wallet.org_id)
        try:
            with pytest.raises(DBAPIError, match="may not be updated by"):
                await connection.execute(
                    text(
                        "UPDATE portfolio_risk_state SET updated_at = now() "
                        "WHERE portfolio_id = :id"
                    ),
                    {"id": wallet.portfolio_id},
                )
        finally:
            await connection.rollback()
            await connection.close()
    finally:
        async with schema_engine.begin() as connection:
            await connection.execute(text(f"REVOKE hunter_app FROM {probe}"))
            await connection.execute(text(f"DROP ROLE {probe}"))


async def test_a_data_modifying_cte_cannot_open_a_wallet_ahead_of_its_own_capital(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Astra's second escape: write the child before the parent, in one statement.

    With the ceiling checked ``BEFORE INSERT`` the wallet did not exist yet, the
    guard had nothing to compare against and skipped; the foreign key, verified
    at the *end* of the statement, found the parent already there and was happy.
    Result: capital 20.000 and a peak of 999.999, as ``hunter_app``. The check is
    now a deferred constraint trigger, so it runs when the whole picture exists.
    """
    wallet, _other = wallets
    portfolio = uuid7()
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        with pytest.raises(DBAPIError, match="above every equity this wallet has shown"):
            await connection.execute(
                text(
                    "WITH child AS ("
                    "  INSERT INTO portfolio_risk_state "
                    "    (organization_id, portfolio_id, peak_equity, peak_equity_at) "
                    "  VALUES (:org, :pf, 999999, now()) RETURNING portfolio_id) "
                    "INSERT INTO portfolios "
                    "  (id, organization_id, workspace_id, name, type, is_arena, "
                    "   initial_capital) "
                    "SELECT portfolio_id, :org, :ws, 'cte', 'paper', true, 20000 FROM child"
                ),
                {"org": wallet.org_id, "pf": portfolio, "ws": wallet.workspace_id},
            )
            # The statement itself succeeds — that is the point of the escape.
            # The refusal is at COMMIT, which is where the deferred trigger can
            # finally see the wallet the CTE wrote after its own lock row.
            await connection.commit()
    finally:
        await connection.rollback()
        await connection.close()


async def test_the_day_reference_cannot_vouch_for_the_peak_it_is_written_with(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Astra's third escape: one statement declaring its own ceiling.

    ``NEW.equity_day_start`` was inside the ``greatest`` that bounds the peak, so
    an ``INSERT`` carrying ``peak_equity = 999999`` *and* ``equity_day_start =
    999999`` passed with no snapshot at all — the wallet born in a fictional 98 %
    drawdown, which monotonicity then makes permanent. Both columns are equities
    of the same wallet: both are capped by what it showed, neither vouches for
    the other.
    """
    wallet, _other = wallets
    portfolio = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'vouch', 'paper', true, 20000)"
            ),
            {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
        )
    with pytest.raises(DBAPIError, match="above every equity this wallet has shown"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at, trading_day, trading_day_start_utc, "
                    "equity_day_start, day_reference_observed_at) VALUES "
                    "(:org, :pf, 999999, :ts, '2026-09-06', :ts, 999999, :ts)"
                ),
                {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
            )
    # The same statement with a reference the wallet really has is legal.
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                "peak_equity, peak_equity_at, trading_day, trading_day_start_utc, "
                "equity_day_start, day_reference_observed_at) VALUES "
                "(:org, :pf, 20000, :ts, '2026-09-06', :ts, 20000, :ts)"
            ),
            {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
        )


async def test_the_peak_may_not_be_set_above_the_equity_that_was_observed(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 5** — the peak is a measurement, not a setting.

    ``peak_equity`` only had to rise, so writing 999999 latched the wallet into a
    drawdown of 98 % that nothing could ever undo: the peak never comes back
    down. "Observed" is defined as the largest ``portfolio_equity_snapshots``
    equity for the wallet, or the day reference, or the peak it already carries.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="above every equity observed"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE portfolio_risk_state SET peak_equity = 999999 WHERE portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                "realized_pnl_cum, peak_equity) VALUES "
                "(:org, :pf, '1m', :ts, 0, 25000, 0, 0, 0, 25000)"
            ),
            {"org": wallet.org_id, "pf": wallet.portfolio_id, "ts": _NOW},
        )
        await connection.execute(
            text("UPDATE portfolio_risk_state SET peak_equity = 25000 WHERE portfolio_id = :id"),
            {"id": wallet.portfolio_id},
        )
    with pytest.raises(DBAPIError, match="above every equity observed"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE portfolio_risk_state SET peak_equity = 25000.0000000001 "
                    "WHERE portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )


async def test_a_wallet_cannot_open_with_a_peak_it_never_reached(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The same ceiling on ``INSERT``: the guard was ``UPDATE``-only.

    Refusing only the ``UPDATE`` would leave the identical latch one statement
    away, because ``hunter_app`` writes this row when the wallet opens.
    """
    wallet, _other = wallets
    portfolio = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'peaky', 'paper', true, 1000)"
            ),
            {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
        )
    with pytest.raises(DBAPIError, match="above every equity this wallet has shown"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at) VALUES (:org, :pf, 999999, :ts)"
                ),
                {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
            )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                "peak_equity, peak_equity_at) VALUES (:org, :pf, 1000, :ts)"
            ),
            {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
        )


async def test_the_trading_day_only_advances_and_its_reference_is_set_once(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 5** — rewriting either is an accounting reset.

    ``trading_day`` going backwards re-opens a day whose loss was already
    counted; ``equity_day_start`` rewritten inside the same day re-bases today's
    loss on a number chosen *after* the loss. Unknown to known stays allowed —
    that is the reference becoming available, which §18.7 requires to be
    representable.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE portfolio_risk_state SET trading_day = '2026-09-06', "
                "trading_day_start_utc = :ts, equity_day_start = 19000, "
                "day_reference_observed_at = :ts WHERE portfolio_id = :id"
            ),
            {"ts": _NOW, "id": wallet.portfolio_id},
        )
    for statement, message in (
        (
            "UPDATE portfolio_risk_state SET trading_day = '2026-09-05', "
            "trading_day_start_utc = :ts WHERE portfolio_id = :id",
            "would move from",
        ),
        (
            "UPDATE portfolio_risk_state SET trading_day = NULL, "
            "trading_day_start_utc = NULL, equity_day_start = NULL, "
            "day_reference_observed_at = NULL WHERE portfolio_id = :id",
            "would move from",
        ),
        (
            "UPDATE portfolio_risk_state SET equity_day_start = 1 WHERE portfolio_id = :id",
            "is set once per trading day",
        ),
        (
            "UPDATE portfolio_risk_state SET day_reference_observed_at = :ts2 "
            "WHERE portfolio_id = :id",
            "is set once per trading day",
        ),
    ):
        with pytest.raises(DBAPIError, match=message):
            async with schema_engine.begin() as connection:
                await connection.execute(
                    text(statement),
                    {"ts": _NOW, "ts2": _NOW + timedelta(hours=1), "id": wallet.portfolio_id},
                )
    # The turn of the day is exactly when a new reference is legal.
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE portfolio_risk_state SET trading_day = '2026-09-07', "
                "trading_day_start_utc = :ts, equity_day_start = 18000, "
                "day_reference_observed_at = :ts WHERE portfolio_id = :id"
            ),
            {"ts": _NOW + timedelta(days=1), "id": wallet.portfolio_id},
        )


async def test_an_anchor_refuses_an_observation_of_another_currency_pair(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **must-fix 6** — "R$1,2 bilhão", and it would be permanent.

    ``conversion_is_exact`` only proves the arithmetic is internally consistent.
    An anchor naming a ``BTCUSDT`` observation at 60000 and copying that rate
    satisfies it perfectly, opens the wallet with a credited amount nobody
    credited, and the anchor is immutable — so the error can never be corrected.
    The pair is ``operating_currency || origin_currency``.
    """
    wallet, _other = wallets
    portfolio, wrong_pair = uuid7(), uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
                "VALUES (:id, 'BTCUSDT', 60000, :source, :ts, :ts)"
            ),
            {"id": wrong_pair, "ts": _NOW, "source": f"btc.ticker#{wallet.slug}"},
        )
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES "
                "(:id, :org, :ws, 'fx', 'paper', true, 1.6666666667)"
            ),
            {"id": portfolio, "org": wallet.org_id, "ws": wallet.workspace_id},
        )
        await connection.execute(
            text(
                "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, peak_equity, "
                "peak_equity_at) VALUES (:org, :pf, 1.6666666667, :ts)"
            ),
            {"org": wallet.org_id, "pf": portfolio, "ts": _NOW},
        )
    with pytest.raises(DBAPIError, match="on pair BTCUSDT"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
                    "origin_amount, credited_amount, fx_observation_id, rate, "
                    "conversion_residual, rounding_policy) VALUES "
                    "(:id, :org, :pf, 100000, 1.6666666667, :fx, 60000, 0.0002, 'floor_10dp_v1')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": portfolio, "fx": wrong_pair},
            )


async def test_a_participation_release_cannot_exceed_its_own_reservation(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **suggestion 8** — ``notional > 0`` was the only bound.

    The budget is ``Σ(reserved − executed − released)``, so a release of 900
    against a reservation of 80 handed the market 820 USDT of a minute it never
    had. A CHECK cannot reach ``trade_proposals``, hence the trigger.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        proposal = await _proposal(connection, wallet)
        await connection.execute(
            text(
                "UPDATE trade_proposals SET reservation_state = 'held', reserved_notional = 80, "
                "reserved_cash = 80.1, reserved_risk = 2, reserved_until = :until WHERE id = :id"
            ),
            {"until": _NOW + timedelta(minutes=5), "id": proposal},
        )

    def _entry(notional: int) -> dict[str, object]:
        return {
            "id": uuid7(),
            "org": wallet.org_id,
            "pf": wallet.portfolio_id,
            "m": wallet.market_id,
            "p": proposal,
            "n": notional,
            "ts": _NOW,
        }

    statement = text(
        "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, market_id, "
        "proposal_id, kind, notional, occurred_at) VALUES "
        "(:id, :org, :pf, :m, :p, 'released', :n, :ts)"
    )
    with pytest.raises(DBAPIError, match="is larger than the"):
        async with schema_engine.begin() as connection:
            await connection.execute(statement, _entry(900))
    async with schema_engine.begin() as connection:
        await connection.execute(statement, _entry(50))


async def test_a_release_against_a_proposal_that_reserved_nothing_is_refused(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The other half of suggestion 8: there is nothing to give back."""
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        proposal = await _proposal(connection, wallet)
    with pytest.raises(DBAPIError, match="never quantified a reservation"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
                    "market_id, proposal_id, kind, notional, occurred_at) VALUES "
                    "(:id, :org, :pf, :m, :p, 'released', 10, :ts)"
                ),
                {
                    "id": uuid7(),
                    "org": wallet.org_id,
                    "pf": wallet.portfolio_id,
                    "m": wallet.market_id,
                    "p": proposal,
                    "ts": _NOW,
                },
            )


async def test_an_automatic_transition_must_carry_its_evidence(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **suggestion 9**.

    A ``system`` row has ``actor_id IS NULL`` by definition and ``reason`` is
    prose, so ``evidence`` is the only thing on it that says *why* the wallet was
    latched. Empty, the row records that something happened and nothing about
    what.
    """
    wallet, _other = wallets
    with pytest.raises(IntegrityError, match="an_automatic_move_shows_its_numbers"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                    "from_state, to_state, actor_type) VALUES "
                    "(:id, :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', 'system')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": wallet.portfolio_id},
            )
    # A person may still move it without numbers: they are the evidence.
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, actor_id) VALUES "
                "(:id, :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', 'user', :actor)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "pf": wallet.portfolio_id, "actor": uuid7()},
        )


async def test_the_kill_switch_trail_outlives_the_tenant(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review, **suggestion 10** — the teardown erased the latch.

    ``app.portfolio_teardown`` is a ``SET LOCAL`` any role can write, and with
    the cascading foreign key in place ``DELETE FROM organizations`` took the
    kill-switch history with it: latching a wallet and then removing the tenant
    was a way to make the latch never have happened. ``audit_logs`` has had no
    foreign key here since ``0001`` for the same reason (§15.4); the orphan is
    deliberate and RLS is what keeps it unreadable.
    """
    wallet, _other = wallets
    await _latch(schema_engine, wallet, "TRADING_DISABLED", actor="system")
    async with schema_engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL {_TEARDOWN} = 'on'"))
        await connection.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": wallet.org_id}
        )
    async with schema_engine.connect() as connection:
        survived = await connection.scalar(
            text("SELECT count(*) FROM kill_switch_transitions WHERE organization_id = :org"),
            {"org": wallet.org_id},
        )
        gone = await connection.scalar(
            text("SELECT count(*) FROM portfolios WHERE id = :pf"), {"pf": wallet.portfolio_id}
        )
    assert survived == 1, "the record of a latched kill switch is not the tenant's to delete"
    assert gone == 0, "the tenant itself did go"


async def test_the_teardown_orphan_is_still_invisible_to_every_other_tenant(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The price of suggestion 10, paid where it is safe to pay it.

    Dropping the foreign key leaves rows whose ``organization_id`` names nothing.
    ``tenant_isolation`` filters on that column and not on the referenced row, so
    an orphan is readable by exactly nobody — which is the RLS half of the
    isolation test, on the table the trail lives in.
    """
    first, second = wallets
    await _latch(schema_engine, first, "TRADING_DISABLED", actor="system")
    async with schema_engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL {_TEARDOWN} = 'on'"))
        await connection.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": first.org_id}
        )
    connection = await _as(schema_engine, _AS_APP, second.org_id)
    try:
        theirs = await connection.scalar(
            text("SELECT count(*) FROM kill_switch_transitions WHERE organization_id = :org"),
            {"org": first.org_id},
        )
        assert theirs == 0, "an orphaned trail leaked to another organization"
    finally:
        await connection.rollback()
        await connection.close()


def _shipped_paper_limits() -> dict[str, Any]:
    """``infra/scripts/seed_reference.PAPER_V1_LIMITS``, loaded as the seed loads it.

    By path and not by ``import``, for the reason
    ``test_schema_seed_and_partitions._load_script`` records: ``infra/scripts``
    is on ``sys.path`` when the seed runs as a script and is not a package
    anywhere else.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "hunter_infra_seed_reference", SCRIPTS_DIR / "seed_reference.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    limits: dict[str, Any] = module.PAPER_V1_LIMITS
    return limits


def test_the_seeded_paper_profile_has_exactly_one_source() -> None:
    """Security review, **must-fix 7** — the seed and the engine had drifted.

    ``RiskLimits.model_validate(profile.limits)`` failed with ten errors against
    the row the seed writes: six keys the engine requires were missing
    (``max_entry_deviation_pct`` and the four input ages of v2.1, plus
    ``day_timezone``) and four it forbids were present. This loads both and
    compares the serialised bytes, so an edit to either has to move both.
    """
    shipped = _shipped_paper_limits()
    assert json.dumps(shipped, sort_keys=True) == json.dumps(
        PAPER_V1.model_dump(mode="json"), sort_keys=True
    ), "the seed and the engine disagree about paper_v1"
    assert RiskLimits.model_validate(shipped) == PAPER_V1
    # And the directive's numbers are unchanged by the derivation.
    assert shipped["risk_per_trade_pct"] == "0.0025"
    assert shipped["max_participation_pct"] == "0.01"
    assert shipped["max_total_exposure_pct"] == "0.40"
    assert shipped["max_concurrent_positions"] == 5


# --------------------------------------------------------------------------
# T3.1c — the role model: the engine decides, the API asks (§19)
# --------------------------------------------------------------------------


async def test_the_engine_writes_a_whole_evaluation_in_one_transaction(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``0007_paper_roles``, and the inverse of T3.6's finding 1.

    One automatic evaluation is four writes the contract puts in one
    transaction: the daily reference and the peak (``portfolio_risk_state``),
    the latch the workers read (``portfolios``), the transition that explains it
    and the ``kill_switch.changed`` projection (``outbox_events``). Before this
    revision no deployed role held all four — ``hunter_app`` was refused the lock
    row, ``hunter_worker`` was refused ``portfolios`` — so the São Paulo rollover
    of a wallet in WARNING had to be split, and a split leaves a window where the
    reference is today's and the latch is yesterday's.

    Here it is one transaction as ``hunter_worker``, and it commits.
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_WORKER)
    try:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, reason, actor_type, evidence, created_at) VALUES "
                "(:id, :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', 'daily loss', 'system', "
                "CAST(:evidence AS jsonb), :ts)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "evidence": '{"daily_loss_pct": "0.0200"}',
                "ts": _NOW,
            },
        )
        await connection.execute(
            text(
                "UPDATE portfolios SET kill_switch_state = 'WARNING', "
                "kill_switch_reason = 'daily loss', updated_at = now() WHERE id = :pf"
            ),
            {"pf": wallet.portfolio_id},
        )
        await connection.execute(
            text(
                "UPDATE portfolio_risk_state SET trading_day = :day, "
                "trading_day_start_utc = :ts, updated_at = now() WHERE portfolio_id = :pf"
            ),
            {"pf": wallet.portfolio_id, "day": _NOW.date(), "ts": _NOW},
        )
        await connection.execute(
            text(
                "INSERT INTO outbox_events (event_id, stream, payload) "
                "VALUES (:id, 'kill_switch.changed', CAST('{}' AS jsonb))"
            ),
            {"id": uuid7()},
        )
        await connection.commit()
    finally:
        await connection.close()

    async with schema_engine.connect() as reader:
        latch = await reader.scalar(
            text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
        day = await reader.scalar(
            text("SELECT trading_day FROM portfolio_risk_state WHERE portfolio_id = :id"),
            {"id": wallet.portfolio_id},
        )
    assert str(latch) == "WARNING", "the engine could not move the latch it decided"
    assert day == _NOW.date(), "the engine could not write the reference it decided"


async def test_the_engine_may_not_rename_or_rescope_the_wallet_it_latches(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The engine's grant on ``portfolios`` is three columns, not the table.

    Table-level ``UPDATE`` would hand the worker the identity fields §18.8 keeps
    frozen: flipping ``is_arena`` takes the wallet out of
    ``uq_portfolios_principal_paper`` and frees a second principal with a fresh
    R$100.000, with no ``DELETE`` for a delete trigger to see.
    """
    wallet, _other = wallets
    for statement in (
        "UPDATE portfolios SET name = 'renamed' WHERE id = :pf",
        "UPDATE portfolios SET is_arena = true WHERE id = :pf",
        "UPDATE portfolios SET status = 'archived' WHERE id = :pf",
        "UPDATE portfolios SET initial_capital = 999999 WHERE id = :pf",
    ):
        connection = await _as(schema_engine, _AS_WORKER)
        try:
            with pytest.raises(DBAPIError, match=_DENIED):
                await connection.execute(text(statement), {"pf": wallet.portfolio_id})
        finally:
            await connection.rollback()
            await connection.close()


async def test_the_engine_locks_the_organization_row_and_never_writes_it(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """T3.12, blocking A: ``FOR SHARE`` needs ``ACL_UPDATE``, and nothing else does.

    ``effective_state(lock=True)`` acquires system → organization → wallet, and
    without this grant the admission path died with *permission denied for table
    organizations* before deciding anything. The grant is ``UPDATE (updated_at)``
    — enough for the row mark, not enough to block a whole organization, which
    stays an OWNER's act through the API (§19.2).
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_WORKER)
    try:
        locked = await connection.scalar(
            text("SELECT kill_switch_state FROM organizations WHERE id = :id FOR SHARE"),
            {"id": wallet.org_id},
        )
        assert locked is not None, "the engine cannot take the organization lock"
    finally:
        await connection.rollback()
        await connection.close()

    connection = await _as(schema_engine, _AS_WORKER)
    try:
        with pytest.raises(DBAPIError, match=_DENIED):
            await connection.execute(
                text("UPDATE organizations SET kill_switch_state = 'EMERGENCY' WHERE id = :id"),
                {"id": wallet.org_id},
            )
    finally:
        await connection.rollback()
        await connection.close()


async def test_the_app_may_not_write_the_curve_of_its_own_wallet(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review of ``0006``, finding 5 — and RLS is not what closes it.

    The organization in context is the wallet's own, so ``tenant_isolation`` says
    yes; the refusal is the privilege. That is the point: the curve is the
    evidence a resume reads, and a fabricated point at the right timestamp is a
    recovery the next resume believes.
    """
    wallet, _other = wallets
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        with pytest.raises(DBAPIError, match=_DENIED):
            await connection.execute(
                text(
                    "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                    "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                    "realized_pnl_cum, peak_equity) VALUES (:org, :pf, '1m', :ts, 20000, 20000, "
                    "0, 0, 0, 20000)"
                ),
                {"org": wallet.org_id, "pf": wallet.portfolio_id, "ts": _NOW},
            )
    finally:
        await connection.rollback()
        await connection.close()


async def test_the_app_files_a_request_and_the_engine_is_the_one_that_decides(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """§19.4: an ``INSERT`` by the API is a *request*, and afterwards it is read-only.

    A grant cannot describe the shape of an ``INSERT``, so a handler could file a
    row already stamped ``approved`` with a ``risk_decision`` of its own making
    and a reservation attached — a decision the Risk Engine never took, holding
    capital in the participation budget. The trigger refuses that; the honest
    request passes; and the decision that follows is the engine's.
    """
    wallet, _other = wallets
    proposal_id = uuid7()
    request = {
        "id": uuid7(),
        "org": wallet.org_id,
        "pf": wallet.portfolio_id,
        "market": wallet.market_id,
        "key": f"idem-{uuid.uuid4().hex[:8]}",
    }
    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        with pytest.raises(DBAPIError, match="carrying a decision"):
            await connection.execute(
                text(
                    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                    "direction, status, idempotency_key, source, risk_decision) VALUES "
                    "(:id, :org, :pf, :market, 'long', 'approved', :key, 'manual', "
                    "CAST(:decision AS jsonb))"
                ),
                {**request, "decision": '{"approved": true}'},
            )
    finally:
        await connection.rollback()
        await connection.close()

    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        await connection.execute(
            text(
                "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                "direction, status, idempotency_key, source, request_digest) VALUES "
                "(:id, :org, :pf, :market, 'long', 'pending', :key, 'manual', :digest)"
            ),
            {**request, "id": proposal_id, "digest": "sha256:" + uuid.uuid4().hex},
        )
        await connection.commit()
    finally:
        await connection.close()

    connection = await _as(schema_engine, _AS_APP, wallet.org_id)
    try:
        with pytest.raises(DBAPIError, match=_DENIED):
            await connection.execute(
                text("UPDATE trade_proposals SET status = 'approved' WHERE id = :id"),
                {"id": proposal_id},
            )
    finally:
        await connection.rollback()
        await connection.close()

    connection = await _as(schema_engine, _AS_WORKER)
    try:
        await connection.execute(
            text(
                "UPDATE trade_proposals SET status = 'approved', decided_at = now(), "
                "admission_seq = 1 WHERE id = :id"
            ),
            {"id": proposal_id},
        )
        await connection.execute(
            text(
                "UPDATE portfolio_risk_state SET last_admission_seq = 1, updated_at = now() "
                "WHERE portfolio_id = :pf"
            ),
            {"pf": wallet.portfolio_id},
        )
        await connection.commit()
    finally:
        await connection.close()

    async with schema_engine.connect() as reader:
        status = await reader.scalar(
            text("SELECT status FROM trade_proposals WHERE id = :id"), {"id": proposal_id}
        )
        seq = await reader.scalar(
            text("SELECT last_admission_seq FROM portfolio_risk_state WHERE portfolio_id = :pf"),
            {"pf": wallet.portfolio_id},
        )
    assert str(status) == "approved"
    assert seq == 1, "the FIFO counter is the engine's, and only the engine advanced it"


# --------------------------------------------------------------------------
# 0008_paper_roles_2 — a wallet is born audited, and the motive is part of
# the latch (DATABASE.md §20; security review of ``0007``, D3 and D4)
# --------------------------------------------------------------------------


async def _bare_organization(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """An organization with a workspace and **no** wallet, built as the owner.

    Needed because the ``wallets`` fixture's two organizations already hold their
    principal wallet, and ``uq_portfolios_principal_paper`` would refuse a second
    one before the guard under test ever ran — the index would pass the test for
    the wrong reason.
    """
    org_id, workspace_id = uuid7(), uuid7()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": org_id, "slug": f"born-{uuid.uuid4().hex[:8]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, 'born', 'paper_trading')"
            ),
            {"id": workspace_id, "org": org_id},
        )
    return org_id, workspace_id


async def _audit(connection: AsyncConnection, org_id: uuid.UUID, entity: uuid.UUID) -> None:
    await connection.execute(
        text(
            "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, action, "
            "entity_type, entity_id) VALUES (:id, now(), :org, 'system', 'portfolio.opened', "
            "'portfolio', :entity)"
        ),
        {"id": uuid7(), "org": org_id, "entity": entity},
    )


async def _open_as_the_engine(
    engine: AsyncEngine,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    kind: str = "paper",
    arena: bool = False,
    audited: bool = True,
    audit_org: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one ``portfolios`` row as ``hunter_worker``, and nothing else.

    Deliberately *not* ``open_paper_wallet``: this is the raw capability
    ``0007``'s grant handed the engine, and the raw capability is what the guard
    has to bound.
    """
    portfolio_id = uuid7()
    async with engine.begin() as connection:
        await connection.execute(_AS_WORKER)
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'probe', :kind, "
                ":arena, 100000)"
            ),
            {
                "id": portfolio_id,
                "org": org_id,
                "ws": workspace_id,
                "kind": kind,
                "arena": arena,
            },
        )
        if audited:
            await _audit(connection, audit_org or org_id, portfolio_id)
    return portfolio_id


async def test_the_engine_cannot_open_an_arena_wallet(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review of ``0007``, **D3** — ``is_arena`` was the way past permanence.

    ``uq_portfolios_principal_paper`` is ``WHERE type = 'paper' AND NOT
    is_arena`` (§18.8), so an arena wallet sits **outside** it: the engine could
    write a second wallet the index that makes "one wallet" true cannot see, with
    a capital of its own, no anchor and no history. Reproduced as the role —
    ``0007`` accepted this row.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="the engine opens the paper wallet and nothing else"):
        await _open_as_the_engine(
            schema_engine, wallet.org_id, wallet.workspace_id, arena=True, audited=False
        )


async def test_the_engine_cannot_open_a_live_portfolio(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The directive is paper-only in M3, and ``INSERT`` carries every column.

    Every downstream reader treats a ``live`` portfolio as real money. The grant
    ``0007`` gave the engine was for opening *the paper wallet*; this is the
    schema saying so instead of a comment saying so.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="the engine opens the paper wallet and nothing else"):
        await _open_as_the_engine(
            schema_engine, wallet.org_id, wallet.workspace_id, kind="live", audited=False
        )


async def test_the_engine_cannot_open_a_wallet_it_never_audited(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """A wallet whose birth nobody recorded has no beginning to reconstruct.

    ``hunter_worker`` holds ``BYPASSRLS``, so the organization in the row is
    checked by no policy at all: the review opened a wallet **in another
    organization**, with no anchor, no lock row and no audit entry, and nothing
    refused it. What makes an opening honest is that the audit row is written in
    the same commit (§18.2) — so that is what the guard asks for.
    """
    org_id, workspace_id = await _bare_organization(schema_engine)
    with pytest.raises(DBAPIError, match="no audit_logs row written in this transaction"):
        await _open_as_the_engine(schema_engine, org_id, workspace_id, audited=False)

    async with schema_engine.connect() as connection:
        opened = await connection.scalar(
            text("SELECT count(*) FROM portfolios WHERE organization_id = :org"), {"org": org_id}
        )
    assert opened == 0, "the refusal has to take the row with it"


async def test_an_audit_row_of_another_organization_does_not_bless_this_opening(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The entry has to be *this* tenant's, not any entry the transaction wrote.

    A worker that touches several organizations in one transaction writes audit
    rows for all of them; without the ``organization_id`` half, one of those
    would authorise a wallet opened for a tenant nobody recorded.
    """
    wallet, _other = wallets
    org_id, workspace_id = await _bare_organization(schema_engine)
    with pytest.raises(DBAPIError, match="no audit_logs row written in this transaction"):
        await _open_as_the_engine(schema_engine, org_id, workspace_id, audit_org=wallet.org_id)


async def test_an_audit_row_banked_earlier_does_not_bless_a_later_opening(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``xmin``, not ``EXISTS`` — the same lesson as blocking 1 of §18.7.

    Being audited *at some point* is not being audited *for this act*: one row
    banked by an earlier transaction would otherwise authorise every later
    opening for that organization, for ever.
    """
    org_id, workspace_id = await _bare_organization(schema_engine)
    async with schema_engine.begin() as connection:
        await _audit(connection, org_id, uuid7())

    with pytest.raises(DBAPIError, match="no audit_logs row written in this transaction"):
        await _open_as_the_engine(schema_engine, org_id, workspace_id, audited=False)


async def test_the_engine_opens_a_paper_wallet_it_audits_in_the_same_transaction(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """And the honest shape passes: the guard bounds the grant, it does not remove it.

    This is the shape ``hunter_core.portfolio.open_paper_wallet`` writes, proved
    end to end through the real function in ``test_portfolio_opening.py``.
    """
    org_id, workspace_id = await _bare_organization(schema_engine)
    portfolio_id = await _open_as_the_engine(schema_engine, org_id, workspace_id)

    async with schema_engine.connect() as connection:
        stored = await connection.scalar(
            text("SELECT type FROM portfolios WHERE id = :id"), {"id": portfolio_id}
        )
    assert str(stored) == "paper"


async def test_an_operator_holding_both_roles_may_still_write_any_portfolio(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The guard is scoped to *only* the engine's privileges, as §18.7's is.

    An operator, the owner and a superuser hold both roles, so they are not "only
    the engine"; ``hunter_app`` is untouched and still creates the arena and
    shadow portfolios the product offers. Scoping this to ``current_user`` would
    have been the "name is not a privilege" mistake in reverse.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(wallet.org_id)}
        )
        await connection.execute(_AS_APP)
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "is_arena, initial_capital) VALUES (:id, :org, :ws, 'arena', 'paper', true, 1000)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "ws": wallet.workspace_id},
        )
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "initial_capital) VALUES (:id, :org, :ws, 'shadow', 'shadow', 1000)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "ws": wallet.workspace_id},
        )


async def test_a_wallet_motive_cannot_be_rewritten_without_a_transition(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """Security review of ``0007``, **D4** — the ``WHEN`` watched the state only.

    ``kill_switch_reason`` is what an OWNER reads on the screen
    (``routers/risk.py``, ``services/radar_org_derivation.py``), and it was
    rewritable with no transition, no actor and no history: the latch said one
    thing and the story explaining it said another, permanently.

    Refused for **every** role, not only the engine: it is a constraint trigger,
    and the motive of a latch is not a caption anyone gets to edit.
    """
    wallet, _other = wallets
    await _latch(schema_engine, wallet, "WARNING", actor="system")

    for role in (_AS_WORKER, _AS_APP):
        with pytest.raises(DBAPIError, match="rewrote its kill switch reason"):
            async with schema_engine.begin() as connection:
                await connection.execute(
                    text("SELECT set_config('app.current_org', :org, true)"),
                    {"org": str(wallet.org_id)},
                )
                await connection.execute(role)
                await connection.execute(
                    text("UPDATE portfolios SET kill_switch_reason = :why WHERE id = :id"),
                    {"why": "whatever the screen should say", "id": wallet.portfolio_id},
                )
    with pytest.raises(DBAPIError, match="rewrote its kill switch reason"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_reason = 'as the owner' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )

    async with schema_engine.connect() as connection:
        reason = await connection.scalar(
            text("SELECT kill_switch_reason FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
    assert reason is None, "nothing was rewritten: _latch moves the state, not the motive"
    await _latch(schema_engine, wallet, "ACTIVE", actor="user")


async def test_an_organization_motive_cannot_be_rewritten_without_a_transition(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The same widening on the organization scope — the two guards are one body."""
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="rewrote its kill switch reason"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE organizations SET kill_switch_reason = 'quiet' WHERE id = :id"),
                {"id": wallet.org_id},
            )


async def test_a_move_that_carries_its_motive_and_its_transition_still_passes(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """The engine's real path: state, reason and the transition, one transaction.

    ``hunter_core.risk.transitions.record_transition`` writes
    ``kill_switch_state`` and ``kill_switch_reason`` in the *same* ``UPDATE``,
    with the transition next to it — which is why the widened ``WHEN`` costs that
    path nothing, and why ``0007``'s column grant names the two together.
    """
    wallet, _other = wallets
    async with schema_engine.begin() as connection:
        await connection.execute(_AS_WORKER)
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, reason, actor_type, evidence) VALUES "
                "(:id, :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', :why, 'system', :evidence)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "why": "daily loss 1.2%",
                "evidence": '{"daily_loss_pct": "0.012"}',
            },
        )
        await connection.execute(
            text(
                "UPDATE portfolios SET kill_switch_state = 'WARNING', kill_switch_reason = :why "
                "WHERE id = :id"
            ),
            {"why": "daily loss 1.2%", "id": wallet.portfolio_id},
        )

    async with schema_engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT kill_switch_state, kill_switch_reason FROM portfolios WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )
        ).one()
    assert tuple(row) == ("WARNING", "daily loss 1.2%")
    await _latch(schema_engine, wallet, "ACTIVE", actor="user")


async def test_the_audited_move_guard_still_proves_the_same_transition(
    schema_engine: AsyncEngine, wallets: tuple[Wallet, Wallet]
) -> None:
    """``0008`` re-installs the body; the refusals ``0006`` measured survive it.

    The body is frozen in ``ddl/paper_roles_2.py`` rather than read out of
    ``0006``'s module (§16.5's rule against a later edit changing what an earlier
    revision installs), so this is the test that keeps the copy honest: no
    transition at all, and one banked by an earlier transaction.
    """
    wallet, _other = wallets
    with pytest.raises(DBAPIError, match="without an audited transition"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = 'WARNING' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )

    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, actor_type, evidence) VALUES "
                "(:id, :org, 'portfolio', :pf, 'ACTIVE', 'WARNING', 'system', :evidence)"
            ),
            {
                "id": uuid7(),
                "org": wallet.org_id,
                "pf": wallet.portfolio_id,
                "evidence": '{"daily_loss_pct": "0.012"}',
            },
        )
    with pytest.raises(DBAPIError, match="written by an earlier transaction"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = 'WARNING' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )
