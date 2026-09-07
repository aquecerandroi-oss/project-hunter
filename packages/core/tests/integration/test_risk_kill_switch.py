"""The kill switch, against a real Postgres — RISK_ENGINE.md §5, DATABASE.md §18.7.

The unit tests state the arithmetic; this states the things only a database can
answer: that the column the workers read cannot move without an audited
transition, that two concurrent evaluations produce one, that a restart finds the
same latch, and that a resume never touches the peak or the day's opening.

Everything runs as the roles a deployment uses (``hunter_app`` under RLS), never
as the container owner, because a privilege answered by ``has_table_privilege``
and a privilege answered by a statement are different questions (the lesson
``test_schema_paper.py`` opens with).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import uuid7
from hunter_core.risk import (
    DayReferenceReason,
    ResumeRefused,
    effective_state,
    evaluate_and_persist,
    resume,
)
from hunter_risk import PortfolioState, sao_paulo_day_start_utc

from .conftest import alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

# Sao Paulo is UTC-3: midnight there is 03:00 UTC.
DAY_ONE = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
DAY_TWO_TURN = datetime(2026, 9, 7, 3, 0, 5, tzinfo=UTC)
OPENING = Decimal(20000)


class Transition(NamedTuple):
    from_state: KillSwitchState
    to_state: KillSwitchState
    actor_type: str
    actor_id: uuid.UUID | None
    reason: str
    evidence: dict[str, str]


class Wallet:
    def __init__(self) -> None:
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.portfolio_id = uuid7()
        self.user_id = uuid7()


@pytest.fixture(scope="session")
def kill_switch_db(container_url: str) -> str:
    """A database of its own at ``head`` — a downgrade elsewhere must not reach it."""
    url = asyncio.run(create_database(container_url, "hunter_kill_switch"))
    command.upgrade(alembic_config(url), "head")
    return url


@pytest_asyncio.fixture
async def engine(kill_switch_db: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(kill_switch_db)
    try:
        yield created
    finally:
        await created.dispose()


@pytest_asyncio.fixture
async def factory(kill_switch_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory shaped like the application's (``expire_on_commit=False``)."""
    built = create_async_engine(kill_switch_db, connect_args={"statement_cache_size": 0})
    try:
        yield async_sessionmaker(bind=built, expire_on_commit=False)
    finally:
        await built.dispose()


@pytest_asyncio.fixture
async def wallet(engine: AsyncEngine) -> AsyncIterator[Wallet]:
    """One organization with an opened principal wallet and its lock row."""
    built = Wallet()
    async with engine.begin() as connection:
        await connection.execute(text("GRANT hunter_app, hunter_worker TO CURRENT_USER"))
        await connection.execute(
            text("INSERT INTO users (id, external_auth_id, email) VALUES (:id, :external, :email)"),
            {
                "id": built.user_id,
                "external": f"clerk_{built.user_id}",
                "email": f"ks-{built.user_id}@example.test",
            },
        )
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": built.org_id, "slug": f"ks-{uuid.uuid4().hex[:10]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, 'ks', 'paper_trading')"
            ),
            {"id": built.workspace_id, "org": built.org_id},
        )
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "initial_capital) VALUES (:id, :org, :ws, 'principal', 'paper', :capital)"
            ),
            {
                "id": built.portfolio_id,
                "org": built.org_id,
                "ws": built.workspace_id,
                "capital": OPENING,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, trading_day, "
                "trading_day_start_utc, equity_day_start, day_reference_observed_at, peak_equity, "
                "peak_equity_at) VALUES (:org, :pf, DATE '2026-09-06', :start, :equity, :start, "
                ":equity, :start)"
            ),
            {
                "org": built.org_id,
                "pf": built.portfolio_id,
                "start": sao_paulo_day_start_utc(DAY_ONE),
                "equity": OPENING,
            },
        )
    try:
        yield built
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL app.portfolio_teardown = 'on'"))
            await connection.execute(
                text("DELETE FROM organizations WHERE id = :id"), {"id": built.org_id}
            )
            await connection.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": built.user_id}
            )


