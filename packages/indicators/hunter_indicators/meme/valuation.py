"""The honest valuation of a curve position, and of a whole paper wallet.

``docs/RISK_ENGINE_MEME.md`` §6 and §10.6 make this the contract, not a
convenience: **the mark is what a full sell would net now, fees included** —
never the marginal price times the quantity, which is "o número que faz um paper
trade parecer lucrativo e um resgate real sair 30 % abaixo".

:func:`equity_sol` returns the balance plus the marks it could compute **and the
names of the positions it could not**. A wallet that silently valued an
unpriceable position at zero, or that quietly skipped it, would publish an equity
that is neither — the caller decides what to do with a position whose reserves
were not supplied, and it has to know there is one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_sell
from hunter_indicators.meme.models import PaperPosition

__all__ = ["Equity", "equity_sol", "position_mark_sol"]


def position_mark_sol(
    position: PaperPosition, reserves: CurveReserves, fee_pct: Decimal
) -> Decimal:
    """SOL a full sell of ``position`` would net against ``reserves``, fees included."""
    return quote_sell(reserves, position.tokens, fee_pct).net_sol


@dataclass(frozen=True, slots=True)
class Equity:
    """Balance plus the marks that exist, plus the mints whose reserves were missing."""

    total_sol: Decimal
    balance_sol: Decimal
    marked_sol: Decimal
    unpriced_mints: tuple[str, ...]


def equity_sol(
    balance_sol: Decimal,
    positions: Mapping[str, PaperPosition],
    reserves_by_mint: Mapping[str, CurveReserves],
    fee_pct: Decimal,
) -> Equity:
    """``equity = sol_balance + sum(mark(position))`` — the invariant of §10.6."""
    marked = Decimal(0)
    unpriced: list[str] = []
    with localcontext(CONTEXT):
        for mint, position in positions.items():
            reserves = reserves_by_mint.get(mint)
            if reserves is None:
                unpriced.append(mint)
                continue
            marked += position_mark_sol(position, reserves, fee_pct)
        return Equity(
            total_sol=balance_sol + marked,
            balance_sol=balance_sol,
            marked_sol=marked,
            unpriced_mints=tuple(unpriced),
        )
