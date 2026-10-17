"""The copy lane's bet-side database access (H-037), as ``hunter_worker``: closing a copy with the Lab's
own ``close_bet_row`` and proving it landed, late facts on a copy's ``entry.copy`` / ``exit.copy`` block,
and the restart read of the copies still open. The funnel (proposals) is ``copy_repo_funnel.py``; the
coverage holes and T0 are ``copy_repo_gaps.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_meme_worker.lab_models import MARK_CURVE, BetState, EffectiveParams, decimal_of
from hunter_meme_worker.lab_repo_bets import close_bet_row

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.lab_models import BetExit

__all__ = [
    "RecoveredCopy",
    "close_copy_bet",
    "load_open_copies",
    "set_copy_fact",
]

_LANDED = text(
    "SELECT 1 FROM meme_paper_bets WHERE id = CAST(:id AS uuid) AND status = 'closed' "
    "  AND exit -> 'copy' -> 'ts' ->> 'persisted_at' = :stamp"
)
_OPEN_COPIES = text(
    "SELECT b.id, b.proposal_id, b.rule_set_id, b.mint, b.entry_at, b.entry, b.initial_risk_sol, "
    "       b.params, b.high_water_x, b.mark_sol, b.mark_at, b.mark_source, t.mayhem_enabled "
    "FROM meme_paper_bets b LEFT JOIN meme_tokens t ON t.mint = b.mint "
    "WHERE b.rule_set_id = CAST(:rule_set_id AS uuid) AND b.status = 'open' ORDER BY b.entry_at"
)
"""Its own read, not ``lab_repo_bets.load_open_bets``: the Lab is about to stop reading copy rows
(task I), and recovery must keep working when it does."""
_SET_ENTRY_FACT = text(
    "UPDATE meme_paper_bets SET entry = jsonb_set(entry, CAST(CAST(:path AS text) AS text[]), "
    "  CAST(:value AS jsonb), true) WHERE id = :id"
)
_SET_EXIT_FACT = text(
    "UPDATE meme_paper_bets SET exit = jsonb_set(exit, CAST(CAST(:path AS text) AS text[]), "
    "  CAST(:value AS jsonb), true) WHERE id = :id AND exit IS NOT NULL"
)


async def set_copy_fact(
    session: AsyncSession, bet_id: str, *, where: str, name: str, value: Any
) -> bool:
    """Late facts about a copy (the confirmation delay, an invalid reason) on its ``entry.copy`` or
    ``exit.copy`` block — a value the lane learned after the row was written. ``False`` when no row took
    it (the close has not landed, the bet is not there): the caller must not treat that as done."""
    statement = _SET_ENTRY_FACT if where == "entry" else _SET_EXIT_FACT
    result = await session.execute(
        statement, {"id": bet_id, "path": "{copy," + name + "}", "value": json.dumps(value)}
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]  # a zero-row update is NOT a success


async def close_copy_bet(
    session: AsyncSession, bet_id: str, closed: BetExit, *, mark_source: str | None, stamp: str
) -> bool:
    """The Lab's ``close_bet_row`` — then proof that **our** close is the one on the row. Another
    writer (the Lab's tick, an operator ``sell_now``) may have closed it first; ``UPDATE ... WHERE
    status = 'open'`` then touches nothing and the caller must not count a sale that is not ours."""
    await close_bet_row(session, bet_id, closed, mark_source=mark_source)
    landed = await session.execute(_LANDED, {"id": bet_id, "stamp": stamp})
    return landed.first() is not None


@dataclass(frozen=True, slots=True)
class RecoveredCopy:
    state: BetState
    leader: str
    stratum: str
    peak_atoms: int
    priced_slot: int
    unconfirmed_signature: str | None
    """Set when the copy was opened on an unconfirmed signal that never got its confirmation."""
    leader_observed_at: datetime
    leader_token_delta: int
    leader_slot: int


async def load_open_copies(session: AsyncSession, spec: CopySpec) -> list[RecoveredCopy]:
    """The copies still open in the database, rebuilt for the book and the executor."""
    out: list[RecoveredCopy] = []
    for r in (await session.execute(_OPEN_COPIES, {"rule_set_id": spec.id})).mappings():
        entry = r["entry"]
        copy = entry["copy"]
        leader = copy["leader"]
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
            exit_intent=None,
            fee_pct=decimal_of(entry["fee_pct"]),
            priority_fee_sol=decimal_of(entry["priority_fee_sol"]),
            curve_cost_sol=decimal_of(entry["curve_cost_sol"]),
            mark_source=str(r["mark_source"] or MARK_CURVE),
            is_mayhem=r["mayhem_enabled"],
        )
        out.append(
            RecoveredCopy(
                state=state,
                leader=str(leader["wallet"]),
                stratum=str(leader["stratum"]),
                peak_atoms=int(leader["position_after_atoms"]),
                priced_slot=int(copy.get("priced_slot") or 0),
                unconfirmed_signature=(
                    str(leader["signature"])
                    if leader.get("confirmed_at_decision") is False
                    and copy.get("confirmation_delay_ms") is None
                    and copy.get("invalid_reason") is None
                    and not copy.get("unverified")
                    else None
                ),
                leader_observed_at=datetime.fromisoformat(str(leader["observed_at"])),
                leader_token_delta=int(leader["token_delta_atoms"]),
                leader_slot=int(leader["slot"]),
            )
        )
    return out
