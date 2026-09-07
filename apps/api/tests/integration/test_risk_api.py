"""The kill switch over HTTP — RISK_ENGINE.md §5, SECURITY.md §2.

Reading it is a dashboard read (VIEWER); **resuming is OWNER** — T3.1c split the
one SECURITY.md §2 line in two, because latching is a protection anyone who
operates should be able to trigger and leaving a latched block is what the
directive reserves for the owner's authorisation. Both are asserted here against
a live app, a live Postgres and real signed tokens.

The refusal matters more than the success: a resume while the automatic
assessment still blocks answers **409 problem+json with the numbers in it**, and
writes nothing — no transition, no state change. A resume that the next
evaluation would undo is worse in the log than no resume (v2.1, §5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.risk import evaluate_and_persist
from hunter_risk import PortfolioState, sao_paulo_day_start_utc

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

OPENING = Decimal(20000)


class Wallet:
    def __init__(self, actor: Actor, portfolio_id: uuid.UUID) -> None:
        self.actor = actor
        self.portfolio_id = portfolio_id

    @property
    def base(self) -> str:
        return f"/api/v1/orgs/{self.actor.org_id}/portfolios/{self.portfolio_id}/risk"


@pytest_asyncio.fixture
async def wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> Wallet:
    """An organization with an opened principal wallet and its lock row.

    Written through the API's own session factory as ``hunter_app`` under RLS —
    the same role the routes run as, so nothing here is provable only because a
    superuser wrote it.
    """
    unique = uuid.uuid4().hex[:8]
    actor = await create_org(client, make_actor(f"risk-{unique}"), f"Risk {unique}")
    assert actor.org_id is not None and actor.workspace_id is not None
    portfolio_id = uuid7()
    day_start = sao_paulo_day_start_utc(utcnow())
    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        await session.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "initial_capital) VALUES (:id, :org, :ws, 'principal', 'paper', :capital)"
            ),
            {
                "id": portfolio_id,
                "org": actor.org_id,
                "ws": actor.workspace_id,
                "capital": OPENING,
            },
        )
        await session.execute(
            text(
                "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, trading_day, "
                "trading_day_start_utc, equity_day_start, day_reference_observed_at, peak_equity, "
                "peak_equity_at) VALUES (:org, :pf, :day, :start, :equity, :start, :equity, :start)"
            ),
            {
                "org": actor.org_id,
                "pf": portfolio_id,
                "day": day_start.date(),
                "start": day_start,
                "equity": OPENING,
            },
        )
    return Wallet(actor, portfolio_id)


def state(wallet: Wallet, equity: Decimal, at: datetime) -> PortfolioState:
    return PortfolioState(
        portfolio_id=wallet.portfolio_id,
        as_of=at,
        equity=equity,
        cash=equity,
        peak_equity=OPENING,
        day_start_equity=OPENING,
        day_start_utc=sao_paulo_day_start_utc(at),
    )


async def block(
    session_factory: async_sessionmaker[AsyncSession], wallet: Wallet, equity: Decimal
) -> None:
    """Drive the wallet down the automatic ladder, the way the worker does.

    As ``hunter_worker``: since ``0007_paper_roles`` an automatic evaluation is
    the engine's, in one transaction (DATABASE.md §19.2). The API's business with
    the kill switch is the *resume*, which is what these tests exercise through
    the route.
    """
    now = utcnow()
    assert wallet.actor.org_id is not None
    async with tenant_session(
        session_factory, wallet.actor.org_id, wallet.actor.user_id, db_role="hunter_worker"
    ) as session:
        await evaluate_and_persist(session, wallet.portfolio_id, state(wallet, equity, now), now)


async def snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    equity: Decimal,
    *,
    age_s: int,
) -> None:
    """One point of the equity curve — the durable evidence a resume reads.

    ``age_s=0`` matters: the evidence has to be observed **after** the move being
    resumed, or it describes the wallet before the block (Astra, review of this
    diff). The blocking evaluation runs microseconds earlier in these tests.

    Written as ``hunter_worker``, because since ``0007_paper_roles`` the curve is
    read-only to the API — it is the evidence a resume reads, and a role that can
    write it can fabricate the recovery it then claims (§19.2).
    """
    assert wallet.actor.org_id is not None
    async with tenant_session(
        session_factory, wallet.actor.org_id, wallet.actor.user_id, db_role="hunter_worker"
    ) as session:
        await session.execute(
            text(
                "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                "realized_pnl_cum, peak_equity) VALUES (:org, :pf, '1m', :ts, :equity, :equity, "
                "0, 0, 0, :peak)"
            ),
            {
                "org": wallet.actor.org_id,
                "pf": wallet.portfolio_id,
                "ts": utcnow() - timedelta(seconds=age_s),
                "equity": equity,
                "peak": OPENING,
            },
        )


async def test_the_kill_switch_read_publishes_the_motive_and_the_evidence(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    await block(session_factory, wallet, Decimal(19600))

    response = await client.get(f"{wallet.base}/kill-switch", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effective"] == KillSwitchState.TRADING_DISABLED.value
    assert body["blocks_entries"] is True
    assert body["scopes"] == {
        "system": "ACTIVE",
        "organization": "ACTIVE",
        "portfolio": "TRADING_DISABLED",
    }
    assert body["daily_reference"]["available"] is True
    assert Decimal(body["daily_reference"]["equity_day_start"]) == OPENING
    assert Decimal(body["peak"]["equity"]) == OPENING
    transition = body["last_transition"]
    assert transition["from_state"] == "ACTIVE"
    assert transition["to_state"] == "TRADING_DISABLED"
    assert transition["actor_type"] == "system"
    assert transition["evidence"]["daily_loss_pct"] == "0.02"
    assert transition["evidence"]["blocked_daily_loss_pct"] == "0.02"


async def test_a_resume_is_refused_with_the_numbers_while_the_trigger_still_bites(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    await block(session_factory, wallet, Decimal(19600))
    await snapshot(session_factory, wallet, Decimal(19600), age_s=0)

    refused = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "I would like to trade"},
        headers=wallet.actor.headers,
    )

    assert refused.status_code == 409, refused.text
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert "still TRADING_DISABLED" in refused.json()["detail"]
    after = await client.get(f"{wallet.base}/kill-switch", headers=wallet.actor.headers)
    assert after.json()["effective"] == "TRADING_DISABLED"
    assert after.json()["last_transition"]["actor_type"] == "system", "nothing was written"


async def test_a_resume_on_a_recovered_wallet_is_audited_with_the_person(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    await block(session_factory, wallet, Decimal(19600))
    await snapshot(session_factory, wallet, OPENING, age_s=0)

    resumed = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "reviewed the day with Everton"},
        headers=wallet.actor.headers,
    )

    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["from_state"] == "TRADING_DISABLED"
    assert body["to_state"] == "ACTIVE"
    assert body["actor_id"] == str(wallet.actor.user_id)
    after = (await client.get(f"{wallet.base}/kill-switch", headers=wallet.actor.headers)).json()
    assert after["effective"] == "ACTIVE"
    assert after["last_transition"]["actor_type"] == "user"
    assert after["last_transition"]["actor_id"] == str(wallet.actor.user_id)
    assert Decimal(after["peak"]["equity"]) == OPENING, "a resume never redefines the peak"
    assert Decimal(after["daily_reference"]["equity_day_start"]) == OPENING


async def test_a_resume_with_no_fresh_equity_is_refused(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], wallet: Wallet
) -> None:
    """Two minutes is one missed sample of a per-minute curve; older is not proof."""
    await block(session_factory, wallet, Decimal(19600))
    await snapshot(session_factory, wallet, OPENING, age_s=600)

    refused = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "it looked fine an hour ago"},
        headers=wallet.actor.headers,
    )

    assert refused.status_code == 409, refused.text
    assert "stale equity" in refused.json()["detail"]


async def test_an_active_wallet_has_nothing_to_resume(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    refused = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "just in case"},
        headers=wallet.actor.headers,
    )

    assert refused.status_code == 409
    assert "nothing to resume" in refused.json()["detail"]


async def test_a_blank_reason_is_refused_before_anything_is_read(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    response = await client.post(
        f"{wallet.base}/kill-switch/resume", json={"reason": ""}, headers=wallet.actor.headers
    )

    assert response.status_code == 422


async def test_another_organizations_wallet_is_a_404_not_a_403(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor], wallet: Wallet
) -> None:
    """The wallet exists; the caller is a member of *their own* org, not this one."""
    unique = uuid.uuid4().hex[:8]
    outsider = await create_org(client, make_actor(f"risk-out-{unique}"), f"Outsider {unique}")

    response = await client.get(
        f"/api/v1/orgs/{outsider.org_id}/portfolios/{wallet.portfolio_id}/risk/kill-switch",
        headers=outsider.headers,
    )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_wallet_with_no_risk_state_is_a_404(
    client: httpx.AsyncClient, wallet: Wallet
) -> None:
    unknown = uuid7()

    response = await client.get(
        f"/api/v1/orgs/{wallet.actor.org_id}/portfolios/{unknown}/risk/kill-switch",
        headers=wallet.actor.headers,
    )

    assert response.status_code == 404


def test_the_day_is_sao_paulo_not_utc() -> None:
    """A guard on the anchor the whole route set reports, with no database in it."""
    midnight_utc = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)

    assert sao_paulo_day_start_utc(midnight_utc) == datetime(2026, 9, 6, 3, 0, tzinfo=UTC)


async def test_a_trader_may_not_resume_and_the_owner_may(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    wallet: Wallet,
) -> None:
    """T3.1c: leaving a latched block is the owner's act, and only the owner's.

    The old floor was TRADER (SECURITY.md §2 had latching and resuming on one
    line), so a trader invited into the organization could unblock a wallet the
    engine had blocked, without the owner. The scenario is the whole point of the
    directive's "retomar somente com a minha autorização", so it is asserted end
    to end: same wallet, same recovered curve, two callers.
    """
    assert wallet.actor.org_id is not None
    trader = make_actor(f"trader-{uuid.uuid4().hex[:8]}")
    invited = await client.post(
        f"/api/v1/orgs/{wallet.actor.org_id}/invitations",
        json={"email": trader.email, "role": "TRADER"},
        headers=wallet.actor.headers,
    )
    assert invited.status_code == 201, invited.text
    accepted = await client.post(
        f"/api/v1/invitations/{invited.json()['token']}/accept", headers=trader.headers
    )
    assert accepted.status_code == 200, accepted.text

    await block(session_factory, wallet, Decimal(19600))
    await snapshot(session_factory, wallet, OPENING, age_s=0)

    refused = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "I can trade, so I can unblock"},
        headers=trader.headers,
    )
    assert refused.status_code == 403, refused.text
    still = (await client.get(f"{wallet.base}/kill-switch", headers=trader.headers)).json()
    assert still["effective"] == "TRADING_DISABLED"
    assert still["last_transition"]["actor_type"] == "system", "the refusal wrote nothing"

    resumed = await client.post(
        f"{wallet.base}/kill-switch/resume",
        json={"reason": "reviewed the day"},
        headers=wallet.actor.headers,
    )
    assert resumed.status_code == 200, resumed.text
    after = (await client.get(f"{wallet.base}/kill-switch", headers=wallet.actor.headers)).json()
    assert after["effective"] == "ACTIVE"
    assert after["last_transition"]["actor_type"] == "user"
    assert after["last_transition"]["actor_id"] == str(wallet.actor.user_id)


async def test_an_owner_of_another_organization_cannot_resume_this_wallet(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    wallet: Wallet,
) -> None:
    """T3.1c security review, suggestion 5 — the *write* half of the cross-org 404.

    ``test_another_organizations_wallet_is_a_404_not_a_403`` covers the read.
    The resume is the one route on this wallet that changes anything, and it is
    the one the directive reserves for the owner, so "OWNER of A pressing the
    button on B's wallet" is the scenario worth stating: being an owner
    *somewhere* must not be being an owner *here*.

    Both spellings of the request are asserted, because they fail in different
    places and both have to end in the same 404:

    - **A's org id in the path, B's wallet id.** ``require_org(OWNER)`` passes —
      the caller really is an owner of that organization — and ``_owned`` is what
      refuses, because the wallet belongs to nobody in it;
    - **B's org id in the path.** ``require_org`` refuses first, with the same
      404 and the same body, so the API is not an existence oracle for
      organizations (SECURITY.md §3.3).

    And nothing is written: the wallet stays latched, and the last transition is
    still the automatic one the engine wrote.
    """
    assert wallet.actor.org_id is not None
    unique = uuid.uuid4().hex[:8]
    outsider = await create_org(client, make_actor(f"risk-out-{unique}"), f"Outsider {unique}")

    await block(session_factory, wallet, Decimal(19600))
    await snapshot(session_factory, wallet, OPENING, age_s=0)

    for org_id, headers in (
        (outsider.org_id, outsider.headers),
        (wallet.actor.org_id, outsider.headers),
    ):
        response = await client.post(
            f"/api/v1/orgs/{org_id}/portfolios/{wallet.portfolio_id}/risk/kill-switch/resume",
            json={"reason": "I am an owner, just not of this"},
            headers=headers,
        )
        assert response.status_code == 404, (org_id, response.text)
        assert response.headers["content-type"].startswith("application/problem+json")

    after = (await client.get(f"{wallet.base}/kill-switch", headers=wallet.actor.headers)).json()
    assert after["effective"] == "TRADING_DISABLED", "the wallet stayed latched"
    assert after["last_transition"]["actor_type"] == "system", "the refusal wrote nothing"