def portfolio_state(
    wallet: Wallet, equity: Decimal, *, as_of: datetime, peak: Decimal = OPENING
) -> PortfolioState:
    """A minimal state: the kill switch reads equity, peak and the day's opening."""
    return PortfolioState(
        portfolio_id=wallet.portfolio_id,
        as_of=as_of,
        equity=equity,
        cash=equity,
        peak_equity=max(peak, equity),
        day_start_equity=OPENING,
        day_start_utc=sao_paulo_day_start_utc(as_of),
    )


async def evaluate(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    equity: Decimal | None,
    at: datetime,
):
    """One evaluation in its own committed transaction, as the API role does it."""
    async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
        state = None if equity is None else portfolio_state(wallet, equity, as_of=at)
        return await evaluate_and_persist(session, wallet.portfolio_id, state, at)


@asynccontextmanager
async def privileged(engine: AsyncEngine, wallet: Wallet) -> AsyncGenerator[AsyncSession]:
    """A transaction with the organization in context and **no role downgrade**.

    Used only by the evaluations that have to write ``portfolio_risk_state`` and
    ``portfolios`` together — the day's rollover and a rising peak. No deployed
    role can do both today: ``portfolio_risk_state_guard`` refuses the ``UPDATE``
    for ``hunter_app`` and ``hunter_worker`` holds ``SELECT`` only on
    ``portfolios``. That wall is asserted by
    ``test_no_deployed_role_can_write_both_halves_of_one_evaluation``; these
    tests are about the engine's behaviour, and they say plainly which privilege
    they are standing on to observe it (notes-T3.6, finding 1).
    """
    session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org', :org, true)"),
                {"org": str(wallet.org_id)},
            )
            yield session
    finally:
        await session.close()


async def evaluate_state(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    state: PortfolioState,
    at: datetime,
):
    """One evaluation with a state the caller built by hand."""
    async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
        return await evaluate_and_persist(session, wallet.portfolio_id, state, at)


async def evaluate_privileged(
    engine: AsyncEngine, wallet: Wallet, equity: Decimal | None, at: datetime
):
    async with privileged(engine, wallet) as session:
        state = None if equity is None else portfolio_state(wallet, equity, as_of=at)
        return await evaluate_and_persist(session, wallet.portfolio_id, state, at)


