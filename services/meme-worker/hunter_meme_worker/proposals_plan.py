"""``suggested.manual_plan`` (T4.19) — the plan the operator executes by hand,
written at proposal time for every ``operator`` proposal (Everton, 12/09/2026:
"coloca aí qual entra, quanto comprar e na mesma hora qual horário vender").

Every number is read from the rule set's own ``params`` — never typed into
the text — and every hour is Brasília's: the proposal's expiry
(``proposed_at + ttl_s``: until when to buy) and the hold's end
(``proposed_at + max_hold_s``: until when to sell), then the exits that sell
earlier in the order the operator watches them — the target, the trailing
stop (with its arming multiple when the set has one), the loss floor, the
creator dumping (always on: ``ExitRules.exit_on_creator_dump``) and the
support line breaking (only for a set that watches the line). Pure: no clock,
no session.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from hunter_meme_worker.lab_models import RuleSetSpec

__all__ = ["manual_plan", "pt_number", "ticker_of"]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
HALF = Decimal(50)
_MULTIPLE_WORDS: dict[Decimal, str] = {
    Decimal(2): "dobrar",
    Decimal(3): "triplicar",
    Decimal(4): "quadruplicar",
}
"""The multiples Portuguese has a verb for; any other reads "chegar a N×"."""


def pt_number(value: Decimal) -> str:
    """``0.05`` → ``0,05``; ``3`` → ``3``; ``1.50`` → ``1,5`` — plain digits, decimal comma."""
    return format(value.normalize(), "f").replace(".", ",")


def ticker_of(symbol: str | None, mint: str) -> str:
    """The token's ticker, or the mint abbreviated when the identity never came."""
    return symbol if symbol else f"{mint[:6]}…"


def _hold(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds % 60 == 0 else f"{seconds} s"


def _target(multiple: Decimal) -> str:
    word = _MULTIPLE_WORDS.get(multiple)
    return f"se {word} ({pt_number(multiple)}×)" if word else f"se chegar a {pt_number(multiple)}×"


def _trailing(pct: Decimal, arm: Decimal | None) -> str:
    """The trailing stop is an exit the engine takes (``exits.py``): a hand
    that does not know it holds through the 2× → 1,3× retreat the loop sells."""
    clause = f"se recuar {pt_number(pct)} % do topo"
    return clause if arm is None else f"{clause} depois de {pt_number(arm)}×"


def _loss(pct: Decimal) -> str:
    return "se cair pela metade (−50 %)" if pct == HALF else f"se cair {pt_number(pct)} %"


def manual_plan(spec: RuleSetSpec, *, ticker: str, proposed_at: datetime, ttl_s: int) -> str:
    """The sentence the desk shows under an ``operator`` proposal."""
    buy_until = (proposed_at + timedelta(seconds=ttl_s)).astimezone(SAO_PAULO)
    sell_until = (proposed_at + timedelta(seconds=spec.max_hold_s)).astimezone(SAO_PAULO)
    exits = [
        _target(spec.target_x),
        _trailing(spec.trailing_pct, spec.trailing_arm_x),
        _loss(spec.max_loss_pct),
        "se o dev vender",
    ]
    if spec.exit_on_line_break:
        exits.append("se a linha de suporte quebrar")
    return (
        f"Comprar {pt_number(spec.size_sol)} SOL de {ticker} até {buy_until:%H:%M:%S} "
        f"(proposta expira). Vender até {sell_until:%H:%M} ({_hold(spec.max_hold_s)}) — "
        f"antes disso {', '.join(exits[:-1])}, ou {exits[-1]}."
    )
