"""V6 — stale inputs, reconnections and restarts never produce a silent approval.

**Objetivo (spec V6):** the contract's "fail closed" pattern (§7) survives real
infrastructure — an admission that reads a stale volume or an unobserved book
never approves, and a restarted worker recovers a partially-filled protection
from Postgres alone, never losing or duplicating the remaining quantity.

**Scope note (spec §13, updated by this task):** V6 steps 3 (WS drop with a
gap) and 4 (Redis loss mid-decision) are not deliverable here — both need the
SPOT collector wired into the market-worker's hot state (T3.0b) and this
worker's own Redis-backed ``SpotMarketData`` reading it, and
``notes-T3.5.md`` §5.3 records that connection as not built yet:
``StaticSpotMarketData`` (the double every test in this suite uses) never
touches Redis at all, so there is no gap or outage to simulate honestly. This
is recorded in ``.claude/state/notes-T3.9b.md``, not silently skipped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_execution_worker.market_data import SpotSnapshot
from hunter_risk.inputs import BookLevel, MarketIdentity, MarketLiquidity

from .conftest import (
    HEALTHY_MINUTE,
    NOW,
    admit_entry,
    admit_in,
    at,
    check_of,
    liquidity_for,
    read_exit_intents,
    read_orders,
    read_positions,
    read_proposal,
    request_for,
    run_entries,
    run_protection,
    spot_book,
    spot_trade,
    static_data,
    tenant_session,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .conftest import Wallet

pytestmark = [pytest.mark.integration]

ENTRY_REF = Decimal(100)
STOP = Decimal("97.5")
WORKER_ROLE = "hunter_worker"


def _fresh_liquidity(
    identity: MarketIdentity,
    *,
    price_ts: datetime,
    book_ts: datetime | None,
    volume_ts: datetime | None,
    asks: tuple[BookLevel, ...],
) -> MarketLiquidity:
    """A liquidity picture with every timestamp named explicitly — never
    ``datetime.now()`` (spec §12 trap 2): a stale test builds a stale input on
    purpose, at an instant it chooses.
    """
    return MarketLiquidity(
        market=identity,
        last_price=Decimal(100),
        mid_price=Decimal(100),
        best_bid=Decimal("99.99"),
        best_ask=Decimal("100.01"),
        price_ts=price_ts,
        asks=asks,
        book_ts=book_ts,
        quote_volume_24h=Decimal(100_000_000),
        last_minute_quote_volume=HEALTHY_MINUTE,
        median_30m_quote_volume=HEALTHY_MINUTE,
        volume_window_complete=True,
        volume_ts=volume_ts,
        gap_state="ok",
        in_universe=True,
    )


class TestAMinuteOldVolumeFortyFiveMinutesAgoNeverApproves:
    """Spec V6 step 1: "volume do minuto de 45 min atrás" — the exact scenario
    already green in the pure core
    (``test_review_findings.py::TestFinding3``); this proves the same
    ``MarketLiquidity`` that would arrive from the admission's own caller (a
    strategy or the manual route) is rejected the same way once it goes
    through ``admit()`` and lands in the persisted decision, not just in the
    engine called directly.

    **O que refuta:** ``approved=True`` with a volume older than
    ``max_volume_age_s`` (120 s, ``paper_v1``); a persisted ``sizing`` computed
    from a stale participation reference; ``liquidity_24h`` reported as
    anything but ``unavailable``.
    """

    async def test_a_volume_stamped_45_minutes_ago_is_unavailable_not_stale_but_ok(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        stale_liquidity = _fresh_liquidity(
            market.identity,
            price_ts=NOW,  # the price itself is fresh
            book_ts=NOW,
            volume_ts=at(minutes=-45),  # the volume snapshot is not
            asks=(BookLevel(price=Decimal("100.01"), qty=Decimal(10_000)),),
        )
        request = request_for(wallet, market, entry_ref=ENTRY_REF, stop=STOP)
        async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
            result = await admit_in(
                session,
                wallet,
                market,
                request,
                now=NOW,
                marks={market.id: ENTRY_REF},
                liquidity=stale_liquidity,
            )
        assert result.approved is False

        row = await read_proposal(engine, result.proposal_id)
        assert row.status == "rejected"
        assert row.risk_decision["sizing"] is None
        liquidity_check = check_of(row.risk_decision, "liquidity_24h")
        assert liquidity_check["state"] == "unavailable"
        assert "45" not in liquidity_check["message"]  # the message names seconds, not minutes
        assert "volume" in liquidity_check["message"]


class TestAnUnobservedBookNeverInventsATimestamp:
    """Spec V6 step 2: SPOT's book carries no exchange clock at all
    (``received_at`` is the only stamp, ``.claude/state/notes-T3.0a.md`` §4);
    at the Risk Engine's own input, the equivalent fact is "the book was not
    observed" (``asks=()``, ``book_ts=None``) — and the check must say
    ``unavailable``, never substitute the price feed's timestamp or a
    plausible number.

    **O que refuta:** ``book_depth`` (or any cap derived from it) reporting a
    value when the book was never observed; the check passing because another
    field (``price_ts``) happened to be fresh.
    """

    async def test_no_book_observed_makes_book_depth_unavailable_not_passed(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        no_book_liquidity = _fresh_liquidity(
            market.identity, price_ts=NOW, book_ts=None, volume_ts=NOW, asks=()
        )
        request = request_for(wallet, market, entry_ref=ENTRY_REF, stop=STOP)
        async with tenant_session(factory, wallet.org_id, db_role=WORKER_ROLE) as session:
            result = await admit_in(
                session,
                wallet,
                market,
                request,
                now=NOW,
                marks={market.id: ENTRY_REF},
                liquidity=no_book_liquidity,
            )
        assert result.approved is False
        row = await read_proposal(engine, result.proposal_id)
        book_check = check_of(row.risk_decision, "book_depth")
        assert book_check["state"] == "unavailable"
        assert "nao observado" in book_check["message"] or "não observado" in book_check["message"]


class TestARestartRecoversAPartiallyFilledProtectionFromPostgresAlone:
    """Spec V6 step 5: kill the process between the stop's partial fill (4 of
    10 vendable that cycle) and the new attempt for the rest — "never a
    position of six units silently unprotected".

    The "restart" is what ``services/execution-worker/tests
    /test_restart_recovery.py`` already established as the honest one (§12
    trap 7): every object this test built is dropped, and a **fresh**
    ``run_protection`` call — no carried-over ``TriggerWatermarks`` or
    ``DegradedRetries``, exactly what a new process starts with — rebuilds the
    intention and finishes the job.

    **O que refuta:** the intention ending anything but ``open`` with
    ``filled_qty`` set to what really sold; a second attempt reusing the first
    attempt's ``client_order_id``; the six remaining units left with no live
    intention at all.
    """

    async def test_the_remainder_gets_a_new_attempt_with_its_own_identity(
        self, engine: AsyncEngine, factory: async_sessionmaker[AsyncSession], wallet: Wallet
    ) -> None:
        market = wallet.market("SOLUSDT")
        decision = await admit_entry(
            factory,
            wallet,
            market,
            now=NOW,
            marks={market.id: ENTRY_REF},
            liquidity=liquidity_for(market, as_of=NOW, last_price=ENTRY_REF),
        )
        assert decision.approved
        fill_at = at(seconds=1)
        book_at = fill_at + timedelta(milliseconds=300)
        entries = await run_entries(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(market, received_at=book_at, bid=ENTRY_REF, ask=ENTRY_REF),
                    trades=(spot_trade(market, price=ENTRY_REF, ts=fill_at, trade_id=1),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=fill_at + timedelta(seconds=1),
        )
        assert [o.status for o in entries] == ["filled"]
        net_base = Decimal("18.499482")  # 18,518 x 0,999 — §0/V5's own number

        # Cycle 1: a shallow book gives the stop only 4 of the position it
        # asks for — the literal "um stop de 10 unidades encontra 4
        # vendáveis" of RISK_ENGINE.md §10, on this suite's own quantities.
        stop_at = at(minutes=1)
        shallow_at = stop_at + timedelta(milliseconds=300)
        partial_cycle_at = stop_at + timedelta(seconds=1)
        shallow_depth = Decimal(4)
        partial = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market,
                        received_at=shallow_at,
                        bid=Decimal(95),
                        ask=Decimal("95.05"),
                        qty=shallow_depth,
                    ),
                    trades=(spot_trade(market, price=Decimal(95), ts=stop_at, trade_id=2),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=partial_cycle_at,
        )
        assert [o.status for o in partial] == ["partially_filled"]

        positions = await read_positions(engine, wallet)
        assert positions[0].qty == net_base - shallow_depth
        intents = await read_exit_intents(engine, wallet)
        assert intents[0].filled_qty == shallow_depth
        assert intents[0].state == "open"  # never closed with 6 units unaccounted
        first_attempt = (await read_orders(engine, wallet))[-1].client_order_id

        # The "restart": a brand-new cycle, no watermarks or backoff carried
        # over from the call above — the process died and came back with
        # nothing in memory (§12 trap 7). It finishes the job with an
        # attempt of its own identity.
        later = partial_cycle_at + timedelta(minutes=1)
        later_book_at = later + timedelta(milliseconds=300)
        later_cycle_at = later + timedelta(seconds=1)
        finished = await run_protection(
            factory,
            wallet,
            static_data(
                market,
                SpotSnapshot(
                    market=market.identity,
                    book=spot_book(
                        market, received_at=later_book_at, bid=Decimal(95), ask=Decimal("95.05")
                    ),
                    trades=(spot_trade(market, price=Decimal(95), ts=later, trade_id=3),),
                    avg_price=ENTRY_REF,
                ),
            ),
            now=later_cycle_at,
        )
        assert [o.status for o in finished] == ["filled"]

        after_positions = await read_positions(engine, wallet)
        after_orders = await read_orders(engine, wallet)
        second_attempt = after_orders[-1].client_order_id
        assert second_attempt != first_attempt  # its own identity, never reused
        assert after_positions[0].status == "closing"  # dust, §T3.5b — not an unprotected loss
        after_intents = await read_exit_intents(engine, wallet)
        assert after_intents[0].filled_qty == net_base - after_positions[0].qty