async def record_equity(engine: AsyncEngine, wallet: Wallet, equity: Decimal, at: datetime) -> None:
    """One point of the equity curve. The peak may only rise to an equity the
    curve actually showed (``portfolio_risk_state_guard``, ``_OBSERVED_EQUITY``)."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                "realized_pnl_cum, peak_equity) VALUES (:org, :pf, '1m', :ts, :equity, :equity, "
                "0, 0, 0, :equity)"
            ),
            {"org": wallet.org_id, "pf": wallet.portfolio_id, "ts": at, "equity": equity},
        )


async def read_row(engine: AsyncEngine, wallet: Wallet) -> dict[str, object]:
    async with engine.connect() as connection:
        risk = (
            await connection.execute(
                text(
                    "SELECT peak_equity, peak_equity_at, equity_day_start, trading_day, "
                    "day_reference_observed_at FROM portfolio_risk_state WHERE portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )
        ).one()
        latch = await connection.scalar(
            text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
        rows = (
            await connection.execute(
                text(
                    "SELECT from_state, to_state, actor_type, actor_id, reason, evidence "
                    "FROM kill_switch_transitions WHERE scope_id = :id ORDER BY created_at, id"
                ),
                {"id": wallet.portfolio_id},
            )
        ).all()
    # ``text()`` hands back the enum labels as plain strings; the assertions are
    # about the domain enum, so the coercion happens once, here.
    transitions = [
        Transition(
            KillSwitchState(row.from_state),
            KillSwitchState(row.to_state),
            row.actor_type,
            row.actor_id,
            row.reason,
            row.evidence,
        )
        for row in rows
    ]
    return {
        "peak_equity": risk.peak_equity,
        "peak_equity_at": risk.peak_equity_at,
        "equity_day_start": risk.equity_day_start,
        "trading_day": risk.trading_day,
        "day_reference_observed_at": risk.day_reference_observed_at,
        "latch": KillSwitchState(latch),
        "transitions": transitions,
    }


# --------------------------------------------------------------------------
# The database refuses an unaudited move
# --------------------------------------------------------------------------


async def test_a_bare_update_of_the_latch_is_refused_by_the_database(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """The deferred constraint trigger, proved from the application role.

    Without it, ``UPDATE portfolios SET kill_switch_state = 'ACTIVE'`` is a
    complete, silent unblock: no row, no actor, no evidence. This is the reason
    :mod:`hunter_core.risk.transitions` is the only write path.
    """
    with pytest.raises(DBAPIError, match="without an audited transition"):
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.current_org', :org, true)"),
                {"org": str(wallet.org_id)},
            )
            await connection.execute(text("SET LOCAL ROLE hunter_app"))
            await connection.execute(
                text("UPDATE portfolios SET kill_switch_state = 'TRADING_DISABLED' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )


# --------------------------------------------------------------------------
# The ladder, latched, and the resume that has to prove itself
# --------------------------------------------------------------------------


async def test_the_ladder_latches_and_only_an_authorised_resume_leaves_it(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """-1 % -> WARNING -> -2 % -> BLOCKED -> recovery keeps BLOCKED -> resume.

    Every step is the directive's §5 read literally: escalation is automatic and
    immediate, the block does not expire when the loss does, and the resume is
    refused while the trigger still bites — then granted, without moving the peak
    or the day's opening one unit.
    """
    warning = await evaluate(factory, wallet, Decimal(19800), DAY_ONE)
    assert warning.latched is KillSwitchState.WARNING
    assert warning.daily_loss_pct == Decimal("0.01")

    blocked = await evaluate(factory, wallet, Decimal(19600), DAY_ONE + timedelta(minutes=1))
    assert blocked.latched is KillSwitchState.TRADING_DISABLED
    assert blocked.automatic is KillSwitchState.TRADING_DISABLED

    # A resume while the loss is still 2 % is refused, not written.
    with pytest.raises(ResumeRefused, match="still TRADING_DISABLED"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="I looked at it",
                now=DAY_ONE + timedelta(minutes=2),
                state=portfolio_state(wallet, Decimal(19600), as_of=DAY_ONE + timedelta(minutes=2)),
                publish=False,
            )

    # Recovering inside the same day does not unlatch anything.
    recovered = await evaluate(factory, wallet, OPENING, DAY_ONE + timedelta(minutes=3))
    assert recovered.latched is KillSwitchState.TRADING_DISABLED
    assert recovered.automatic is KillSwitchState.ACTIVE
    assert recovered.changed is False

    async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
        outcome = await resume(
            session,
            wallet.portfolio_id,
            actor_id=wallet.user_id,
            reason="reviewed with Everton",
            now=DAY_ONE + timedelta(minutes=4),
            state=portfolio_state(wallet, OPENING, as_of=DAY_ONE + timedelta(minutes=4)),
            publish=False,
        )
    assert outcome.to_state is KillSwitchState.ACTIVE

    row = await read_row(engine, wallet)
    assert row["latch"] is KillSwitchState.ACTIVE
    assert row["peak_equity"] == OPENING, "a resume never redefines the peak"
    assert row["equity_day_start"] == OPENING, "nor the day's opening"
    states = [(t.from_state, t.to_state, t.actor_type) for t in row["transitions"]]  # type: ignore[union-attr]
    assert states == [
        (KillSwitchState.ACTIVE, KillSwitchState.WARNING, "system"),
        (KillSwitchState.WARNING, KillSwitchState.TRADING_DISABLED, "system"),
        (KillSwitchState.TRADING_DISABLED, KillSwitchState.ACTIVE, "user"),
    ]
    evidence = row["transitions"][1].evidence  # type: ignore[index]
    assert evidence["daily_loss_pct"] == "0.02"
    assert evidence["blocked_daily_loss_pct"] == "0.02"
    assert evidence["equity"] == "19600"
    assert row["transitions"][2].actor_id == wallet.user_id  # type: ignore[index]


async def test_a_resume_on_a_stale_equity_is_refused(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """No fresh observation, no proof — and no proof means no resume (§7)."""
    await evaluate(factory, wallet, Decimal(19600), DAY_ONE)

    with pytest.raises(ResumeRefused, match="no equity observation"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="trust me",
                now=DAY_ONE + timedelta(minutes=1),
                publish=False,
            )


async def test_a_caller_supplied_state_cannot_lower_the_durable_peak(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The way round "resuming redefines neither peak nor losses", closed.

    Astra, review of this diff: peak 20.800, equity 19.968 — a 4 % drawdown. Hand
    ``resume`` a state whose peak equals the equity and the drawdown reads zero,
    so the WARNING (and, with worse numbers, the block) evaporates. The state is
    re-anchored on the locked row before it is assessed, so the number the
    caller offered for the peak is simply not used.
    """
    await record_equity(engine, wallet, Decimal(20800), DAY_ONE)
    await evaluate_privileged(engine, wallet, Decimal(20800), DAY_ONE)
    at = DAY_ONE + timedelta(minutes=1)
    await evaluate(factory, wallet, Decimal(19000), at)  # blocked: -5 % on the day

    flattering = PortfolioState(
        portfolio_id=wallet.portfolio_id,
        as_of=at + timedelta(seconds=1),
        equity=Decimal(19000),
        cash=Decimal(19000),
        peak_equity=Decimal(19000),
        day_start_equity=Decimal(19000),
        day_start_utc=sao_paulo_day_start_utc(at),
    )
    with pytest.raises(ResumeRefused, match="still TRADING_DISABLED"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="my own numbers say it is fine",
                now=at + timedelta(seconds=1),
                state=flattering,
            )

    row = await read_row(engine, wallet)
    assert row["latch"] is KillSwitchState.TRADING_DISABLED
    assert row["peak_equity"] == Decimal(20800)


