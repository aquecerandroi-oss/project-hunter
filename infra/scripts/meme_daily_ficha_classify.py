"""The automatic loss class (T4.92) — pure, no database, no clock.

Everton's ask: every real trade gets a sheet with its metrics and motives
*without depending on anyone remembering*, so losses are classified and the
biggest leak shows up by itself. A winning position (``pnl_sol >= 0``) has no
loss class — ``None``, rendered as "ganho".

**Order, documented, first match wins** (a losing position can match more
than one rule; whichever is checked first is the class that sticks):

1. ``comprou_no_topo`` — the position's peak (``high_water_sol``) never rose
   above the cost: the entry itself was the local top.
2. ``golpe_do_criador`` — the exit itself says ``creator_dump``, **or** the
   chain shows ten or more distinct sellers landing in the same slot while
   the position was open (a coordinated dump, not organic selling).
3. ``recompra`` — the same mint was re-entered within 300 s of a previous
   exit of *any* operator (T4.78's own pause window; KB-0149 §3.18 measured
   0/19 recompras winning in papel).
4. ``custo`` — the loss is smaller in magnitude than the round-trip cost
   (fees + network − any rent refund): the market roughly broke even and
   costs alone turned it red.
5. ``saida_normal`` — none of the above: an ordinary market loss.

A rule whose input is unknown (``None``) is skipped, never guessed —
"never invent a number" applies to classification too: a class this
function cannot prove is not assigned, and the position falls through to
the next rule instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meme_daily_ficha_types import RealPosition

__all__ = ["LOSS_CLASSES", "LossClassInputs", "classify_loss", "loss_class"]

LOSS_CLASSES: tuple[str, ...] = (
    "comprou_no_topo",
    "golpe_do_criador",
    "recompra",
    "custo",
    "saida_normal",
)

_CREATOR_DUMP_SELLERS_THRESHOLD = 10
_RECOMPRA_WINDOW = timedelta(seconds=300)


@dataclass(frozen=True, slots=True)
class LossClassInputs:
    """Everything a rule may look at — each field ``None`` when this ficha
    could not prove it, in which case the rule that needs it is skipped."""

    pnl_sol: Decimal
    cost_sol: Decimal
    high_water_sol: Decimal | None
    exit_reason: str | None
    distinct_sellers_one_slot: int | None
    """The largest count of distinct sellers seen in a single slot (``meme_trades``)
    while the position was open; ``None`` when the window could not be read."""
    since_prior_exit: timedelta | None
    """Elapsed time between this entry and the most recent prior exit of the
    same mint (any operator); ``None`` when there was no prior exit. Kept as a
    ``timedelta`` (Astra, T4.92 review, MEDIUM) rather than truncated to an
    ``int`` of seconds — ``int(300.9)`` used to read as 300 and wrongly pass a
    ``<= 300 s`` gate."""
    round_trip_cost_sol: Decimal | None
    """Buy + sell fees and network cost, minus any recorded ATA rent refund."""


def classify_loss(inputs: LossClassInputs) -> str | None:
    """``None`` for a winning position; otherwise one of :data:`LOSS_CLASSES`."""
    if inputs.pnl_sol >= 0:
        return None
    if inputs.high_water_sol is not None and inputs.high_water_sol <= inputs.cost_sol:
        return "comprou_no_topo"
    if inputs.exit_reason == "creator_dump":
        return "golpe_do_criador"
    if (
        inputs.distinct_sellers_one_slot is not None
        and inputs.distinct_sellers_one_slot >= _CREATOR_DUMP_SELLERS_THRESHOLD
    ):
        return "golpe_do_criador"
    if inputs.since_prior_exit is not None and inputs.since_prior_exit <= _RECOMPRA_WINDOW:
        return "recompra"
    if inputs.round_trip_cost_sol is not None and -inputs.pnl_sol < inputs.round_trip_cost_sol:
        return "custo"
    return "saida_normal"


def rose_after_buy(*, high_water_sol: Decimal | None, cost_sol: Decimal) -> bool | None:
    """ "Subiu depois da compra?" — ``None`` when the mark was never recorded."""
    if high_water_sol is None:
        return None
    return high_water_sol > cost_sol


def loss_class(position: RealPosition) -> str | None:
    """The automatic loss class of one ``RealPosition`` — ``None`` for a win
    or an open position. Shared by ``meme_daily_ficha_render`` (the human
    table) and ``meme_daily_ficha_frontmatter`` (the Dataview totals), so
    both always agree on the same class."""
    if position.pnl_sol is None:
        return None  # open position: not a closed loss, nothing to classify yet
    return classify_loss(
        LossClassInputs(
            pnl_sol=position.pnl_sol,
            cost_sol=position.cost_sol,
            high_water_sol=position.high_water_sol,
            exit_reason=position.exit_reason,
            distinct_sellers_one_slot=position.distinct_sellers_one_slot,
            since_prior_exit=position.since_prior_exit,
            round_trip_cost_sol=position.round_trip_cost_sol,
        )
    )
