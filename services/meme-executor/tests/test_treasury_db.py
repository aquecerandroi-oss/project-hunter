"""T4.54 — ``treasury_db`` against a real, migrated ``meme_treasury_swaps``
table: the insert/update lifecycle a real attempt drives, and the two reads
``treasury.py`` gates on (last attempt, 24 h confirmed spend).

Cleanup runs on ``db_engine`` (the admin connection), never on a
``hunter_worker`` session: that role has no ``DELETE`` on this table by
design (``0051``'s grants) — the same reason a real attempt is never erased.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _status(session: AsyncSession, swap_id: object) -> dict[str, object]:
    row = (
        (
            await session.execute(
                text(
                    "SELECT status, refusal, signature, sol_out_filled, wallet_sol_after "
                    "FROM meme_treasury_swaps WHERE id = :id"
                ),
                {"id": swap_id},
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    return dict(row)


async def _delete(db_engine: AsyncEngine, ids: list[object]) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM meme_treasury_swaps WHERE id = ANY(:ids)"), {"ids": ids}
        )


@pytest.mark.asyncio
async def test_last_attempt_at_and_24h_spend_start_empty(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        assert await treasury_db.last_attempt_at(session) is None
        assert await treasury_db.usdc_committed_last_24h(session, now=utcnow()) == Decimal(0)


@pytest.mark.asyncio
async def test_the_full_lifecycle_quoted_simulated_submitted_confirmed(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        swap_id = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("10"),
            sol_out_quoted=Decimal("0.068"),
            price_impact_pct=Decimal("0.0012"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.20"),
        )
        assert (await _status(session, swap_id))["status"] == "quoted"

        await treasury_db.mark_simulated(session, swap_id)
        assert (await _status(session, swap_id))["status"] == "simulated"

        await treasury_db.mark_submitted(session, swap_id, signature="6" * 88)
        row = await _status(session, swap_id)
        assert row["status"] == "submitted"
        assert row["signature"] == "6" * 88

        await treasury_db.mark_confirmed(
            session, swap_id, sol_out_filled=Decimal("0.067"), wallet_sol_after=Decimal("0.267")
        )
        row = await _status(session, swap_id)
        assert row["status"] == "confirmed"
        assert row["sol_out_filled"] == Decimal("0.067")
        assert row["wallet_sol_after"] == Decimal("0.267")

    await _delete(db_engine, [swap_id])


@pytest.mark.asyncio
async def test_a_refused_row_never_reaches_submitted(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        swap_id = await treasury_db.insert_refused(
            session,
            reason="sol_below_floor",
            refusal="price_impact_above_cap",
            usdc_in=Decimal("25"),
            sol_out_quoted=Decimal("0.16"),
            price_impact_pct=Decimal("0.02"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.20"),
        )
        row = await _status(session, swap_id)
        assert row["status"] == "refused"
        assert row["refusal"] == "price_impact_above_cap"
        assert row["signature"] is None

    await _delete(db_engine, [swap_id])


@pytest.mark.asyncio
async def test_a_quoted_row_can_still_be_refused_before_anything_sends(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        swap_id = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("10"),
            sol_out_quoted=Decimal("0.068"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.20"),
        )
        await treasury_db.mark_refused(session, swap_id, refusal="program_not_allowed:foo")
        row = await _status(session, swap_id)
        assert row["status"] == "refused"
        assert row["refusal"] == "program_not_allowed:foo"
        assert row["signature"] is None

    await _delete(db_engine, [swap_id])


@pytest.mark.asyncio
async def test_usdc_committed_last_24h_counts_submitted_and_confirmed_in_the_window(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    now = utcnow()
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        recent = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("12"),
            sol_out_quoted=Decimal("0.08"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, recent, signature="7" * 88)
        await treasury_db.mark_confirmed(
            session, recent, sol_out_filled=Decimal("0.079"), wallet_sol_after=Decimal("0.279")
        )
        still_quoted = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("30"),
            sol_out_quoted=Decimal("0.2"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        old_confirmed = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("40"),
            sol_out_quoted=Decimal("0.27"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, old_confirmed, signature="8" * 88)
        await treasury_db.mark_confirmed(
            session, old_confirmed, sol_out_filled=Decimal("0.26"), wallet_sol_after=Decimal("0.46")
        )
        await session.execute(
            text("UPDATE meme_treasury_swaps SET requested_at = :ts WHERE id = :id"),
            {"ts": now - timedelta(hours=30), "id": old_confirmed},
        )
        # T4.54b fix C: sent but not yet settled counts as spent until proven dead
        submitted = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("5"),
            sol_out_quoted=Decimal("0.03"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, submitted, signature="9" * 88)
        failed = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("7"),
            sol_out_quoted=Decimal("0.04"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, failed, signature="A" * 88)
        await treasury_db.mark_failed(session, failed)

        spent = await treasury_db.usdc_committed_last_24h(session, now=now)
        assert spent == Decimal("17"), (
            "confirmed (12) + submitted (5); the still-quoted, the failed and the "
            "30h-old confirmed rows must not count"
        )
        last = await treasury_db.last_attempt_at(session)
        assert last is not None

        pending = await treasury_db.submitted_swaps(session)
        assert [row.id for row in pending] == [submitted]
        assert pending[0].signature == "9" * 88
        assert pending[0].wallet_sol_before == Decimal("0.2")

    await _delete(db_engine, [recent, still_quoted, old_confirmed, submitted, failed])


WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
WSOL = "So11111111111111111111111111111111111111112"


@pytest.mark.asyncio
async def test_a_spot_swap_row_is_neither_inflow_nor_spend_nor_picked_by_the_reconcile(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """T4.73c (Astra, review of T4.73b): since ``0056`` the same table holds
    the generic spot swaps of ``infra/scripts/meme_spot_swap.py`` — rows with
    ``input_mint``/``output_mint`` set, whose ``sol_out_*`` are **token
    atoms** (10 402 273 WIF for a 0.02 SOL buy), not SOL. The three treasury
    reads must see only the USDC->SOL rows (``input_mint IS NULL``): a spot
    buy counted as inflow would push ``daily_loss_sol`` negative forever, and
    a stuck spot row picked by the reconcile would be marked ``confirmed``
    with ``sol_out_filled = 0``."""
    now = utcnow()
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        treasury = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("12"),
            sol_out_quoted=Decimal("0.08"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, treasury, signature="7" * 88)
        await treasury_db.mark_confirmed(
            session, treasury, sol_out_filled=Decimal("0.079"), wallet_sol_after=Decimal("0.279")
        )
        treasury_pending = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=Decimal("5"),
            sol_out_quoted=Decimal("0.03"),
            price_impact_pct=Decimal("0.001"),
            slippage_bps=50,
            wallet_sol_before=Decimal("0.2"),
        )
        await treasury_db.mark_submitted(session, treasury_pending, signature="9" * 88)

        # The spot rows, exactly as meme_spot_swap_db.insert_row writes them.
        spot_confirmed = uuid.uuid4()
        spot_submitted = uuid.uuid4()
        for swap_id, status, signature, filled, wallet_after in (
            (spot_confirmed, "confirmed", "B" * 88, Decimal("10402273"), Decimal("0.48")),
            (spot_submitted, "submitted", "C" * 88, None, None),
        ):
            await session.execute(
                text(
                    "INSERT INTO meme_treasury_swaps (id, reason, usdc_in, sol_out_quoted, "
                    "  sol_out_filled, price_impact_pct, slippage_bps, signature, status, "
                    "  refusal, wallet_sol_before, wallet_sol_after, input_mint, output_mint) "
                    "VALUES (:id, 'spot_swap:SOL->WIF', 0.02, 10402273, :filled, 0.001, 50, "
                    "  :signature, :status, NULL, 0.5, :wallet_after, :input_mint, :output_mint)"
                ),
                {
                    "id": swap_id,
                    "filled": filled,
                    "wallet_after": wallet_after,
                    "signature": signature,
                    "status": status,
                    "input_mint": WSOL,
                    "output_mint": WIF,
                },
            )

        inflow = await treasury_db.sol_inflow_since(session, since=now - timedelta(hours=1))
        assert inflow == Decimal("0.079") + Decimal("0.03"), (
            "confirmed treasury (filled 0.079) + submitted treasury (quoted 0.03); "
            "the 10 402 273 WIF atoms of the spot rows are not SOL"
        )
        spent = await treasury_db.usdc_committed_last_24h(session, now=now)
        assert spent == Decimal("17"), "the 0.02 SOL of the spot rows is not USDC"
        pending = await treasury_db.submitted_swaps(session)
        assert [row.id for row in pending] == [treasury_pending], (
            "a stuck spot row is the script operator's to reconcile, never the treasury's"
        )

    await _delete(db_engine, [treasury, treasury_pending, spot_confirmed, spot_submitted])
