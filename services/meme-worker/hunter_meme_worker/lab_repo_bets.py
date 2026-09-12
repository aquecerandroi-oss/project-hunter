"""The bet side of the Lab repository - snapshots, the derived wallet, fills,
marks and closes - as ``hunter_worker``, never as owner (``lab_repo.py``'s rule).

The wallet of a rule set is **never stored**: :func:`wallet_state` derives
``wallet_max_sol + sum(closed pnl) - sum(open stake)`` from ``meme_paper_bets``
on every call, so a restart is not a reset and no counter in memory can drift
from the ledger.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_meme_worker.lab_models import (
    MARK_CURVE,
    BetEntry,
    BetExit,
    BetState,
    EffectiveParams,
    RuleSetSpec,
    Snapshot,
    WalletState,
    decimal_of,
)
from hunter_meme_worker.lab_rows import ApprovedProposal, OpenBet, snapshot_from_row
from hunter_meme_worker.lab_values import INDETERMINATE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "close_bet_row",
    "count_indeterminate",
    "first_snapshot_after",
    "load_open_bets",
    "mark_filled",
    "mark_unfilled",
    "snapshots_after",
    "update_mark",
    "wallet_state",
]


_SNAPSHOT_COLUMNS = (
    "observed_at, mint, source, virtual_sol_reserves, virtual_token_reserves, "
    "real_sol_reserves, real_token_reserves, total_supply, complete, mcap_sol"
)
_FIRST_SNAPSHOT_AFTER = text(
    f"SELECT {_SNAPSHOT_COLUMNS} FROM meme_curve_snapshots "  # noqa: S608
    "WHERE mint = :mint AND observed_at > :after ORDER BY observed_at, source LIMIT 1"
)
_SNAPSHOTS_AFTER = text(
    f"SELECT {_SNAPSHOT_COLUMNS} FROM meme_curve_snapshots "  # noqa: S608
    "WHERE mint = :mint AND observed_at > :after ORDER BY observed_at, source LIMIT :limit"
)

_WALLET = text(
    "SELECT coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed' "
    "                AND outcome_quality = 'measured'), 0) AS realized_total, "
    "       coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed' "
    "                AND outcome_quality = 'measured' "
    "                AND exit_at >= :day_start AND exit_at < :day_end), 0) AS realized_today, "
    "       coalesce(sum(initial_risk_sol) FILTER (WHERE status = 'open'), 0) AS open_exposure, "
    "       count(*) FILTER (WHERE status = 'open' AND leg <> 'scale') AS open_positions "
    "FROM meme_paper_bets WHERE rule_set_id = :rule_set_id"
)
"""``open_positions`` counts the legs that take a slot of ``max_open_positions``
(``probe`` and ``single``): a ``scale`` leg rides on its probe's slot (T4.10 —
the brief's ceiling is "máximo 5 sondas abertas"). Exposure counts every leg.
Realized sums count **measured** closes only (T4.16, ``0030``): on 12/09 five
``rug_no_snapshot`` artefacts summed −0,25 SOL, past the 0,20 daily cap — the
instrument, not the market, would have latched the Lab shut."""
_INDETERMINATE = text(
    "SELECT count(*) FROM meme_paper_bets WHERE outcome_quality = 'indeterminate'"
)
_EXPOSURE = text(
    "SELECT mint, sum(initial_risk_sol) AS exposure FROM meme_paper_bets "
    "WHERE rule_set_id = :rule_set_id AND status = 'open' GROUP BY mint"
)

_INSERT_BET = text(
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, status, entry_at, "
    "  entry, initial_risk_sol, params, mark_sol, mark_at, mark_source, high_water_x, "
    "  sol_usd_at_entry, leg, parent_bet_id) "
    "VALUES (:id, :proposal_id, :rule_set_id, :mint, 'paper', 'open', :entry_at, "
    "  CAST(:entry AS jsonb), :initial_risk_sol, CAST(:params AS jsonb), :mark_sol, :entry_at, "
    "  'curve', :high_water_x, :sol_usd_at_entry, :leg, CAST(:parent_bet_id AS uuid))"
)
"""The first mark is the fill's own snapshot — a curve mark by construction."""
_FILL_PROPOSAL = text(
    "UPDATE meme_proposals SET status = 'filled', bet_id = :bet_id "
    "WHERE id = :id AND status = 'approved'"
)
_UNFILL_PROPOSAL = text(
    "UPDATE meme_proposals SET status = 'unfilled', refusal = :refusal "
    "WHERE id = :id AND status = 'approved'"
)

