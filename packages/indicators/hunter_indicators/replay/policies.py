"""The eight exit policies and the seven contrasts, declared before any result.

Every policy is registered the way a feature is (``key``, ``version``,
``parameters``, ``description``, ``inputs``): changing a rule is a **new
version**, never an edit of an existing one, because a policy that changed
meaning silently would make two runs of EXP-0004 incomparable.

What each policy may change is deliberately narrow, so each contrast measures
one thing:

- ``base`` (INV-A) — what the Lab tracked: stop, target1 at 1.5 ATR0 from the
  reference, the strategy's own invalidation, horizon;
- ``INV-B`` — no invalidation, target kept;
- ``INV-C`` — invalidation only after **two consecutive** aligned closes below
  the level;
- ``INV-E`` — invalidation at ``L - 0.25 x ATR0``;
- ``TGT-3`` / ``TGT-4.5`` — target at 3.0 / 4.5 ATR0 from the reference (the
  ``target2``/``target3`` the strategy already computed and persisted);
- ``EXIT-NOTGT`` — no target; stop, invalidation and horizon unchanged;
- ``EXIT-CHAN`` — no target; **the original invalidation is kept** and a channel
  exit is added (close of a 15m bar below the lowest of the previous 10 15m
  closes). Keeping the invalidation is what makes ``CHAN - NOTGT`` measure the
  channel and not the removal of the invalidation (Astra, R1 design review).

The entry side is never touched: the geometry check ``stop < P_entry <
target1`` stays frozen at the base, and no arm occupies or re-arms an episode
slot. This is a replay, not eight independent strategies.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "BASE",
    "CONTRASTS",
    "FAMILY_SIZE",
    "MIN_EFFECT_R",
    "NO_TARGET_FACTOR",
    "POLICIES",
    "ChannelRule",
    "Contrast",
    "ExitPolicy",
    "InvalidationRule",
    "TargetRule",
    "buffered_level",
    "check_target_unreachable",
    "no_target_level",
    "policy",
]

NO_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType({})
"""A policy with nothing to parameterise still declares an empty mapping."""

BASE: Final = "base"

MIN_EFFECT_R: Final = Decimal("0.05")
"""Declared minimum effect of the block (Strategy Backlog, line T-005): a
difference smaller than this is not worth acting on even if it were certain."""

NO_TARGET_FACTOR: Final = Decimal("1000000")
"""How far above the reference the sentinel "no target" sits.

