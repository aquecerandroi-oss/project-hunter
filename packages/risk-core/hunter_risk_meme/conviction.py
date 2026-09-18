"""T4.61c — check 26 ``conviction`` and the ``conviction`` ceiling of §5: the
conviction ladder (§17) as an **input** of the decision, never a verdict beside it.

T4.61b ran the ladder in the executor and handed the engine a shrunken
``requested_sol``; the decision then said ``binding_constraint = requested`` for
a clamp that was the policy's (review A4) and ``approved = true`` for an order
the ladder had refused (A9). Here the ladder's verdict arrives as
:class:`MemeConviction` — computed by the caller from evidence it read, pure once
in hand, like every other input of §2 — and the engine does the two things only
it should do: **record a check by name** and, when the ladder yields an
admissible size, **publish it as the ceiling** that binds.

The engine never sees the rungs; it sees ``enabled``, the size the ladder
allows, and the ladder's own refusal. Off (or absent) the check passes and the
ceiling does not constrain: the flat size of before, byte for byte. A ladder
that refuses does not constrain either — the other 25 checks are recorded at
the flat size, and check 26 is the refusal, first in ``first_refusal`` when the
rest passed. A ladder whose size is below ``min_trade_sol`` is ``conviction_too_small``:
dust is a refusal, never a rounded-up order (§5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import Field, model_validator

from hunter_risk_meme.base import MemeModel
from hunter_risk_meme.decision import LimitCap, MemeCheck, check
from hunter_risk_meme.limits import MemeLimits

__all__ = [
    "CONVICTION_REFUSALS",
    "CONVICTION_TOO_LOW",
    "CONVICTION_TOO_SMALL",
    "ENTRY_AFTER_DROP",
    "ENTRY_AFTER_DROP_UNKNOWN",
    "LADDER_REFUSALS",
    "MemeConviction",
    "conviction_cap",
    "conviction_check",
]

ENTRY_AFTER_DROP: Final = "entry_after_drop"
"""Real SOL ≥ ``drop_pct`` below the peak of the last ``drop_window_s`` (KB-0118)."""
ENTRY_AFTER_DROP_UNKNOWN: Final = "entry_after_drop_unknown"
"""Fewer than two photos of the curve in the window, or the read failed: the one
clean edge cannot be judged, so the entry is refused — not discounted (§8)."""
CONVICTION_TOO_LOW: Final = "conviction_too_low"
"""The product of the rungs fell below the ladder's floor."""
CONVICTION_TOO_SMALL: Final = "conviction_too_small"
"""The sized order is below ``min_trade_sol`` — decided **here**, against the
profile's floor, so 0,07 × 0,25 = 0,0175 SOL is never sent (review A5)."""

LADDER_REFUSALS: Final[frozenset[str]] = frozenset(
    {ENTRY_AFTER_DROP, ENTRY_AFTER_DROP_UNKNOWN, CONVICTION_TOO_LOW}
)
"""What the caller's ladder may say; anything else is not a conviction refusal."""
CONVICTION_REFUSALS: Final[frozenset[str]] = LADDER_REFUSALS | {CONVICTION_TOO_SMALL}
"""Every name check 26 can produce (all in ``checks.REFUSAL_NAMES``)."""

_ZERO = Decimal(0)


class MemeConviction(MemeModel):
    """The ladder's verdict as the engine receives it (§17, check 26)."""

    enabled: bool = False
    """``MEME_CONVICTION_SIZING``; off ⇒ the check passes and nothing constrains."""
    multiplier: Decimal = Field(ge=0, le=1, default=Decimal(1))
    sol_sized: Decimal = Field(ge=0, default=_ZERO)
    """``quantize(min(requested, max_sol_per_trade) × multiplier)`` — the ceiling."""
    refusal: str | None = None
    """One of :data:`LADDER_REFUSALS`, or ``None`` when the ladder allows a size."""
    detail: str = ""

    @model_validator(mode="after")
    def _named(self) -> MemeConviction:
        if self.refusal is not None and self.refusal not in LADDER_REFUSALS:
            raise ValueError(f"not a ladder refusal: {self.refusal}")
        return self


def _verdict(conviction: MemeConviction | None, limits: MemeLimits) -> str | None:
    """The refusal check 26 records, or ``None``: the ladder's own first, then
    the dust floor of the profile."""
    if conviction is None or not conviction.enabled:
        return None
    if conviction.refusal is not None:
        return conviction.refusal
    if conviction.sol_sized < limits.min_trade_sol:
        return CONVICTION_TOO_SMALL
    return None


def conviction_cap(conviction: MemeConviction | None, limits: MemeLimits) -> LimitCap:
    """The ``conviction`` ceiling of §5: the ladder's size when it is admissible;
    ``None`` (does not constrain) when the flag is off or the ladder refused —
    a refusal is check 26's, and the other ceilings are measured at the flat size."""
    if conviction is None or not conviction.enabled:
        return LimitCap(name="conviction", sol=None, detail="off")
    refusal = _verdict(conviction, limits)
    if refusal is not None:
        return LimitCap(name="conviction", sol=None, limit=conviction.multiplier, detail=refusal)
    return LimitCap(
        name="conviction",
        sol=conviction.sol_sized,
        limit=conviction.multiplier,
        detail=f"multiplier={conviction.multiplier}",
    )


def conviction_check(conviction: MemeConviction | None, limits: MemeLimits) -> MemeCheck:
    """Check 26. Off ⇒ passed with ``message = off``; on ⇒ the ladder's refusal by
    name, or ``conviction_too_small`` below the profile's floor, or passed with
    the multiplier as ``limit`` and the sized SOL as ``value``."""
    if conviction is None or not conviction.enabled:
        return check("conviction", True, CONVICTION_TOO_SMALL, message="off")
    refusal = _verdict(conviction, limits)
    return check(
        "conviction",
        refusal is None,
        refusal or CONVICTION_TOO_SMALL,
        value=conviction.sol_sized,
        limit=limits.min_trade_sol if refusal == CONVICTION_TOO_SMALL else conviction.multiplier,
        message=conviction.detail or f"multiplier={conviction.multiplier}",
    )
