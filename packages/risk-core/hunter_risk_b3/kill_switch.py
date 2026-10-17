"""Kill-switch resolution for the B3 robot (docs/RISK_ENGINE_B3.md §7.1).

Effective = the most restrictive of **system**, **organization** and **robot** by the
explicit order ``ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY``. The order is a table,
not ``max()`` over the ``StrEnum``: sorted as strings, ``"WARNING"`` is above
``"EMERGENCY"`` and the obvious spelling would let entries through during an emergency.

What each state does is a pure policy (:func:`kill_policy`); persisting a transition,
cancelling orders and running the bracket are the service's job. ``auto_close_on_emergency``
is fixed behaviour of this robot (§7.1, declared difference §13 item 4), not a profile key.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from hunter_risk_b3.base import B3Model
from hunter_risk_b3.context import KillSwitchB3
from hunter_risk_b3.enums import KillSwitchState
from hunter_risk_b3.limits import RiskLimitsB3

__all__ = [
    "RESTRICTION_ORDER",
    "KillPolicy",
    "automatic_state",
    "blocks_entries",
    "effective_state",
    "halve_for_warning",
    "kill_policy",
    "most_restrictive",
]

RESTRICTION_ORDER: Final[dict[KillSwitchState, int]] = {
    KillSwitchState.ACTIVE: 0,
    KillSwitchState.WARNING: 1,
    KillSwitchState.TRADING_DISABLED: 2,
    KillSwitchState.EMERGENCY: 3,
}


def most_restrictive(*states: KillSwitchState) -> KillSwitchState:
    return max(states, key=lambda state: RESTRICTION_ORDER[state])


def effective_state(kill_switch: KillSwitchB3) -> KillSwitchState:
    """The persisted scopes only — what check 1 reads (§8.2)."""
    return most_restrictive(kill_switch.system, kill_switch.organization, kill_switch.robot)


def blocks_entries(state: KillSwitchState) -> bool:
    return RESTRICTION_ORDER[state] >= RESTRICTION_ORDER[KillSwitchState.TRADING_DISABLED]


def automatic_state(loss_brl: Decimal, limits: RiskLimitsB3) -> KillSwitchState:
    """§7.1: the day's loss alone. ``TRADING_DISABLED`` at the limit (check 14 refuses and
    emits ``daily_loss_limit``); ``WARNING`` from ``warning_fraction × limit`` (automatic
    return when below)."""
    if loss_brl >= limits.daily_loss_limit_brl:
        return KillSwitchState.TRADING_DISABLED
    if loss_brl >= limits.warning_fraction * limits.daily_loss_limit_brl:
        return KillSwitchState.WARNING
    return KillSwitchState.ACTIVE


def halve_for_warning(n: int) -> int:
    """``floor(n × 0,5)`` — 1 becomes 0, never 1 (§8.3)."""
    return n // 2


class KillPolicy(B3Model):
    state: KillSwitchState
    entries_allowed: bool
    size_halved: bool
    cancel_entry_orders: bool
    flatten_positions: bool
    """Only ``EMERGENCY``, and only through the bracket (§5); foreign positions untouched."""


def kill_policy(state: KillSwitchState) -> KillPolicy:
    blocked = blocks_entries(state)
    return KillPolicy(
        state=state,
        entries_allowed=not blocked,
        size_halved=state is KillSwitchState.WARNING,
        cancel_entry_orders=blocked,
        flatten_positions=state is KillSwitchState.EMERGENCY,
    )
