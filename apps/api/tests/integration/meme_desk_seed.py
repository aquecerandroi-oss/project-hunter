"""Seed rows for ``test_meme_desk_repository_{a,b}.py`` (T4.7b) — inserted
straight into a database Alembic already migrated to ``head``
(``conftest.py``'s ``migrate_fresh_database``), never onto a frozen, literal
DDL copy: the four ``meme_lab`` tables and every column ``0022``-``0031`` added
to them are the real schema, so a later migration cannot leave this seed
inserting into columns or defaults that no longer match production.

**Rule set names are test-only and never ``meme_paper_v0``/``operator``**:
``0022``'s own seed (``ddl/meme_lab_views.py``) plants those names on every
database this suite migrates, and ``(name, version)`` is unique — reusing them
here would collide on ``INSERT``. ``repositories/meme_desk.py``'s
``get_operator_rule_set()`` looks up the *name* ``operator`` directly, so a
manual proposal in these tests is filed under the real migrated set (currently
``operator/2``, ``0029``), never a synthetic one: the seed deliberately leaves
that name alone.

The primary mint/reserves/creator values are T4.1's live capture
(``packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_list_raw.json``,
2026-09-12); every proposal/bet row is synthetic (there is no loop yet) and
labelled as such by this module's own docstring.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.domain.types import uuid7

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # 09:00 Brasília
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
CLERK_ID = "user_FAKE_desk_operator"

MINT_CURVE = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"  # T4.1 live capture
MINT_DONE = "Synthetic1CompletedNotMigratedxxxxxxxxxxxxx"  # synthetic, completed

RS_RESEARCH_NAME = "meme_desk_it_research"
RS_OPERATOR_NAME = "meme_desk_it_operator"
RS_RESEARCH = uuid.uuid4()
RS_OPERATOR = uuid.uuid4()
P_PROPOSED = uuid7()
P_APPROVED = uuid7()
P_FILLED_OPEN = uuid7()
P_FILLED_CLOSED = uuid7()
P_REJECTED = uuid7()
P_UNFILLED = uuid7()
B_OPEN = uuid7()
B_CLOSED = uuid7()

PARAMS_RESEARCH: dict[str, Any] = {
    "size_sol": "0.2",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
    "wallet_max_sol": "5",
    "max_sol_per_bet": "0.5",
    "daily_loss_cap_sol": "1",
}
PARAMS_OPERATOR: dict[str, Any] = {
    "wallet_max_sol": "3",
    "max_sol_per_bet": "0.5",
    "daily_loss_cap_sol": "1",
}
SUGGESTED: dict[str, Any] = {
    "size_sol": "0.2",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
}


def _j(value: object) -> str:
    return json.dumps(value)


async def seed(url: str) -> None:
    """The rows above, inserted as the container's owner role (which every
    ``0022``-``0031`` grant is a subtraction *from*, never a check on) — a
    fresh engine of its own so this seed never shares a loop with a test."""
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await _seed_tokens(connection)
            await _seed_curve_snapshots(connection)
            await _seed_rule_sets(connection)
            await _seed_proposals(connection)
            await _seed_bets(connection)
    finally:
        await engine.dispose()


async def _seed_tokens(connection: Any) -> None:
    await connection.execute(
        text(
            "INSERT INTO meme_tokens (mint, name, symbol, creator, created_at, completed_at, "
            "first_seen_source, first_seen_at, last_seen_at, updated_at) VALUES "
            "(:mint, :name, :symbol, :creator, :created_at, :completed_at, 'pumpportal_ws', "
            ":created_at, :created_at, :created_at)"
        ),
        [
            {
                "mint": MINT_CURVE,
                "name": "bum bum",
                "symbol": "bam bum",
                "creator": "s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
                "created_at": NOW - timedelta(minutes=30),
                "completed_at": None,
            },
            {
                "mint": MINT_DONE,
                "name": "Synthetic Completed",
                "symbol": "SYNC1",
                "creator": "SyntheticCreator1xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "created_at": NOW - timedelta(hours=3),
                "completed_at": NOW - timedelta(hours=1),
            },
        ],
    )


async def _seed_curve_snapshots(connection: Any) -> None:
    await connection.execute(
        text(
            "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
            "virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves, "
            "total_supply, complete) VALUES (:observed_at, :mint, :source, :observed_at, :vsr, :vtr, "
            ":rsr, :rtr, 1000000000, false)"
        ),
        [
            {
                "observed_at": NOW - timedelta(minutes=6),
                "mint": MINT_CURVE,
                "source": "pumpfun_rest",
                "vsr": Decimal("9.713447588"),
                "vtr": Decimal("1072520031.280431"),
                "rsr": Decimal("0.019167922"),
                "rtr": Decimal("792620031.280431"),
            },
            {
                "observed_at": NOW - timedelta(minutes=1),
                "mint": MINT_CURVE,
                "source": "solana_rpc",
                "vsr": Decimal("9.8"),
                "vtr": Decimal("1071000000"),
                "rsr": Decimal("0.12"),
                "rtr": Decimal("791100000"),
            },
        ],
    )


async def _seed_rule_sets(connection: Any) -> None:
    """Test-only names (module docstring); ``RS_OPERATOR`` is ``kind =
    'operator'`` but never named ``operator`` — the real migrated set of that
    name is what ``get_operator_rule_set()`` must find instead."""
    await connection.execute(
        text(
            "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status, "
            "created_at) VALUES (:id, :name, :version, :kind, CAST(:params AS jsonb), :code_ref, "
            ":exp_ref, 'active', :created_at)"
        ),
        [
            {
                "id": RS_RESEARCH,
                "name": RS_RESEARCH_NAME,
                "version": "1",
                "kind": "research_only",
                "params": _j(PARAMS_RESEARCH),
                "code_ref": "hunter_indicators.meme.rules",
                "exp_ref": "EXP-IT-DESK",
                "created_at": NOW - timedelta(days=1),
            },
            {
                "id": RS_OPERATOR,
                "name": RS_OPERATOR_NAME,
                "version": "1",
                "kind": "operator",
                "params": _j(PARAMS_OPERATOR),
                "code_ref": "hunter_api.services.meme_desk",
                "exp_ref": None,
                "created_at": NOW - timedelta(days=1) + timedelta(seconds=1),
            },
        ],
    )


async def _seed_proposals(connection: Any) -> None:
    proposals = [
        (P_PROPOSED, RS_OPERATOR, "rules", "proposed", -30, None, None, None, None),
        (P_APPROVED, RS_OPERATOR, "rules", "approved", -60, SUGGESTED, CLERK_ID, None, None),
        (P_FILLED_OPEN, RS_RESEARCH, "rules", "approved", -600, SUGGESTED, "rules", None, None),
        (
            P_FILLED_CLOSED,
            RS_RESEARCH,
            "rules",
            "approved",
            -7200,
            SUGGESTED,
            "rules",
            None,
            None,
        ),
        (P_REJECTED, RS_OPERATOR, "rules", "rejected", -300, {"note": "nao"}, CLERK_ID, None, None),
        (
            P_UNFILLED,
            RS_RESEARCH,
            "rules",
            "unfilled",
            -180,
            SUGGESTED,
            "rules",
            None,
            "daily_loss_cap",
        ),
    ]
    await connection.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "expires_at, features_end_time, quote, reasons, suggested, decision, decided_by, "
            "decided_at, bet_id, refusal) VALUES (:id, :mint, :rule_set_id, :origin, :status, "
            ":proposed_at, :expires_at, :features_end_time, CAST(:quote AS jsonb), "
            "CAST(:reasons AS jsonb), CAST(:suggested AS jsonb), CAST(:decision AS jsonb), "
            ":decided_by, :decided_at, :bet_id, :refusal)"
        ),
        [
            {
                "id": pid,
                "mint": MINT_CURVE,
                "rule_set_id": rs,
                "origin": origin,
                "status": status,
                "proposed_at": NOW + timedelta(seconds=offset),
                "expires_at": NOW + timedelta(seconds=offset + 120),
                "features_end_time": NOW + timedelta(seconds=offset - 60),
                "quote": _j(
                    {
                        "observed_at": (NOW + timedelta(seconds=offset - 10)).isoformat(),
                        "source": "solana_rpc",
                        "mcap_sol": "9.14",
                        "size_sol": "0.2",
                        "fee_sol": "0.0035",
                        "cost_sol": "0.2",
                    }
                ),
                "reasons": _j(["progress_gate", "age_gate"]),
                "suggested": _j(SUGGESTED),
                "decision": None if decision is None else _j(decision),
                "decided_by": decided_by,
                "decided_at": None if decided_by is None else NOW + timedelta(seconds=offset + 5),
                "bet_id": bet_id,
                "refusal": refusal,
            }
            for pid, rs, origin, status, offset, decision, decided_by, bet_id, refusal in proposals
        ],
    )


async def _seed_bets(connection: Any) -> None:
    """``mark_source`` is set explicitly on every row that carries a
    ``mark_sol``: ``0029``'s ``ck_meme_paper_bets_a_mark_names_its_source``
    (``(mark_sol IS NULL) = (mark_source IS NULL)``) means a mark with no
    source is now a constraint violation, not a value the desk reads as
    ``None`` — the column the frozen-DDL version of this suite never had."""
    await connection.execute(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, status, entry_at, "
            "entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, mark_sol, mark_at, "
            "mark_source, high_water_x, sol_usd_at_entry, sol_usd_at_exit) VALUES (:id, :proposal_id, "
            ":rule_set_id, :mint, 'paper', :status, :entry_at, CAST(:entry AS jsonb), 0.2, "
            "CAST(:params AS jsonb), :exit_at, CAST(:exit AS jsonb), :pnl_sol, :r_multiple, "
            ":mark_sol, :mark_at, :mark_source, :high_water_x, :sol_usd_at_entry, :sol_usd_at_exit)"
        ),
        [
            {
                "id": B_OPEN,
                "proposal_id": P_FILLED_OPEN,
                "rule_set_id": RS_RESEARCH,
                "mint": MINT_CURVE,
                "status": "open",
                "entry_at": NOW - timedelta(minutes=9),
                "entry": _j(
                    {
                        "sol_spent": "0.2",
                        "fee_sol": "0.0035",
                        "tokens": "21000000",
                        "sol_usd_source": "coingecko",
                    }
                ),
                "params": _j(SUGGESTED),
                "exit_at": None,
                "exit": None,
                "pnl_sol": None,
                "r_multiple": None,
                "mark_sol": Decimal("0.25"),
                "mark_at": NOW - timedelta(minutes=1),
                "mark_source": "curve",
                "high_water_x": Decimal("1.3"),
                "sol_usd_at_entry": Decimal("180"),
                "sol_usd_at_exit": None,
            },
            {
                "id": B_CLOSED,
                "proposal_id": P_FILLED_CLOSED,
                "rule_set_id": RS_RESEARCH,
                "mint": MINT_CURVE,
                "status": "closed",
                "entry_at": NOW - timedelta(hours=2),
                "entry": _j({"sol_spent": "0.2", "fee_sol": "0.0035", "tokens": "20000000"}),
                "params": _j(SUGGESTED),
                "exit_at": NOW - timedelta(hours=1),
                "exit": _j(
                    {
                        "reason": "target",
                        "sol_received": "0.38",
                        "fee_sol": "0.0066",
                        "sol_usd_source": "coingecko",
                    }
                ),
                "pnl_sol": Decimal("0.18"),
                "r_multiple": Decimal("0.9"),
                "mark_sol": Decimal("0.38"),
                "mark_at": NOW - timedelta(hours=1),
                "mark_source": "curve",
                "high_water_x": Decimal("2.0"),
                "sol_usd_at_entry": Decimal("179"),
                "sol_usd_at_exit": Decimal("181"),
            },
        ],
    )
    # The bets exist now: close the proposals -> bets -> proposals cycle the
    # real schema enforces (``fk_meme_proposals_bet_id_meme_paper_bets`` plus
    # ``a_fill_names_its_bet``), the way the loop itself fills a proposal.
    await connection.execute(
        text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
        [{"bet": B_OPEN, "id": P_FILLED_OPEN}, {"bet": B_CLOSED, "id": P_FILLED_CLOSED}],
    )
