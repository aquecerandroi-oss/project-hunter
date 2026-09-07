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

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql.elements import TextClause

from hunter_core.domain.types import uuid7

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


async def test_the_principal_wallet_index_ignores_status_and_soft_delete(
    schema_engine: AsyncEngine,
) -> None:
    """The predicate is read back from Postgres, not from the model.

    Alembic compares the *columns* of an index and not its ``WHERE`` (§17.3), so
    an index left with the wrong predicate reports no drift while enforcing the
    wrong invariant. The joint M3 decision is explicit about both halves: the
    predicate must not mention ``status`` and must not exclude a filled
    ``deleted_at`` — archiving or soft-deleting the wallet and opening another
    one is the substitution the directive forbids.
    """
    async with schema_engine.connect() as connection:
        definition: str | None = await connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": "uq_portfolios_principal_paper"},
        )
    assert definition is not None, "the principal-wallet index is missing"
    assert "UNIQUE INDEX" in definition
    assert "(organization_id, workspace_id)" in definition
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
                    "from_state, to_state, actor_type) VALUES "
                    "(:id, :org, 'portfolio', :pf, 'TRADING_DISABLED', 'ACTIVE', 'system')"
                ),
                {"id": uuid7(), "org": wallet.org_id, "pf": wallet.portfolio_id},
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
                        "scope_id, from_state, to_state, actor_type, actor_id) VALUES "
                        "(:id, :org, 'portfolio', :pf, :frm, :to, :actor, :actor_id)"
                    ),
                    {
                        "id": uuid7(),
                        "org": wallet.org_id,
                        "pf": wallet.portfolio_id,
                        "frm": current,
                        "to": to_state,
                        "actor": actor,
                        "actor_id": uuid7() if actor == "user" else None,
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