_OPEN_BETS = text(
    "SELECT b.id, b.proposal_id, b.rule_set_id, b.mint, b.entry_at, b.entry, b.initial_risk_sol, "
    "       b.params, b.high_water_x, b.mark_sol, b.mark_at, b.exit_intent, "
    "       b.leg, b.parent_bet_id, b.mark_source, b.mark_stale_s, "
    "       t.migrated_at, t.completed_at, t.total_supply, t.creator, "
    "       (SELECT f.creator_sold FROM meme_features_1m f WHERE f.mint = b.mint "
    "          AND f.creator_sold IS NOT NULL ORDER BY f.end_time DESC LIMIT 1) AS creator_sold "
    "FROM meme_paper_bets b LEFT JOIN meme_tokens t ON t.mint = b.mint "
    "WHERE b.status = 'open' ORDER BY b.entry_at"
)
_UPDATE_MARK = text(
    "UPDATE meme_paper_bets SET mark_sol = :mark_sol, mark_at = :mark_at, "
    "  high_water_x = :high_water_x, exit_intent = CAST(:exit_intent AS jsonb), "
    "  mark_source = :mark_source, mark_stale_s = :mark_stale_s "
    "WHERE id = :id AND status = 'open'"
)
_CLOSE_BET = text(
    "UPDATE meme_paper_bets SET status = 'closed', exit_at = :exit_at, exit = CAST(:exit AS jsonb), "
    "  pnl_sol = :pnl_sol, r_multiple = :r_multiple, sol_usd_at_exit = :sol_usd_at_exit, "
    "  mark_sol = :mark_sol, mark_at = :exit_at, mark_stale_s = :mark_stale_s, "
    "  mark_source = coalesce(:mark_source, mark_source), "
    "  exit_intent = coalesce(CAST(:exit_intent AS jsonb), exit_intent), "
    "  outcome_quality = :outcome_quality, outcome_quality_reason = :outcome_quality_reason, "
    "  outcome_quality_at = :outcome_quality_at "
    "WHERE id = :id AND status = 'open'"
)
"""``outcome_quality_at`` is bound on its own (the close's instant, or ``NULL``
for a measured close): a ``CASE … THEN :exit_at END`` would make asyncpg
deduce ``text`` for the parameter it shares with ``exit_at``. ``mark_stale_s``
is ``NULL`` on every ordinary close (staleness of an open position is
meaningless once it is shut) **except** the T4.16b rescue: a pending exit
priced by one point read straight from the chain carries the honest age of
that read, never a fabricated zero."""


async def first_snapshot_after(
    session: AsyncSession, *, mint: str, after: datetime
) -> Snapshot | None:
    row = (
        (await session.execute(_FIRST_SNAPSHOT_AFTER, {"mint": mint, "after": after}))
        .mappings()
        .first()
    )
    return None if row is None else snapshot_from_row(row)


async def snapshots_after(
    session: AsyncSession, *, mint: str, after: datetime, limit: int = 500
) -> list[Snapshot]:
    rows = (
        await session.execute(_SNAPSHOTS_AFTER, {"mint": mint, "after": after, "limit": limit})
    ).mappings()
    return [snapshot_from_row(r) for r in rows]


async def wallet_state(
    session: AsyncSession, spec: RuleSetSpec, *, day_start: datetime, day_end: datetime
) -> WalletState:
    """``wallet_max_sol + Σ closed pnl − Σ open stake`` — from the rows, every time."""
    params = {"rule_set_id": spec.id, "day_start": day_start, "day_end": day_end}
    totals = (await session.execute(_WALLET, params)).mappings().one()
    exposure = {
        str(r["mint"]): Decimal(r["exposure"])
        for r in (await session.execute(_EXPOSURE, {"rule_set_id": spec.id})).mappings()
    }
    return WalletState(
        balance_sol=spec.wallet_max_sol
        + Decimal(totals["realized_total"])
        - Decimal(totals["open_exposure"]),
        open_positions=int(totals["open_positions"]),
        realized_today_sol=Decimal(totals["realized_today"]),
        exposure_by_mint=exposure,
    )


async def mark_filled(session: AsyncSession, proposal: ApprovedProposal, entry: BetEntry) -> str:
    bet_id = str(uuid7())
    await session.execute(
        _INSERT_BET,
        {
            "id": bet_id,
            "proposal_id": proposal.id,
            "rule_set_id": proposal.rule_set_id,
            "mint": proposal.mint,
            "entry_at": entry.entry_at,
            "entry": json.dumps(entry.entry),
            "initial_risk_sol": entry.initial_risk_sol,
            "params": json.dumps(entry.params.as_json()),
            "mark_sol": entry.mark_sol,
            "high_water_x": entry.high_water_x,
            "sol_usd_at_entry": entry.sol_usd_at_entry,
            "leg": entry.leg,
            "parent_bet_id": entry.parent_bet_id,
        },
    )
    await session.execute(_FILL_PROPOSAL, {"id": proposal.id, "bet_id": bet_id})
    return bet_id


