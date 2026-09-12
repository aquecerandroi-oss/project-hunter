"""The meme kill switch (§7): escalation is arithmetic in SOL, the daily latch is
durable, and de-escalation is an owner's act that this module can refuse.

Three differences from ``hunter_risk.kill_switch``, each from the contract:

- the unit is **SOL**, not a percentage of equity — ``daily_loss_sol`` against
  ``MEME_DAILY_LOSS_CAP_SOL``;
- the daily block is **latched**: the caller stores it (``MemeKillSwitchInputs.
  daily_loss_latched``) and this module keeps it ``TRADING_DISABLED`` even when
  the mark recovers — a meme mark can swing 50 % in minutes, and unlatching on a
  swing would erase the owner's limit;
- ``resume`` refuses while the instant's own assessment still blocks — the same
  rule as SPOT.

Nothing here closes a position. ``auto_close_on_emergency`` is a decision of the
owner (§14.4) that the *executor* reads from its environment; the engine only
publishes whether entries are blocked and pendings cancelled.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import Field

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme.base import MemeModel
from hunter_risk_meme.inputs import MemeKillSwitchInputs, MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = [
    "RESTRICTION_ORDER",
    "MemeKillSwitchAssessment",
    "MemeResumeAuthorization",
    "MemeResumeRefused",
    "assess",
    "most_restrictive",
    "resume",
]

RESTRICTION_ORDER: Final[dict[KillSwitchState, int]] = {
    KillSwitchState.ACTIVE: 0,
    KillSwitchState.WARNING: 1,
    KillSwitchState.TRADING_DISABLED: 2,
    KillSwitchState.EMERGENCY: 3,
}
_ONE = Decimal(1)
_ZERO = Decimal(0)


def most_restrictive(*states: KillSwitchState) -> KillSwitchState:
    return max(states, key=lambda s: RESTRICTION_ORDER[s])


class MemeKillSwitchAssessment(MemeModel):
    automatic: KillSwitchState
    effective: KillSwitchState
    daily_loss_sol: Decimal
    drawdown_pct: Decimal
    latched: bool
    """True when the daily cap is (or was, durably) reached: the caller persists it."""
    trigger: str | None
    entry_size_multiplier: Decimal
    blocks_entries: bool
    cancel_pending: bool


def assess(
    wallet: MemeWalletState, limits: MemeLimits, inputs: MemeKillSwitchInputs
) -> MemeKillSwitchAssessment:
    loss = wallet.daily_loss_sol
    cap = limits.daily_loss_cap_sol
    warning_at = cap * limits.warning_daily_loss_fraction
    if inputs.daily_loss_latched or loss >= cap:
        automatic, trigger = KillSwitchState.TRADING_DISABLED, "daily_loss"
        latched = True
    elif loss >= warning_at:
        automatic, trigger, latched = KillSwitchState.WARNING, "daily_loss_warning", False
    else:
        automatic, trigger, latched = KillSwitchState.ACTIVE, None, False
    effective = most_restrictive(inputs.system, inputs.organization, inputs.wallet, automatic)
    if effective is KillSwitchState.ACTIVE:
        multiplier = _ONE
    elif effective is KillSwitchState.WARNING:
        multiplier = limits.warning_size_multiplier
    else:
        multiplier = _ZERO
    blocked = effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)
    return MemeKillSwitchAssessment(
        automatic=automatic,
        effective=effective,
        daily_loss_sol=loss,
        drawdown_pct=wallet.drawdown_pct,
        latched=latched,
        trigger=trigger,
        entry_size_multiplier=multiplier,
        blocks_entries=blocked,
        cancel_pending=effective is KillSwitchState.TRADING_DISABLED,
    )


class MemeResumeAuthorization(MemeModel):
    wallet_id: str = Field(min_length=1)
    actor_role: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MemeResumeRefused(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def resume(
    wallet: MemeWalletState,
    limits: MemeLimits,
    inputs: MemeKillSwitchInputs,
    authorization: MemeResumeAuthorization,
) -> MemeKillSwitchInputs:
    """Release the durable daily latch — OWNER only, and never while the instant's
    own assessment still blocks (a transition the next tick undoes is worse in the
    log than no transition)."""
    if authorization.actor_role != "OWNER":
        raise MemeResumeRefused("resume_requires_owner")
    if authorization.wallet_id != wallet.wallet_id:
        raise MemeResumeRefused("resume_wallet_mismatch")
    if not inputs.daily_loss_latched:
        raise MemeResumeRefused("nothing_latched")
    fresh = assess(wallet, limits, inputs.model_copy(update={"daily_loss_latched": False}))
    if fresh.automatic is KillSwitchState.TRADING_DISABLED:
        raise MemeResumeRefused("still_blocked_by_daily_loss")
    return inputs.model_copy(update={"daily_loss_latched": False})