async def test_evidence_from_before_the_block_is_not_evidence_of_recovery(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Snapshot 20.000 at 12:00:00, block at 12:00:30 on 19.500, resume at 12:00:31.

    The 12:00:00 point is 31 seconds old — well inside the freshness window — and
    describes the wallet *before* the loss that blocked it (Astra, review of this
    diff). Age alone was never the right test.
    """
    await record_equity(engine, wallet, OPENING, DAY_ONE)
    await evaluate(factory, wallet, Decimal(19600), DAY_ONE + timedelta(seconds=30))

    with pytest.raises(ResumeRefused, match="not newer than the kill switch move"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="it was fine a moment ago",
                now=DAY_ONE + timedelta(seconds=31),
            )


async def test_a_stale_or_unmarked_state_keeps_the_latch_instead_of_assessing(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """A state from 23:59 assessed at 00:00:30 is not a measurement of 00:00:30.

    Both degraded cases answer like no state at all: the latch stands, the
    automatic ladder is ``None``, the protections are untouched.
    """
    stale = portfolio_state(wallet, Decimal(19600), as_of=DAY_ONE)
    unmarked = portfolio_state(wallet, Decimal(19600), as_of=DAY_ONE).model_copy(
        update={"marks_complete": False}
    )

    late = await evaluate_state(factory, wallet, stale, DAY_ONE + timedelta(minutes=5))
    blind = await evaluate_state(factory, wallet, unmarked, DAY_ONE)

    assert late.automatic is None
    assert late.latched is KillSwitchState.ACTIVE
    assert blind.automatic is None
    assert blind.latched is KillSwitchState.ACTIVE
    row = await read_row(engine, wallet)
    assert row["transitions"] == []


async def test_a_caller_supplied_state_from_before_the_block_is_refused_too(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The ``state=`` argument does not skip the "after the block" condition.

    Astra, second round: the first fix compared the *curve* against the moment of
    the block and left the caller's own state comparing only its age. State at
    12:00:00 with 20.000, block at 12:00:30 on 19.500, resume at 12:00:31 — 31
    seconds old, comfortably inside the freshness window, and describing a wallet
    that had not lost anything yet.
    """
    before = portfolio_state(wallet, OPENING, as_of=DAY_ONE)
    await evaluate(factory, wallet, Decimal(19600), DAY_ONE + timedelta(seconds=30))

    with pytest.raises(ResumeRefused, match="not newer than the kill switch move"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="it was fine a moment ago",
                now=DAY_ONE + timedelta(seconds=31),
                state=before,
            )


async def test_evidence_stamped_in_the_future_or_half_marked_is_refused(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Two more ways an equity is not evidence — both refusals, never grants.

    A patrimony stamped ahead of the act has not happened; an equity whose marks
    are incomplete is a guess, and a guess cannot show a trigger stopped biting.
    """
    at = DAY_ONE + timedelta(seconds=30)
    await evaluate(factory, wallet, Decimal(19600), at)
    future = portfolio_state(wallet, OPENING, as_of=at + timedelta(seconds=90))
    unmarked = portfolio_state(wallet, OPENING, as_of=at + timedelta(seconds=1)).model_copy(
        update={"marks_complete": False}
    )

    async def attempt(state: PortfolioState) -> None:
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await resume(
                session,
                wallet.portfolio_id,
                actor_id=wallet.user_id,
                reason="trust these numbers",
                now=at + timedelta(seconds=60),
                state=state,
            )

    with pytest.raises(ResumeRefused, match="stamped in the future"):
        await attempt(future)
    with pytest.raises(ResumeRefused, match="incomplete marks"):
        await attempt(unmarked)


# --------------------------------------------------------------------------
# The turn of the day
# --------------------------------------------------------------------------


async def test_the_warning_clears_only_at_the_turn_and_only_when_both_triggers_are_gone(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    await evaluate(factory, wallet, Decimal(19800), DAY_ONE)
    # The day is anchored on the last point observed **before** the turn, never on
    # the equity of whenever the evaluation ran (``daily.py``).
    await record_equity(engine, wallet, Decimal(19800), DAY_TWO_TURN - timedelta(seconds=30))

    turned = await evaluate_privileged(engine, wallet, Decimal(19800), DAY_TWO_TURN)

    assert turned.reference.rolled is True
    assert turned.reference.reason is DayReferenceReason.ROLLED
    assert turned.latched is KillSwitchState.ACTIVE
    row = await read_row(engine, wallet)
    assert row["equity_day_start"] == Decimal(19800), "the new day opens at the equity of the turn"
    assert row["day_reference_observed_at"] == DAY_TWO_TURN, "the real instant, not midnight"
    assert row["peak_equity"] == OPENING, "the peak does not reset at the turn"
    assert row["transitions"][-1].to_state is KillSwitchState.ACTIVE  # type: ignore[index]


async def test_a_drawdown_warning_survives_the_turn_because_the_peak_does(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The day opens at 20.000, the peak reaches 20.800, the equity is 19.968.

    The day's loss is 0,16 % — under the 1 % rung — and the drawdown is exactly
    4 %, so the WARNING is the drawdown's alone. At the turn the day's loss
    resets to zero and the drawdown does **not**, because the peak is not a daily
    number. That is the directive's "manter o maior patrimônio histórico sem
    resets" doing visible work, and it is why the exit condition names *both*
    triggers instead of just the day's loss.
    """
    await record_equity(engine, wallet, Decimal(20800), DAY_ONE)
    await evaluate_privileged(engine, wallet, Decimal(20800), DAY_ONE)

    warned = await evaluate(factory, wallet, Decimal(19968), DAY_ONE + timedelta(minutes=1))
    await record_equity(engine, wallet, Decimal(19968), DAY_TWO_TURN - timedelta(seconds=30))
    turned = await evaluate_privileged(engine, wallet, Decimal(19968), DAY_TWO_TURN)

    assert warned.peak_equity == Decimal(20800)
    assert warned.drawdown_pct == Decimal("0.04")
    assert warned.daily_loss_pct == Decimal("0.0016")
    assert warned.latched is KillSwitchState.WARNING
    assert turned.reference.rolled is True
    assert turned.daily_loss_pct == Decimal(0)
    assert turned.drawdown_pct == Decimal("0.04")
    assert turned.latched is KillSwitchState.WARNING
    assert turned.changed is False


async def test_a_rollover_with_no_point_before_the_turn_leaves_the_reference_unknown(
    engine: AsyncEngine, wallet: Wallet
) -> None:
    """A restart at 03:17 does not make the equity of 03:17 the equity of midnight.

    Nothing was marked before the turn, so the day is recorded, the opening is
    not, the latch is preserved, and the automatic ladder is ``None`` — entries
    blocked by a missing input, protections untouched (RISK_ENGINE.md §5).
    """
    late = DAY_TWO_TURN.replace(hour=6, minute=17, second=0)

    evaluation = await evaluate_privileged(engine, wallet, Decimal(19500), late)

    assert evaluation.reference.reason is DayReferenceReason.UNAVAILABLE_NO_OBSERVATION
    assert evaluation.automatic is None
    assert evaluation.changed is False
    row = await read_row(engine, wallet)
    assert row["equity_day_start"] is None
    assert row["day_reference_observed_at"] is None
    assert str(row["trading_day"]) == "2026-09-07"


async def test_a_wallet_that_cannot_be_marked_keeps_its_latch(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    await evaluate(factory, wallet, Decimal(19600), DAY_ONE)

    unmarked = await evaluate(factory, wallet, None, DAY_ONE + timedelta(minutes=1))

    assert unmarked.automatic is None
    assert unmarked.latched is KillSwitchState.TRADING_DISABLED
    assert unmarked.changed is False


# --------------------------------------------------------------------------
# Peak, restart, concurrency and the scopes
# --------------------------------------------------------------------------


async def test_the_peak_rises_and_never_falls(engine: AsyncEngine, wallet: Wallet) -> None:
    await record_equity(engine, wallet, Decimal(21000), DAY_ONE)
    await evaluate_privileged(engine, wallet, Decimal(21000), DAY_ONE)
    raised = await read_row(engine, wallet)

    await evaluate_privileged(engine, wallet, Decimal(20500), DAY_ONE + timedelta(minutes=1))
    kept = await read_row(engine, wallet)

    assert raised["peak_equity"] == Decimal(21000)
    assert kept["peak_equity"] == Decimal(21000)
    assert kept["peak_equity_at"] == raised["peak_equity_at"]


async def test_a_restart_finds_the_same_latch_and_the_same_reference(
    kill_switch_db: str, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """A second process, its own engine and pool, reading the durable state."""
    await evaluate(factory, wallet, Decimal(19600), DAY_ONE)

    restarted = create_async_engine(kill_switch_db, connect_args={"statement_cache_size": 0})
    try:
        after = async_sessionmaker(bind=restarted, expire_on_commit=False)
        async with tenant_session(after, wallet.org_id, wallet.user_id) as session:
            scopes = await effective_state(session, wallet.portfolio_id)
            again = await evaluate_and_persist(
                session,
                wallet.portfolio_id,
                portfolio_state(wallet, OPENING, as_of=DAY_ONE + timedelta(minutes=5)),
                DAY_ONE + timedelta(minutes=5),
            )
    finally:
        await restarted.dispose()

    assert scopes.portfolio is KillSwitchState.TRADING_DISABLED
    assert scopes.effective is KillSwitchState.TRADING_DISABLED
    assert again.latched is KillSwitchState.TRADING_DISABLED
    assert again.reference.equity_day_start == OPENING


async def test_two_concurrent_evaluations_write_one_transition(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The wallet's lock row is what serialises them, and the second one re-reads.

    Without the lock both sessions read ``ACTIVE``, both compute ``WARNING`` and
    both write a transition: two audit rows for one move, and the second
    ``UPDATE`` would silently be a no-op the deferred trigger still accepts,
    because its ``EXISTS`` finds the first session's row.
    """

    async def one() -> None:
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await evaluate_and_persist(
                session,
                wallet.portfolio_id,
                portfolio_state(wallet, Decimal(19800), as_of=DAY_ONE),
                DAY_ONE,
            )

    results = await asyncio.gather(one(), one(), return_exceptions=True)

    row = await read_row(engine, wallet)
    assert row["latch"] is KillSwitchState.WARNING
    assert len(row["transitions"]) == 1, results  # type: ignore[arg-type]


async def test_the_effective_state_is_the_most_restrictive_scope(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """An organization-wide block governs entries without being latched on the wallet.

    Copying the effective state into ``portfolios.kill_switch_state`` would make
    the wallet inherit a block it never earned — and the wallet would still be
    blocked after the organization resumed (Astra, T3.6 review).
    """
    async with engine.begin() as connection:
        # The organization scope carries its own audited-move trigger since the
        # T3.6 review (``ddl/paper.py``, ``organizations_kill_switch_is_audited``),
        # so even a test has to write the transition that explains the move.
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions (id, organization_id, scope, scope_id, "
                "from_state, to_state, reason, actor_type, actor_id) VALUES (:id, :org, "
                "'organization', :org, 'ACTIVE', 'TRADING_DISABLED', 'org-wide halt', 'user', :by)"
            ),
            {"id": uuid7(), "org": wallet.org_id, "by": wallet.user_id},
        )
        await connection.execute(
            text("UPDATE organizations SET kill_switch_state = 'TRADING_DISABLED' WHERE id = :id"),
            {"id": wallet.org_id},
        )

    async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
        scopes = await effective_state(session, wallet.portfolio_id)
        locked = await effective_state(session, wallet.portfolio_id, lock=True)
        evaluation = await evaluate_and_persist(
            session,
            wallet.portfolio_id,
            portfolio_state(wallet, OPENING, as_of=DAY_ONE),
            DAY_ONE,
        )

    assert scopes.organization is KillSwitchState.TRADING_DISABLED
    assert scopes.effective is KillSwitchState.TRADING_DISABLED
    assert scopes.blocks_entries is True
    assert locked.effective is KillSwitchState.TRADING_DISABLED
    assert evaluation.latched is KillSwitchState.ACTIVE, "the wallet's own latch is untouched"
    assert evaluation.effective is KillSwitchState.TRADING_DISABLED


async def test_the_system_scope_comes_from_configuration_and_still_blocks(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """There is no durable row for the system scope — recorded, not pretended away."""
    async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
        scopes = await effective_state(
            session, wallet.portfolio_id, system=KillSwitchState.EMERGENCY
        )

    assert scopes.effective is KillSwitchState.EMERGENCY
    assert scopes.blocks_entries is True


# --------------------------------------------------------------------------
# The grant gap this task found, proved as a statement
# --------------------------------------------------------------------------


async def test_no_deployed_role_can_write_both_halves_of_one_evaluation(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """The wall T3.6 ran into, stated as three statements instead of prose.

    One automatic evaluation writes three things that the contract says belong in
    one transaction: the daily reference and the peak
    (``portfolio_risk_state``), the latch the workers read (``portfolios``) with
    its audited transition, and the ``kill_switch.changed`` projection
    (``outbox_events``). As of this revision:

    - ``hunter_app`` may move the latch but ``portfolio_risk_state_guard``
      refuses its ``UPDATE`` of the lock row, and it holds ``SELECT`` only on
      ``outbox_events``;
    - ``hunter_worker`` may write the lock row and the outbox but holds
      ``SELECT`` only on ``portfolios``.

    Failure scenario: the São Paulo day turns while a wallet sits in WARNING with
    both triggers cleared. The rollover has to write the new daily reference *and*
    clear the WARNING together. Under ``hunter_app`` the reference write is
    refused and the wallet keeps yesterday's anchor; under ``hunter_worker`` the
    clear is refused and the wallet stays halved for a day it never lost anything
    in. Splitting them into two transactions leaves a window in which the
    reference is tomorrow's and the latch is yesterday's.
    """
    # The refusal arrives as a column grant ("permission denied") or as the
    # ``portfolio_risk_state_guard`` message, depending on how ``0006`` spells it
    # this week; both say the same thing, and the test asserts the capability
    # rather than the wording.
    with pytest.raises(DBAPIError, match="permission denied|may not be updated"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await session.execute(
                text(
                    "UPDATE portfolio_risk_state SET peak_equity = peak_equity "
                    "WHERE portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with role_session(factory, db_role="hunter_worker") as session:
            await session.execute(
                text("UPDATE portfolios SET name = 'renamed' WHERE id = :id"),
                {"id": wallet.portfolio_id},
            )

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with tenant_session(factory, wallet.org_id, wallet.user_id) as session:
            await session.execute(
                text(
                    "INSERT INTO outbox_events (event_id, stream, payload) "
                    "VALUES (:id, 'kill_switch.changed', '{}'::jsonb)"
                ),
                {"id": uuid7()},
            )