async def mark_unfilled(session: AsyncSession, proposal_id: str, refusal: str) -> None:
    await session.execute(_UNFILL_PROPOSAL, {"id": proposal_id, "refusal": refusal})


async def load_open_bets(session: AsyncSession) -> list[OpenBet]:
    out: list[OpenBet] = []
    for r in (await session.execute(_OPEN_BETS)).mappings():
        entry = r["entry"]
        state = BetState(
            id=str(r["id"]),
            proposal_id=str(r["proposal_id"]),
            rule_set_id=str(r["rule_set_id"]),
            mint=str(r["mint"]),
            entry_at=r["entry_at"],
            tokens=decimal_of(entry["tokens"]),
            sol_spent=decimal_of(entry["sol_spent"]),
            initial_risk_sol=r["initial_risk_sol"],
            params=EffectiveParams.from_json(r["params"]),
            high_water_x=r["high_water_x"],
            mark_sol=r["mark_sol"],
            mark_at=r["mark_at"],
            exit_intent=r["exit_intent"],
            fee_pct=decimal_of(entry["fee_pct"]),
            priority_fee_sol=decimal_of(entry["priority_fee_sol"]),
            leg=str(r["leg"]),
            parent_bet_id=None if r["parent_bet_id"] is None else str(r["parent_bet_id"]),
            mark_source=str(r["mark_source"] or MARK_CURVE),
            mark_stale_s=None if r["mark_stale_s"] is None else int(r["mark_stale_s"]),
        )
        out.append(
            OpenBet(
                state=state,
                migrated_at=r["migrated_at"],
                completed_at=r["completed_at"],
                creator_net_seller=r["creator_sold"],
                total_supply=r["total_supply"],
                creator=None if r["creator"] is None else str(r["creator"]),
            )
        )
    return out


async def update_mark(
    session: AsyncSession,
    bet_id: str,
    *,
    mark_sol: Decimal,
    mark_at: datetime,
    high_water_x: Decimal,
    exit_intent: dict[str, Any] | None,
    mark_source: str = MARK_CURVE,
    mark_stale_s: int | None = None,
) -> None:
    await session.execute(
        _UPDATE_MARK,
        {
            "id": bet_id,
            "mark_sol": mark_sol,
            "mark_at": mark_at,
            "high_water_x": high_water_x,
            "exit_intent": None if exit_intent is None else json.dumps(exit_intent),
            "mark_source": mark_source,
            "mark_stale_s": mark_stale_s,
        },
    )


async def close_bet_row(
    session: AsyncSession,
    bet_id: str,
    closed: BetExit,
    *,
    exit_intent: dict[str, Any] | None = None,
    mark_source: str | None = None,
    mark_stale_s: int | None = None,
) -> None:
    """Close the bet; the rule that fired stays on the row even when the trigger
    and the sale landed in the same tick and no mark was written between.
    ``mark_source`` names what priced the sale when it was not the curve;
    ``mark_stale_s`` is the honest age of that price — ``None`` on every
    ordinary close, a real number only for the T4.16b point-read rescue."""
    await session.execute(
        _CLOSE_BET,
        {
            "id": bet_id,
            "exit_intent": None if exit_intent is None else json.dumps(exit_intent),
            "exit_at": closed.exit_at,
            "exit": json.dumps(closed.exit),
            "pnl_sol": closed.pnl_sol,
            "r_multiple": closed.r_multiple,
            "sol_usd_at_exit": closed.sol_usd_at_exit,
            "mark_sol": Decimal(closed.exit.get("sol_received", "0")),
            "mark_source": mark_source,
            "mark_stale_s": mark_stale_s,
            "outcome_quality": closed.outcome_quality,
            "outcome_quality_reason": closed.outcome_quality_reason,
            "outcome_quality_at": (
                closed.exit_at if closed.outcome_quality == INDETERMINATE else None
            ),
        },
    )


async def count_indeterminate(session: AsyncSession) -> int:
    """Every bet closed without a photo to price it — the heartbeat's
    ``lab_bets_indeterminate_total``, from the rows, never from memory."""
    return int(await session.scalar(_INDETERMINATE) or 0)