``TrackingPlan.target1`` is not optional, so "no target" is expressed as a level
no candle can reach. It is a declared constant, and
:func:`check_target_unreachable` *proves* it was never touched in the window
being replayed instead of assuming it (Astra, R1 design review): a sentinel that
is reached would silently become a target and fabricate an exit.
"""


class TargetRule(StrEnum):
    """Where ``target1`` comes from in an arm."""

    AS_DECIDED = "as_decided"
    """``virtual_targets[0]`` — 1.5 ATR0 from the reference."""
    TARGET2 = "target2"
    """``virtual_targets[1]`` — 3.0 ATR0, already computed at the decision."""
    TARGET3 = "target3"
    """``virtual_targets[2]`` — 4.5 ATR0, already computed at the decision."""
    NONE = "none"
    """No target: the sentinel above."""


class InvalidationRule(StrEnum):
    """How the invalidation is observed in an arm."""

    AS_DECIDED = "as_decided"
    NONE = "none"
    TWO_CLOSES = "two_consecutive_closes"
    BUFFERED = "buffered_atr"


@dataclass(frozen=True, slots=True)
class ChannelRule:
    """Exit at a close below the lowest of the previous ``lookback`` closes."""

    lookback: int
    timeframe: Timeframe


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """One registered exit policy. ``version`` bumps whenever a rule changes."""

    key: str
    version: int
    description: str
    inputs: tuple[str, ...]
    target: TargetRule
    invalidation: InvalidationRule
    parameters: Mapping[str, str] = NO_PARAMETERS
    channel: ChannelRule | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("a policy version starts at 1")


@dataclass(frozen=True, slots=True)
class Contrast:
    """One declared comparison, ``treatment - control``, paired by signal."""

    key: str
    treatment: str
    control: str
    question: str


_CANDLES: Final = ("candles:1m", "signal_outcomes.meta")
_ATR: Final = ("candles:1m", "signal_outcomes.meta", "agent_signals.supporting_features.atr")

POLICIES: Final[Mapping[str, ExitPolicy]] = {
    p.key: p
    for p in (
        ExitPolicy(
            key=BASE,
            version=1,
            description="INV-A: what the Lab tracked - stop, target1, invalidation, horizon.",
            inputs=_CANDLES,
            target=TargetRule.AS_DECIDED,
            invalidation=InvalidationRule.AS_DECIDED,
        ),
        ExitPolicy(
            key="INV-B",
            version=1,
            description="No invalidation; stop, target1 and horizon unchanged.",
            inputs=_CANDLES,
            target=TargetRule.AS_DECIDED,
            invalidation=InvalidationRule.NONE,
        ),
        ExitPolicy(
            key="INV-C",
            version=1,
            description="Invalidation only after two consecutive aligned closes below the level.",
            inputs=_CANDLES,
            target=TargetRule.AS_DECIDED,
            invalidation=InvalidationRule.TWO_CLOSES,
            parameters={"required_closes": "2"},
        ),
        ExitPolicy(
            key="INV-E",
            version=1,
            description="Invalidation at L - 0.25 x ATR0 (the frozen ATR of the decision).",
            inputs=_ATR,
            target=TargetRule.AS_DECIDED,
            invalidation=InvalidationRule.BUFFERED,
            parameters={"buffer_atr": "0.25"},
        ),
        ExitPolicy(
            key="TGT-3",
            version=1,
            description="Target at 3.0 ATR0 from the reference (the persisted target2).",
            inputs=_CANDLES,
            target=TargetRule.TARGET2,
            invalidation=InvalidationRule.AS_DECIDED,
            parameters={"target_atr": "3"},
        ),
        ExitPolicy(
            key="TGT-4.5",
            version=1,
            description="Target at 4.5 ATR0 from the reference (the persisted target3).",
            inputs=_CANDLES,
            target=TargetRule.TARGET3,
            invalidation=InvalidationRule.AS_DECIDED,
            parameters={"target_atr": "4.5"},
        ),
        ExitPolicy(
            key="EXIT-NOTGT",
            version=1,
            description="No target; stop, invalidation and horizon unchanged.",
            inputs=_CANDLES,
            target=TargetRule.NONE,
            invalidation=InvalidationRule.AS_DECIDED,
            parameters={"target": "none"},
        ),
        ExitPolicy(
            key="EXIT-CHAN",
            version=1,
            description=(
                "No target; original invalidation kept and a channel exit added: "
                "close of a 15m bar below the lowest of the previous 10 15m closes."
            ),
            inputs=_CANDLES,
            target=TargetRule.NONE,
            invalidation=InvalidationRule.AS_DECIDED,
            parameters={"target": "none", "exit_lookback": "10", "exit_timeframe": "15m"},
            channel=ChannelRule(lookback=10, timeframe=Timeframe.M15),
        ),
    )
}

CONTRASTS: Final[tuple[Contrast, ...]] = (
    Contrast("INV-B - base", "INV-B", BASE, "T-005: does the invalidation add value?"),
    Contrast("INV-C - base", "INV-C", BASE, "T-005: does confirming it over two closes help?"),
    Contrast("INV-E - base", "INV-E", BASE, "T-005: does a 0.25 ATR buffer help?"),
    Contrast("TGT-3 - base", "TGT-3", BASE, "L1: is a 3.0 ATR target better?"),
    Contrast("TGT-4.5 - base", "TGT-4.5", BASE, "L1: is a 4.5 ATR target better?"),
    Contrast("EXIT-NOTGT - base", "EXIT-NOTGT", BASE, "L2: is the target cutting the right tail?"),
    Contrast("EXIT-CHAN - EXIT-NOTGT", "EXIT-CHAN", "EXIT-NOTGT", "L2: does the channel exit add?"),
)

FAMILY_SIZE: Final = len(CONTRASTS)
"""Holm always divides by seven, even when ``--policies`` runs a subset: a
partial run must not silently lighten the multiplicity penalty."""


def policy(key: str) -> ExitPolicy:
    """The registered policy ``key``, or ``KeyError``."""
    return POLICIES[key]


def buffered_level(level: Decimal, atr0: Decimal, buffer_atr: Decimal) -> Decimal:
    """``L - buffer x ATR0`` — INV-E's invalidation level."""
    with localcontext(CONTEXT):
        return level - buffer_atr * atr0


def no_target_level(reference: Decimal) -> Decimal:
    """The declared unreachable target of the no-target arms."""
    with localcontext(CONTEXT):
        return reference * NO_TARGET_FACTOR


def check_target_unreachable(sentinel: Decimal, highs: Sequence[Decimal]) -> None:
    """Prove the sentinel was never touched in the replayed window."""
    for high in highs:
        if high >= sentinel:
            raise ValueError(
                f"no-target sentinel {sentinel} was reached by a candle high {high}: "
                "the arm would fabricate a target exit"
            )
