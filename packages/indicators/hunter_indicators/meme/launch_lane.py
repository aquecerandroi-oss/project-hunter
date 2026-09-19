"""The launch lane's own gate (T4.67a, EXP-M18): whether a pump.fun ``create``
is worth a proposal **before any curve data exists** — no 15-second base row,
no holders, no tape, no pedigree. The pre-registration
(``obsidian/05-EXPERIMENTS/EXP-M18-sniper-de-lancamento.md``) names exactly
four criteria, and this module is the closed vocabulary of what refuses them:

- ``is_mayhem`` — the create frame's own bit; ``True`` refuses, unknown refuses
  (fail closed, the same reading every other gate gives a missing flag);
- the creator's own initial buy (``creator_initial_sol``) above the ceiling —
  a large dev buy is the dev pricing itself in ahead of the lane, not the
  lane's own edge;
- ``initial_real_token_reserves`` reconstructed from the frame and found
  insane — a curve whose numbers do not reconcile against the program's own
  constant is not a curve this lane's quote arithmetic can price;
- the symbol matching one created in the last 60 seconds — M-P3's "clone de
  ticker" (``pedigree.py``), narrowed here to what is cheap to know **without**
  a database read: the launch lane's own in-memory memory of recent symbols
  (``hunter_meme_worker.launch_lane_symbols``), not ``symbol_dup_24h``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import INITIAL_REAL_TOKEN_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES

__all__ = [
    "LAUNCH_LANE_REFUSALS",
    "LaunchFeatures",
    "LaunchGate",
    "evaluate_launch",
    "initial_real_token_reserves_is_sane",
    "reconstruct_initial_real_token_reserves",
]

_VIRTUAL_MINUS_REAL_OFFSET: Final = INITIAL_VIRTUAL_TOKEN_RESERVES - INITIAL_REAL_TOKEN_RESERVES
"""279 900 000 tokens — the program's own constant gap between the virtual and
the real side of a brand-new **standard** curve; a Mayhem curve or a future
program version would reconcile to something else, which is exactly what
:func:`initial_real_token_reserves_is_sane` is there to catch."""

LAUNCH_LANE_REFUSALS: Final = frozenset(
    {
        "mayhem",
        "mayhem_unknown",
        "creator_initial_sol_too_high",
        "creator_initial_sol_unknown",
        "initial_real_token_reserves_insane",
        "initial_real_token_reserves_unknown",
        "symbol_clone_recent",
    }
)
"""The closed vocabulary this module can add to a launch decision's refusals."""


@dataclass(frozen=True, slots=True)
class LaunchGate:
    """One registered launch gate. ``version`` bumps whenever a threshold moves."""

    key: str
    version: int
    max_creator_initial_sol: Decimal
    sanity_tolerance_pct: Decimal = Decimal(1)
    """How far :func:`reconstruct_initial_real_token_reserves` may sit from
    :data:`~hunter_indicators.meme.curve.INITIAL_REAL_TOKEN_RESERVES` and still
    read as ``sane`` — the reconstruction is exact integer arithmetic on a
    standard curve, so 1 % is generous headroom, not a measured band."""

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version starts at 1")
        if self.max_creator_initial_sol <= 0:
            raise ValueError("max_creator_initial_sol must be positive")
        if self.sanity_tolerance_pct <= 0:
            raise ValueError("sanity_tolerance_pct must be positive")


@dataclass(frozen=True, slots=True)
class LaunchFeatures:
    """What one ``create`` frame gives the gate, plus the one thing the launch
    lane's own memory answers (``symbol_clone_recent``) — nothing here reads
    a table."""

    is_mayhem: bool | None
    creator_initial_sol: Decimal | None
    initial_real_token_reserves: Decimal | None
    symbol_clone_recent: bool


def reconstruct_initial_real_token_reserves(
    initial_virtual_token_reserves: Decimal, creator_initial_tokens: Decimal | None
) -> Decimal | None:
    """The real token reserve a standard curve started at, worked back from the
    ``create`` frame's own numbers: the frame's virtual reserve is already
    **after** the creator's own buy (T4.45's own finding, ``models.py``), so
    adding the buy back gives the pre-buy virtual reserve, and subtracting the
    program's fixed offset gives the pre-buy real reserve — which is the
    launch denominator, unconditionally, for every trade that follows.

    ``None`` when the creator's own buy was not observed (a frame that saw
    nothing bought is ``Decimal(0)``, never ``None`` — T4.45's own distinction,
    preserved here: only a genuinely absent field refuses to reconstruct).
    """
    if creator_initial_tokens is None:
        return None
    with localcontext(CONTEXT):
        pre_buy_virtual = initial_virtual_token_reserves + creator_initial_tokens
        return pre_buy_virtual - _VIRTUAL_MINUS_REAL_OFFSET


def initial_real_token_reserves_is_sane(value: Decimal | None, gate: LaunchGate) -> bool:
    """``True`` when ``value`` reconciles against the program's own constant
    within :attr:`LaunchGate.sanity_tolerance_pct` — ``False`` for ``None``
    (the caller already refuses that by name) or for a reconstruction the
    program's constant does not explain (a Mayhem curve dressed as a create
    frame, a future layout this module has not seen)."""
    if value is None:
        return False
    with localcontext(CONTEXT):
        tolerance = INITIAL_REAL_TOKEN_RESERVES * gate.sanity_tolerance_pct / Decimal(100)
        return abs(value - INITIAL_REAL_TOKEN_RESERVES) <= tolerance


def evaluate_launch(features: LaunchFeatures, gate: LaunchGate) -> tuple[str, ...]:
    """The named refusals — empty when the launch is worth a proposal. Pure."""
    refusals: list[str] = []
    if features.is_mayhem is None:
        refusals.append("mayhem_unknown")
    elif features.is_mayhem:
        refusals.append("mayhem")
    if features.creator_initial_sol is None:
        refusals.append("creator_initial_sol_unknown")
    elif features.creator_initial_sol > gate.max_creator_initial_sol:
        refusals.append("creator_initial_sol_too_high")
    if features.initial_real_token_reserves is None:
        refusals.append("initial_real_token_reserves_unknown")
    elif not initial_real_token_reserves_is_sane(features.initial_real_token_reserves, gate):
        refusals.append("initial_real_token_reserves_insane")
    if features.symbol_clone_recent:
        refusals.append("symbol_clone_recent")
    return tuple(refusals)
