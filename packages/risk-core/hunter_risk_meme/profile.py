"""T4.67b — the **launch** admission profile (``docs/RISK_ENGINE_MEME.md``,
"Perfil de lançamento"; EXP-M18): the same engine, a coin that is one second old.

At t+1 s after the ``create`` none of the slow inputs exists — no
``/in-memory-coin`` snapshot, no holders read, no minute tape, no creator flow,
no 60 s of curve photos for the conviction ladder. The full profile would
refuse every launch by name (``unavailable`` rejects, §8), which is correct for
the desk and useless for a lane whose whole bet is the first second. This
profile does **not** loosen the doctrine's rule — an input that does not exist
still never turns into a zero — it declares, check by check, which ones the
lane does not run (:data:`LAUNCH_SKIPPED_CHECKS`, recorded as ``skipped`` with
the reason) and which run under a launch rule (:data:`LAUNCH_RELAXED_CHECKS`,
recorded with the rule in the message). Everything else — kill switch, wallet,
daily loss with the treasury inflow, program, identity, freshness, Mayhem, rug
history, duplicate, the global open cap, fees, participation, impact, the
available SOL, the exposure after — runs exactly as in §4.

What the profile adds: its own open cap (``launch_open_cap``, check 27, counts
only ``lane = launch`` positions and pending intents — the desk's positions
count against the global cap as always), the ticket as a ceiling
(``launch_ticket`` in the sizing, never above ``max_sol_per_trade``), the
launch's participation cap, the launch's maximum token age, and a floor that
follows the ticket (a 0,01 SOL ticket under a 0,02 SOL live floor would refuse
every launch; the ratio of fixed costs to the ticket is published in the
sizing for the audit, not hidden).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import Field

from hunter_risk_meme.base import MemeModel
from hunter_risk_meme.decision import MemeCheck, check
from hunter_risk_meme.inputs import MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = [
    "LAUNCH_LANE",
    "LAUNCH_MAX_OPEN_REACHED",
    "LAUNCH_RELAXED_CHECKS",
    "LAUNCH_SKIPPED_CHECKS",
    "MemeLaunchProfile",
    "launch_floor",
    "launch_open_cap_check",
]

LAUNCH_LANE: Final = "launch"
"""``OpenMemePosition.lane`` / ``PendingMemeIntent.lane`` of what this profile opened."""
LAUNCH_MAX_OPEN_REACHED: Final = "launch_max_open_reached"

LAUNCH_SKIPPED_CHECKS: Final[dict[str, str]] = {
    "creator_behaviour": (
        "no creator flow exists at t+1s; the on-demand ATA read (T4.45) is not made "
        "(latency on the critical path); the event exits sell on his first sell instead"
    ),
    "bundled_share": (
        "no /in-memory-coin snapshot exists at t+1s; the on-demand risk read (T4.45) is not made"
    ),
    "top10_share": "no holders read exists at t+1s (first sample lands +114s or later)",
    "conviction": (
        "the ladder (T4.61c) needs 60s of curve photos and a 15s features row; "
        "neither exists at t+1s"
    ),
}
"""Checks the launch profile records as ``skipped`` (state, reason) — never as
``passed``. The executor writes the same names into ``admission.launch.skipped``
next to the reads it did not make (risk snapshot, creator ATA, buyer ATA)."""

LAUNCH_RELAXED_CHECKS: Final[dict[str, str]] = {
    "state_freshness": (
        "a processed quote is admitted (the account bytes of the slot being built; "
        "the fill is still decoded from the confirmed transaction, never from the quote)"
    ),
    "token_age": (
        "no minimum (the coin is seconds old by construction); the maximum is the "
        "launch's own (max_token_age_s), measured from the proposal's create stamp"
    ),
    "curve_progress": (
        "no minimum (a virgin curve is 0 %); complete, above-window and a missing "
        "denominator still refuse (KB-0123: 46 % of graduations are born full)"
    ),
    "participation": "the whole life of the coin is the window: volume = real SOL in the curve",
    "sizing": "the floor follows the ticket when the profile's floor is above it",
}
"""Checks that run under a launch rule — recorded with ``launch`` in the message."""


class MemeLaunchProfile(MemeModel):
    """The launch lane's own numbers, read by the executor from ``MEME_LAUNCH_*``
    and handed to the engine as an input (§2: nothing here reads an environment)."""

    ticket_sol: Decimal = Field(gt=0)
    """``MEME_LAUNCH_TICKET_SOL`` — the ceiling of one launch buy (0,01 by default)."""
    max_open: int = Field(ge=1)
    """``MEME_LAUNCH_MAX_OPEN`` — launch positions + pending launch intents (2)."""
    max_participation_pct: Decimal = Field(gt=0, le=1)
    """``MEME_LAUNCH_MAX_PARTICIPATION_PCT`` — of the real SOL already in the curve."""
    max_token_age_s: int = Field(ge=1)
    """``MEME_LAUNCH_MAX_AGE_S`` — older than this the launch is over (5 s)."""


def launch_floor(limits: MemeLimits, launch: MemeLaunchProfile) -> Decimal:
    """Check 23's floor in this profile: the profile's, unless the ticket is below it."""
    return min(limits.min_trade_sol, launch.ticket_sol)


def launch_open_cap_check(wallet: MemeWalletState, launch: MemeLaunchProfile) -> MemeCheck:
    """Check 27 — the launch's own cap, on launch positions and pending launch
    intents only. The global cap (check 16) still counts every slot."""
    used = sum(1 for p in wallet.positions if p.lane == LAUNCH_LANE) + sum(
        1 for i in wallet.pending_intents if i.lane == LAUNCH_LANE
    )
    return check(
        "launch_open_cap",
        used < launch.max_open,
        LAUNCH_MAX_OPEN_REACHED,
        value=Decimal(used),
        limit=Decimal(launch.max_open),
        message="launch positions + pending launch intents",
    )
