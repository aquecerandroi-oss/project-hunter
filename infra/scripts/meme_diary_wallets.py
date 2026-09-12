"""The diary's section 2b — the observed wallets' real fills of one day (T4.12).

Reads ``meme_wallet_trades`` joined with the position the fill belongs to, as
``hunter_app`` (``SELECT`` only), and turns each row into a
:class:`meme_diary_render.WalletTradeLine`. A buy carries what every active
rule set's gate said in the minute before it (``lab_context``), rendered as
``aceito`` or the refusals by name — never a verdict this script invented.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from meme_diary_render import WalletTradeLine
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["gather_wallets", "lab_verdicts_of"]

LAMPORTS_PER_SOL = Decimal(10**9)

_TRADES = text(
    "SELECT w.wallet, w.mint, w.side, w.venue, w.block_time, w.sol_lamports, w.fee_lamports, "
    "       w.token_amount, w.raw ->> 'reason' AS reason, w.lab_context, "
    "       p.status AS position_status, p.realized_pnl_sol, p.r_multiple "
    "FROM meme_wallet_trades w "
    "LEFT JOIN meme_wallet_positions p ON p.wallet = w.wallet AND p.mint = w.mint "
    "WHERE coalesce(w.block_time, w.received_at) >= :day_start "
    "  AND coalesce(w.block_time, w.received_at) < :day_end "
    "ORDER BY coalesce(w.block_time, w.received_at), w.slot, w.event_index"
)


def lab_verdicts_of(context: Any) -> dict[str, str]:
    """``{rule set label: 'aceito' | refusals joined | 'sem linha de features'}``."""
    if not isinstance(context, dict):
        return {}
    raw = cast(dict[str, Any], context)
    sets_any = raw.get("rule_sets")
    if not isinstance(sets_any, dict):
        return {}
    out: dict[str, str] = {}
    for label, verdict_any in cast(dict[str, Any], sets_any).items():
        verdict = cast(dict[str, Any], verdict_any) if isinstance(verdict_any, dict) else {}
        accepted = verdict.get("accepted")
        refusals_any = verdict.get("refusals")
        refusals = (
            [str(r) for r in cast(list[Any], refusals_any)]
            if isinstance(refusals_any, list)
            else []
        )
        if accepted is None:
            out[str(label)] = str(raw.get("reason") or "sem linha de features")
        elif accepted:
            out[str(label)] = "aceito"
        else:
            out[str(label)] = ", ".join(refusals) or "recusado"
    return out


def _sol_total(side: str, sol: Any, fee: Any) -> Decimal | None:
    if sol is None or fee is None or side not in ("buy", "sell"):
        return None
    lamports = int(sol) + int(fee) if side == "buy" else int(sol) - int(fee)
    return Decimal(lamports) / LAMPORTS_PER_SOL


async def gather_wallets(
    session: AsyncSession, *, day_start: datetime, day_end: datetime
) -> list[WalletTradeLine]:
    rows = (
        (await session.execute(_TRADES, {"day_start": day_start, "day_end": day_end}))
        .mappings()
        .all()
    )
    return [
        WalletTradeLine(
            wallet=str(r["wallet"]),
            mint=r["mint"],
            side=str(r["side"]),
            venue=r["venue"],
            block_time=r["block_time"],
            sol_total=_sol_total(str(r["side"]), r["sol_lamports"], r["fee_lamports"]),
            token_amount=None if r["token_amount"] is None else Decimal(r["token_amount"]),
            reason=r["reason"],
            lab_verdicts=lab_verdicts_of(r["lab_context"]) if r["side"] == "buy" else {},
            position_status=r["position_status"],
            realized_pnl_sol=None
            if r["realized_pnl_sol"] is None
            else Decimal(r["realized_pnl_sol"]),
            r_multiple=None if r["r_multiple"] is None else Decimal(r["r_multiple"]),
        )
        for r in rows
    ]
