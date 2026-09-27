"""I2 (EXP-M26, ``docs/design/exp-m26-grafico-moedas-maduras.md`` §1.6), against
a real Postgres: an ``approved`` proposal without a bet yet is pinned until it
decides or :data:`APPROVED_PIN_TERMINAL_S` after ``decided_at`` — the design's
own failure scenario is a research proposal born ``approved`` (``research_only``
sets never sit in ``proposed``, §2) whose mint leaves the top-K before the
fill's photo ever lands (``obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md``).

The sequence the design's own integration test asks for: retention (I1, pure —
covered in ``test_tracker.py``) → ``approved`` → fill → the 15 s series follows
by membership, not age (``fast_lane.young_mints``) → close, and the pin (and
the series) end. The T4.91/T4.95 exclusions (a recuo arm's bets pin nothing,
ordinary or EXP-M26) stay intact because those bets belong to rule sets whose
``exp_ref`` is never ``'EXP-M26'``.

Run alone (``timeout 590``): shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.entry_pullback import PULLBACK_ARM_RULE_SET_ID
from hunter_meme_worker.fast_lane import young_mints
from hunter_meme_worker.lab import LabContext, LabState
from hunter_meme_worker.lab_pins import reload_pinned_mints
from hunter_meme_worker.repo import TokenRow, load_mature_candidates, upsert_token
from hunter_meme_worker.tracker import MintTracker, TrackedMint
from hunter_meme_worker.tracker_pins import (
    APPROVED_PIN_TERMINAL_S,
    pinned_mints,
    pinned_mints_exp_m26,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

WORKER_ROLE = "hunter_worker"

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

_RULE_SET = text(
    "INSERT INTO meme_rule_sets (id, name, version, kind, code_ref, exp_ref) "
    "VALUES (:id, :name, '1', 'research_only', 'test', 'EXP-M26')"
)
_PROPOSAL = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) "
    "VALUES (:id, :mint, :rs, 'operator', :status, :expires_at, '{}'::jsonb, 'rules', :decided_at)"
)
_BET = text(
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
    "  initial_risk_sol, params) "
    "VALUES (:id, :p, :rs, :mint, :entry_at, '{}'::jsonb, 0.07, '{}'::jsonb)"
)
_FILL = text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :p")
_CLOSE_BET = text(
    "UPDATE meme_paper_bets SET status = 'closed', exit_at = :at, "
    '  exit = \'{"reason": "target"}\'::jsonb, pnl_sol = 0.01, r_multiple = 0.1 WHERE id = :id'
)


async def _rule_set(connection: AsyncConnection) -> str:
    rule_set_id = str(uuid4())
    await connection.execute(_RULE_SET, {"id": rule_set_id, "name": f"m26_test_{uuid4().hex[:8]}"})
    return rule_set_id


async def _proposal(
    connection: AsyncConnection, *, mint: str, rule_set_id: str, decided_at: datetime, status: str
) -> str:
    proposal_id = str(uuid4())
    await connection.execute(
        _PROPOSAL,
        {
            "id": proposal_id,
            "mint": mint,
            "rs": rule_set_id,
            "status": status,
            "expires_at": decided_at + timedelta(seconds=120),
            "decided_at": decided_at,
        },
    )
    return proposal_id


async def _open_bet(
    connection: AsyncConnection, *, mint: str, rule_set_id: str, proposal_id: str
) -> str:
    bet_id = str(uuid4())
    await connection.execute(
        _BET,
        {"id": bet_id, "p": proposal_id, "rs": rule_set_id, "mint": mint, "entry_at": NOW},
    )
    await connection.execute(_FILL, {"bet": bet_id, "p": proposal_id})
    return bet_id


def _mature(mint: str) -> TrackedMint:
    """60 minutes old — well past the fast lane's 300 s and its 1 800 s pinned
    ceiling, so admission through :attr:`MintTracker.pinned_exp_m26` is the
    only thing that can explain the mint staying in the 15 s series at all."""
    created = NOW - timedelta(minutes=60)
    return TrackedMint(mint=mint, first_seen_at=created, created_at=created)


async def test_approved_without_a_bet_pins_until_the_terminal_deadline(
    db_engine: AsyncEngine,
) -> None:
    mint = f"M26_{uuid4().hex[:8]}"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            rule_set_id = await _rule_set(connection)
            await _proposal(
                connection, mint=mint, rule_set_id=rule_set_id, decided_at=NOW, status="approved"
            )
            session = AsyncSession(bind=connection)
            fresh = await pinned_mints_exp_m26(session, now=NOW)
            expired = await pinned_mints_exp_m26(
                session, now=NOW + timedelta(seconds=APPROVED_PIN_TERMINAL_S + 1)
            )
            ordinary = await pinned_mints(session, now=NOW)
            await session.close()
        finally:
            await transaction.rollback()
    assert mint in fresh, "an approved proposal without a bet pins (design §1.6)"
    assert mint not in expired, "180 s after decided_at, the terminal deadline ends the pin"
    assert mint not in ordinary, "an EXP-M26 pin is never the ordinary kind"


async def test_the_open_bet_pins_past_the_terminal_deadline_and_the_close_ends_it(
    db_engine: AsyncEngine,
) -> None:
    """Retention → approved → fill → the 15 s series follows by membership,
    not age → close: the design's own sequence for this integration test."""
    mint = f"M26_{uuid4().hex[:8]}"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            rule_set_id = await _rule_set(connection)
            proposal_id = await _proposal(
                connection, mint=mint, rule_set_id=rule_set_id, decided_at=NOW, status="approved"
            )
            bet_id = await _open_bet(
                connection, mint=mint, rule_set_id=rule_set_id, proposal_id=proposal_id
            )
            session = AsyncSession(bind=connection)
            after_fill = await pinned_mints_exp_m26(
                session, now=NOW + timedelta(seconds=APPROVED_PIN_TERMINAL_S + 1)
            )

            tracker = MintTracker(window_minutes=1440, cap=200)
            tracker.observe(_mature(mint))
            tracker.pin_exp_m26(after_fill)
            still_series = young_mints(
                tracker, NOW + timedelta(minutes=10), max_age_s=300, pinned_max_age_s=1800
            )
            assert [t.mint for t in still_series] == [mint], (
                "an open EXP-M26 bet keeps the 15 s series whatever the mint's age"
            )

            await connection.execute(_CLOSE_BET, {"id": bet_id, "at": NOW + timedelta(minutes=15)})
            after_close = await pinned_mints_exp_m26(session, now=NOW + timedelta(minutes=20))
            await session.close()
        finally:
            await transaction.rollback()
    assert mint not in after_close, "a closed bet no longer pins — reinício reads the same truth"
    tracker2 = MintTracker(window_minutes=1440, cap=200)
    tracker2.observe(_mature(mint))
    tracker2.pin_exp_m26(after_close)
    assert (
        young_mints(tracker2, NOW + timedelta(minutes=20), max_age_s=300, pinned_max_age_s=1800)
        == []
    ), "unpinned, the 60-minute-old mint falls back to the ordinary age rule and drops out"


