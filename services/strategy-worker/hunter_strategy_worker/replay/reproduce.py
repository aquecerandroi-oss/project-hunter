"""Step 1 — proving the replay reproduces the base before anything is contrasted.

Without this the seven contrasts mean nothing: if the replayed base does not
land on the outcome the Lab actually recorded, a difference between two arms is
a difference between two bugs.

Two audits, deliberately separate (Astra, R1 design review, must-fix 5):

- **trajectory** — state, result, entry, ``entry_ts``, exit instant, whether the
  exit was at an open, exit price and ``r_ex_funding``. None of it depends on
  the funding resolver;
- **settlement** — ``r_multiple``, and the funding reason behind it. A change of
  funding code (``d878fd6``: settlements identified by proximity clusters) can
  legitimately move this and nothing else. A divergence that also moves the
  trajectory is a replay bug, not a code correction, and is reported as one.

``no_entry: late:*`` is *not* reproducible from candles: lateness is evidence
about the clock at decision time, which the candles cannot re-derive. Those rows
are counted apart, never counted as reproduced.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.enums import ShadowTrackingState

if TYPE_CHECKING:
    from hunter_strategy_worker.replay.engine import ArmOutcome
    from hunter_strategy_worker.replay.load import ReplayCase

__all__ = ["Divergence", "VersionAudit", "audit_case", "gate", "summarise"]

_SCALE = Decimal(1).scaleb(-10)
"""``NUMERIC(28,10)``: what was stored was rounded to ten decimals on the way in."""


def _stored_scale(value: Decimal | None) -> Decimal | None:
    """A replayed number at the scale Postgres stored the recorded one at.

    Half-up, because that is what Postgres' ``numeric`` cast does; using the
    ambient half-even would manufacture a divergence on an exact tie.
    """
    return None if value is None else value.quantize(_SCALE, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Divergence:
    """One field where the replay and the record disagree."""

    signal_id: uuid.UUID
    version_label: str
    kind: str
    """``trajectory`` or ``settlement``."""
    field: str
    stored: str | None
    replayed: str | None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(getattr(value, "value", value))


def _diff(
    case: ReplayCase, kind: str, field_name: str, stored: Any, replayed: Any
) -> Divergence | None:
    if stored == replayed:
        return None
    return Divergence(
        signal_id=case.signal_id,
        version_label=case.version.label,
        kind=kind,
        field=field_name,
        stored=_text(stored),
        replayed=_text(replayed),
    )


def audit_case(case: ReplayCase, replayed: ArmOutcome) -> tuple[str, list[Divergence]]:
    """``(verdict, divergences)`` for one frozen entry.

    Verdicts: ``reproduced``, ``diverged``, ``not_comparable`` (a lateness the
    candles cannot re-derive) and ``unresolved`` (the replay could not finish
    the tracking — a gap or an immature horizon, reported as coverage).
    """
    stored = case.stored
    if stored.tracking_state is ShadowTrackingState.NO_ENTRY:
        if (stored.no_entry_reason or "").startswith("late"):
            return "not_comparable", []
        divergences: list[Divergence] = [
            d
            for d in (
                _diff(
                    case,
                    "trajectory",
                    "tracking_state",
                    stored.tracking_state,
                    replayed.tracking_state,
                ),
                _diff(
                    case, "trajectory", "no_entry_reason", stored.no_entry_reason, replayed.reason
                ),
            )
            if d is not None
        ]
        return ("reproduced" if not divergences else "diverged"), divergences
    if replayed.tracking_state is ShadowTrackingState.NO_ENTRY:
        # The record says the trade happened and the replay says it never
        # started: that is a **trajectory** disagreement, not missing coverage.
        # Filing it as "unresolved" would take it out of the gate's denominator
        # and let a broken replay pass (Astra, R1 fixes review, contraproof:
        # 1 hit + 99 of these still scored 1.0000).
        return "diverged", [
            d
            for d in (
                _diff(
                    case,
                    "trajectory",
                    "tracking_state",
                    stored.tracking_state,
                    replayed.tracking_state,
                ),
                _diff(case, "trajectory", "no_entry_reason", None, replayed.reason),
            )
            if d is not None
        ]
    if replayed.tracking_state is not ShadowTrackingState.TERMINAL:
        return "unresolved", []
    checks: list[Divergence | None] = [
        _diff(case, "trajectory", "result", stored.result, replayed.result),
        _diff(case, "trajectory", "entry", stored.virtual_entry, _stored_scale(replayed.entry)),
        _diff(case, "trajectory", "entry_ts", stored.entry_ts, replayed.entry_ts),
        _diff(case, "trajectory", "exit_ts", stored.exit_ts, replayed.exit_ts),
        _diff(
            case, "trajectory", "exit_price", stored.exit_price, _stored_scale(replayed.exit_price)
        ),
        # An exit at an open and an intrabar touch at the same instant price the
        # same trade but not the same funding window (``settle`` treats an
        # intrabar exit as ambiguous), so a difference here would surface as a
        # settlement-only divergence and be misread as a funding matter
        # (Astra, R1 diff review, must-fix 2).
        _diff(
            case,
            "trajectory",
            "exit_at_open",
            stored.progress.exit_at_open,
            replayed.exit_at_open,
        ),
        _diff(
            case,
            "trajectory",
            "exit_bar_open",
            stored.progress.exit_bar_open,
            replayed.exit_bar_open,
        ),
        _diff(case, "trajectory", "r_ex_funding", stored.r_ex_funding, replayed.r_ex_funding),
        _diff(case, "settlement", "r_multiple", stored.r_multiple, _stored_scale(replayed.r_net)),
        _diff(case, "settlement", "funding_reason", stored.funding_reason, replayed.funding_reason),
    ]
    divergences = [d for d in checks if d is not None]
    return ("reproduced" if not divergences else "diverged"), divergences


@dataclass(frozen=True, slots=True)
class VersionAudit:
    """Reproduction of one frozen version."""

    label: str
    total: int = 0
    reproduced: int = 0
    diverged: int = 0
    not_comparable: int = 0
    unresolved: int = 0
    diverged_settlement_only: int = 0
    """Rows whose trajectory matched and only the settlement moved — the
    population a later funding row can legitimately change."""
    divergences: tuple[Divergence, ...] = ()

    @property
    def comparable(self) -> int:
        return self.reproduced + self.diverged

    @property
    def rate(self) -> Decimal | None:
        if self.comparable == 0:
            return None
        return Decimal(self.reproduced) / Decimal(self.comparable)

    @property
    def trajectory_rate(self) -> Decimal | None:
        """Reproduction of the *path* — exit, price and ``r_ex_funding`` — which
        does not depend on the funding resolver at all."""
        if self.comparable == 0:
            return None
        matched = self.reproduced + self.diverged_settlement_only
        return Decimal(matched) / Decimal(self.comparable)


def summarise(
    rows: Sequence[tuple[str, str, Sequence[Divergence]]],
) -> list[VersionAudit]:
    """Fold ``(version label, verdict, divergences)`` into one audit per version."""
    by_label: dict[str, dict[str, Any]] = {}
    for label, verdict, divergences in rows:
        bucket = by_label.setdefault(
            label,
            {
                "total": 0,
                "reproduced": 0,
                "diverged": 0,
                "not_comparable": 0,
                "unresolved": 0,
                "diverged_settlement_only": 0,
                "divergences": [],
            },
        )
        bucket["total"] += 1
        bucket[verdict] += 1
        if verdict == "diverged" and all(d.kind == "settlement" for d in divergences):
            bucket["diverged_settlement_only"] += 1
        bucket["divergences"].extend(divergences)
    return [
        VersionAudit(
            label=label,
            total=bucket["total"],
            reproduced=bucket["reproduced"],
            diverged=bucket["diverged"],
            not_comparable=bucket["not_comparable"],
            unresolved=bucket["unresolved"],
            diverged_settlement_only=bucket["diverged_settlement_only"],
            divergences=tuple(cast("list[Divergence]", bucket["divergences"])),
        )
        for label, bucket in sorted(by_label.items())
    ]


def gate(audits: Sequence[VersionAudit], *, threshold: float) -> dict[str, Any]:
    """Step 1 is a gate, not a section: no floor, no contrasts.

    The reading that has to clear the threshold is the **trajectory** one —
    exit, price and ``r_ex_funding``, none of which depends on the funding
    resolver. A settlement-only divergence is allowed through and reported,
    because a funding row that arrived after the outcome was settled changes
    ``R_net`` legitimately; anything that moves the path is a replay bug and
    stops the run (Astra, R1 diff review, must-fix 3).
    """
    comparable = sum(a.comparable for a in audits)
    reproduced = sum(a.reproduced for a in audits)
    settlement_only = sum(a.diverged_settlement_only for a in audits)
    trajectory = reproduced + settlement_only
    rate = 0.0 if comparable == 0 else trajectory / comparable
    passed = comparable > 0 and rate >= threshold
    return {
        "threshold": f"{threshold:.4f}",
        "comparable": comparable,
        "reproduced": reproduced,
        "diverged_settlement_only": settlement_only,
        "trajectory_rate": f"{rate:.4f}",
        "full_rate": f"{0.0 if comparable == 0 else reproduced / comparable:.4f}",
        "passed": passed,
        "reason": None if passed else "reproduction_below_threshold",
    }
