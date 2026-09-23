"""EXP-M22's two entry criteria (T4.79) — the readings of
:mod:`hunter_meme_worker.absorb` judged against two optional switches of a
rule set, each off by default, each unknown refused by name (a lane that
carries no absorption reading is not "no sell was seen"):

- ``require_absorb_confirmed`` (the treatment, ``absorb_v0/1``) →
  ``absorb_not_confirmed`` until the sell was recovered and held;
- ``require_absorb_sell_seen`` (the control, ``absorb_v0/2``) →
  ``absorb_sell_not_seen`` until the first large sell, and again once its
  window closed.

Both share one unknown, ``absorb_unknown``: no reading at all (the 15-second
lane, ``GateRow.absorb is None``) or a coverage gap (``None`` readings).
Wired beside ``require_twitter``/``require_event`` in
``proposals.evaluate_gate`` — spec-level switches judged in the worker, not
keys of ``EntryGate`` — because only the event lane can ever answer them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hunter_meme_worker.absorb import (
    DEFAULT_CONFIRM_TTL_S,
    DEFAULT_HOLD_S,
    DEFAULT_RECOVERY_WINDOW_S,
    DEFAULT_SELL_SEEN_TTL_S,
    DEFAULT_SELL_SHARE,
)
from hunter_meme_worker.lab_values import money_str, optional_money_str

if TYPE_CHECKING:
    from hunter_meme_worker.absorb import AbsorbFeatures

__all__ = [
    "REFUSAL_ABSORB_NOT_CONFIRMED",
    "REFUSAL_ABSORB_SELL_NOT_SEEN",
    "REFUSAL_ABSORB_UNKNOWN",
    "absorb_reason_block",
    "absorb_refusals",
]

REFUSAL_ABSORB_UNKNOWN = "absorb_unknown"
REFUSAL_ABSORB_NOT_CONFIRMED = "absorb_not_confirmed"
REFUSAL_ABSORB_SELL_NOT_SEEN = "absorb_sell_not_seen"


def absorb_refusals(
    features: AbsorbFeatures | None, *, require_confirmed: bool, require_sell_seen: bool
) -> tuple[str, ...]:
    """The criteria, each only when the set asks; unknown first and alone."""
    if not (require_confirmed or require_sell_seen):
        return ()
    if features is None:
        return (REFUSAL_ABSORB_UNKNOWN,)
    if (require_confirmed and features.confirmed is None) or (
        require_sell_seen and features.sell_seen is None
    ):
        return (REFUSAL_ABSORB_UNKNOWN,)
    refusals: list[str] = []
    if require_confirmed and not features.confirmed:
        refusals.append(REFUSAL_ABSORB_NOT_CONFIRMED)
    if require_sell_seen and not features.sell_seen:
        refusals.append(REFUSAL_ABSORB_SELL_NOT_SEEN)
    return tuple(refusals)


def _iso(at: Any) -> str | None:
    return None if at is None else at.isoformat()


def absorb_reason_block(features: AbsorbFeatures | None) -> dict[str, Any]:
    """``meme_proposals.reasons``' ``absorb`` block — the two readings, their
    timestamps and the frozen numbers they were judged with."""
    return {
        "feature": "absorb",
        "sell_seen": None if features is None else features.sell_seen,
        "confirmed": None if features is None else features.confirmed,
        "sell_at": None if features is None else _iso(features.sell_at),
        "reference_sell_at": None if features is None else _iso(features.reference_sell_at),
        "sell_share": None if features is None else optional_money_str(features.sell_share),
        "recovered_at": None if features is None else _iso(features.recovered_at),
        "confirmed_at": None if features is None else _iso(features.confirmed_at),
        "sells_seen": None if features is None else features.sells_seen,
        "reason": None if features is None else features.reason,
        "min_sell_share": money_str(DEFAULT_SELL_SHARE),
        "recovery_window_s": DEFAULT_RECOVERY_WINDOW_S,
        "hold_s": DEFAULT_HOLD_S,
        "sell_seen_ttl_s": DEFAULT_SELL_SEEN_TTL_S,
        "confirm_ttl_s": DEFAULT_CONFIRM_TTL_S,
    }