async def test_a_recuo_arms_open_bet_still_pins_nothing_ordinary_or_exp_m26(
    db_engine: AsyncEngine,
) -> None:
    mint = f"RECUO_{uuid4().hex[:8]}"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            proposal_id = await _proposal(
                connection,
                mint=mint,
                rule_set_id=PULLBACK_ARM_RULE_SET_ID,
                decided_at=NOW,
                status="approved",
            )
            await _open_bet(
                connection, mint=mint, rule_set_id=PULLBACK_ARM_RULE_SET_ID, proposal_id=proposal_id
            )
            session = AsyncSession(bind=connection)
            ordinary = await pinned_mints(session, now=NOW)
            exp_m26 = await pinned_mints_exp_m26(session, now=NOW)
            await session.close()
        finally:
            await transaction.rollback()
    assert mint not in ordinary, "T4.91: the recuo arm's open bets pin nothing ordinary"
    assert mint not in exp_m26, "its rule set's exp_ref is not EXP-M26"


async def test_reload_pinned_mints_rescues_a_pin_the_cap_already_dropped(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Astra's review, must-fix 1: a research proposal can be pinned
    (``approved`` without a bet yet) well after the tracker's cap already
    dropped the mint — a name-only pin with no ``TrackedMint`` behind it
    produces no photo at all (``fast_lane.young_mints`` only reads
    ``tracker.snapshot()``). The reload must rescue it by identity, the same
    rescue T4.16b's boot warmup already does."""
    mint = f"M26_{uuid4().hex[:8]}"
    created_at = NOW - timedelta(minutes=60)
    async with db_engine.begin() as connection:
        rule_set_id = await _rule_set(connection)
        await _proposal(
            connection, mint=mint, rule_set_id=rule_set_id, decided_at=NOW, status="approved"
        )
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        await upsert_token(
            session,
            TokenRow(
                mint=mint,
                first_seen_source="pumpportal_ws",
                first_seen_at=created_at,
                last_seen_at=created_at,
                created_at=created_at,
                initial_real_token_reserves=Decimal("793100000"),
                progress_denominator_source="observed_virgin",
                total_supply=Decimal(1_000_000_000),
                mayhem_enabled=False,
            ),
        )
    tracker = MintTracker(window_minutes=1440, cap=200)
    assert tracker.get(mint) is None, "the cap's own eviction: not in the tracker at all"
    ctx = LabContext(
        config=MemeConfig(),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=None,
        heartbeat=None,
        tracker=tracker,
    )
    await reload_pinned_mints(ctx, now=NOW + timedelta(seconds=1))
    assert mint in tracker.pinned_exp_m26
    assert tracker.get(mint) is not None, "the pin rescued the TrackedMint, not just its name"


async def test_load_mature_candidates_excludes_already_pinned_mints(
    db_engine: AsyncEngine,
) -> None:
    """Astra's review, must-fix 3: a bare ``LIMIT :top_k`` would let an
    already-pinned mint (never in need of this budget) spend one of the K
    slots a genuinely unpinned mature mint needed on restart."""
    pinned_mint = f"M26_{uuid4().hex[:8]}"
    free_mint = f"M26_{uuid4().hex[:8]}"
    created_at = NOW - timedelta(minutes=60)
    async with db_engine.begin() as connection:
        for mint, mcap in ((pinned_mint, "999"), (free_mint, "1")):
            await connection.execute(
                text(
                    "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, "
                    "  last_seen_at, created_at, initial_real_token_reserves, "
                    "  progress_denominator_source, total_supply, mayhem_enabled) "
                    "VALUES (:mint, 'pumpportal_ws', :at, :at, :at, 793100000, "
                    "  'observed_virgin', 1000000000, false)"
                ),
                {"mint": mint, "at": created_at},
            )
            await connection.execute(
                text(
                    "INSERT INTO meme_curve_snapshots (observed_at, mint, source, "
                    "  virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
                    "  real_token_reserves, total_supply, complete) "
                    "VALUES (:at, :mint, 'pumpfun_rest', :mcap, 1000000000, "
                    "  :mcap, 720100000, 1000000000, false)"
                ),
                {"mint": mint, "at": NOW, "mcap": mcap},
            )
        session = AsyncSession(bind=connection)
        with_exclusion = await load_mature_candidates(
            session, now=NOW, top_k=1, excluded=frozenset({pinned_mint})
        )
        without_exclusion = await load_mature_candidates(session, now=NOW, top_k=1)
        await session.close()
    assert [t.mint for t in with_exclusion] == [free_mint], (
        "excluded, the pinned mint's higher mcap never displaces the free one"
    )
    assert [t.mint for t in without_exclusion] == [pinned_mint], (
        "unexcluded, the bare LIMIT lets the higher-mcap (pinned) mint win the only slot"
    )
