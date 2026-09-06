"""The kill switch: escalation is arithmetic, de-escalation is an act.

The directive names three modes (NORMAL, AVISO, BLOQUEADO). They are not a new
enum: they map onto ``hunter_core.domain.enums.KillSwitchState``, which the
database, the API and the frontend already share -

===========  ===========================
Directive    ``KillSwitchState``
===========  ===========================
NORMAL       ``ACTIVE``
AVISO        ``WARNING``
BLOQUEADO    ``TRADING_DISABLED``
-            ``EMERGENCY`` (manual only)
===========  ===========================

Two rules this module exists to make impossible to break:

1. **The multiplier multiplies the final size** (``R-KS-1``). This module only
   *publishes* ``entry_size_multiplier``; :mod:`hunter_risk.sizing` applies it
   after every ceiling, which is what makes "half size in WARNING" true for
   every approved entry instead of true only when the risk ceiling happened to
   be the binding one.
2. **BLOQUEADO never expires.** :func:`assess` can only raise the state; the
   latch lives with the caller (a column), and the single way down is
   :func:`resume`, which demands an authorisation naming the portfolio, the
   state it was written for and a reason. There is no argument here that time
   can move.

The ordering is explicit and not ``max()`` over the ``StrEnum``: sorted by
value, ``"WARNING"`` is greater than ``"TRADING_DISABLED"`` and than
``"EMERGENCY"``, so the obvious spelling would let entries through during an
emergency.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Final

from pydantic import Field, field_validator

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.base import RiskModel
from hunter_risk.exposure import PortfolioState
from hunter_risk.limits import RiskLimits

RESTRICTION_ORDER: Final[dict[KillSwitchState, int]] = {
    KillSwitchState.ACTIVE: 0,
    KillSwitchState.WARNING: 1,
    KillSwitchState.TRADING_DISABLED: 2,
    KillSwitchState.EMERGENCY: 3,
}
"""Least to most restrictive - RISK_ENGINE.md §5."""

_ONE = Decimal(1)
_ZERO = Decimal(0)


def most_restrictive(*states: KillSwitchState) -> KillSwitchState:
    """The effective state of several scopes - the most restrictive one wins."""
    return max(states, key=lambda state: RESTRICTION_ORDER[state])


class KillSwitchInputs(RiskModel):
    """The three persisted scopes. Each is a latch the caller stores and passes in."""

    system: KillSwitchState = KillSwitchState.ACTIVE
    organization: KillSwitchState = KillSwitchState.ACTIVE
    portfolio: KillSwitchState = KillSwitchState.ACTIVE


class KillSwitchAssessment(RiskModel):
    """What the switch is, why, and what follows from it."""

    automatic: KillSwitchState
    """Derived from the day's loss and the drawdown alone."""
    effective: KillSwitchState
    """Most restrictive of the three scopes and the automatic assessment."""
    daily_loss_pct: Decimal
    drawdown_pct: Decimal
    trigger: str | None
    """``"daily_loss"``, ``"drawdown"``, ``"both"`` or ``None``."""
    entry_size_multiplier: Decimal
    """1 in ACTIVE, 0.5 in WARNING, 0 above - applied after every sizing ceiling."""
    blocks_entries: bool
    cancel_pending: bool
    """Directive §5: BLOQUEADO cancels pending entries. It never closes positions
    and never removes a protection - that is what :func:`hunter_risk.evaluate.
    evaluate_exit` guarantees on the other side."""


def assess(
    portfolio: PortfolioState, limits: RiskLimits, inputs: KillSwitchInputs
) -> KillSwitchAssessment:
    """The kill switch at this instant. Pure: same state and limits, same answer."""
    daily_loss = portfolio.daily_loss_pct
    drawdown = portfolio.drawdown_pct

    loss_blocked = daily_loss >= limits.kill_switch_blocked.daily_loss_pct
    dd_blocked = drawdown >= limits.kill_switch_blocked.drawdown_pct
    loss_warning = daily_loss >= limits.kill_switch_warning.daily_loss_pct
    dd_warning = drawdown >= limits.kill_switch_warning.drawdown_pct

    if loss_blocked or dd_blocked:
        automatic = KillSwitchState.TRADING_DISABLED
        by_loss, by_dd = loss_blocked, dd_blocked
    elif loss_warning or dd_warning:
        automatic = KillSwitchState.WARNING
        by_loss, by_dd = loss_warning, dd_warning
    else:
        automatic = KillSwitchState.ACTIVE
        by_loss = by_dd = False

    trigger = (
        "both" if by_loss and by_dd else "daily_loss" if by_loss else "drawdown" if by_dd else None
    )
    effective = most_restrictive(inputs.system, inputs.organization, inputs.portfolio, automatic)
    return KillSwitchAssessment(
        automatic=automatic,
        effective=effective,
        daily_loss_pct=daily_loss,
        drawdown_pct=drawdown,
        trigger=trigger,
        entry_size_multiplier=entry_size_multiplier(effective, limits),
        blocks_entries=blocks_entries(effective),
        cancel_pending=blocks_entries(effective),
    )


def entry_size_multiplier(state: KillSwitchState, limits: RiskLimits) -> Decimal:
    """The factor applied to the **final approved size** of a new entry."""
    if state is KillSwitchState.ACTIVE:
        return _ONE
    if state is KillSwitchState.WARNING:
        return limits.warning_size_multiplier
    return _ZERO


def blocks_entries(state: KillSwitchState) -> bool:
    """True from ``TRADING_DISABLED`` up. Exits are never affected by this."""
    return RESTRICTION_ORDER[state] >= RESTRICTION_ORDER[KillSwitchState.TRADING_DISABLED]


class ResumeAuthorization(RiskModel):
    """A human act, already authenticated by the caller.

    The core does not authenticate anybody; it refuses to move without an
    authorisation that names *this* portfolio and *this* current state, so a
    stale approval for another portfolio (or for a block that has since been
    raised to EMERGENCY) cannot be replayed into an unlock.
    """

    authorized_by: str = Field(min_length=1)
    portfolio_id: uuid.UUID
    from_state: KillSwitchState
    to_state: KillSwitchState
    reason: str = Field(min_length=1)

    @field_validator("authorized_by", "reason", mode="after")
    @classmethod
    def _not_blank(cls, value: str, info: object) -> str:
        if not value.strip():
            field = getattr(info, "field_name", "value")
            raise ValueError(f"{field} must name a person and a reason, not whitespace")
        return value


def resume(
    latched: KillSwitchState,
    authorization: ResumeAuthorization,
    assessment: KillSwitchAssessment,
    portfolio_id: uuid.UUID,
) -> KillSwitchState:
    """Clear (or lower) the portfolio latch. Returns the new latch, nothing else.

    It does **not** override the automatic assessment: if the day's loss or the
    drawdown still breach the blocking thresholds, the next :func:`assess` puts
    the portfolio straight back into ``TRADING_DISABLED``. That is deliberate -
    an unlock that also suspended the thresholds would be a silent exception to
    a limit Everton wrote, granted by whoever pressed the button.
    """
    if authorization.portfolio_id != portfolio_id:
        raise ValueError(
            f"authorisation is for portfolio {authorization.portfolio_id}, not {portfolio_id}"
        )
    if authorization.from_state is not latched:
        raise ValueError(
            f"authorisation was written for from_state {authorization.from_state}, but the "
            f"latch is {latched}: the state moved since it was granted"
        )
    if RESTRICTION_ORDER[authorization.to_state] >= RESTRICTION_ORDER[latched]:
        raise ValueError("resume may only de-escalate; raising the switch is not an authorisation")
    return authorization.to_state
