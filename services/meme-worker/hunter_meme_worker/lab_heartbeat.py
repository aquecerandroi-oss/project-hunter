"""The ``lab_*`` fields of ``hb:meme:radar`` — split from
:mod:`hunter_meme_worker.lab` in T4.16 for the 350-line budget (that module
re-exports both names). Strings, like every heartbeat field of the repo; an
absent number is ``""``, never a ``0`` that reads as a measurement.

T4.16 adds what the brief asks to be **measured, not assumed**:
``lab_decision_to_fill_s_p50`` / ``_p95`` over the fills this process made
(``entry.decision_to_fill_s`` of each), ``lab_bets_indeterminate_total``
from the rows, and the 15-second gate's own counters.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_meme_worker.lab import LabContext, LabState

logger = get_logger(__name__)

HEARTBEAT_PREFIX = "lab_"

__all__ = ["HEARTBEAT_PREFIX", "heartbeat_fields", "percentile", "write_lab_heartbeat"]


def percentile(values: Sequence[int], fraction: float) -> int | None:
    """The nearest-rank percentile of ``values`` (``fraction`` in ``(0, 1]``);
    ``None`` on an empty sample — an unmeasured latency is not zero."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def heartbeat_fields(state: LabState, *, enabled: bool = True) -> dict[str, str]:
    """The ``lab_*`` fields — strings, like every heartbeat field of the repo."""
    quote = state.sol_usd
    delays = list(state.fill_delays)
    p50, p95 = percentile(delays, 0.50), percentile(delays, 0.95)
    fields: dict[str, Any] = {
        "enabled": "true" if enabled else "false",
        "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else "",
        "tick_minute": state.last_tick_minute.isoformat() if state.last_tick_minute else "",
        "rule_sets_active": str(state.rule_sets_active),
        "rows_evaluated": str(state.rows_evaluated),
        "gate_refusals": json.dumps(state.refusals, sort_keys=True),
        "proposals_last_tick": str(state.proposals_last_tick),
        "proposals_total": str(state.proposals_total),
        "fills_total": str(state.fills_total),
        "unfilled_total": str(state.unfilled_total),
        "closes_total": str(state.closes_total),
        "bets_open": str(state.bets_open),
        "sol_usd": "" if quote is None else str(quote.price_usd),
        "sol_usd_observed_at": "" if quote is None else quote.observed_at.isoformat(),
        "sol_usd_source": "" if quote is None else quote.source,
        "sol_usd_error": state.sol_usd_error or "",
        # T4.16: the 15-second gate, the measured decision-to-fill, the indeterminate closes.
        "fast_last_as_of": state.last_fast_as_of.isoformat() if state.last_fast_as_of else "",
        "fast_rows_evaluated": str(state.fast_rows_evaluated),
        "fast_proposals_total": str(state.fast_proposals_total),
        "decision_to_fill_s_p50": "" if p50 is None else str(p50),
        "decision_to_fill_s_p95": "" if p95 is None else str(p95),
        "decision_to_fill_n": str(len(delays)),
        "bets_indeterminate_total": (
            "" if state.bets_indeterminate_total is None else str(state.bets_indeterminate_total)
        ),
    }
    return {HEARTBEAT_PREFIX + key: str(value) for key, value in fields.items()}


async def write_lab_heartbeat(ctx: LabContext, *, enabled: bool = True) -> None:
    if ctx.heartbeat is None:
        return
    try:
        await ctx.heartbeat(heartbeat_fields(ctx.state, enabled=enabled))
    except Exception:  # a heartbeat that cannot be written must not stop the Lab
        logger.warning("meme_lab_heartbeat_write_failed")
