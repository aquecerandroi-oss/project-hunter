"""The carry-over state of the feature engine — small, explicit, serialisable.

Only what genuinely cannot be recomputed from a rolling window lives here: the
anchored ATR checkpoint (``atr.py``). Everything else is a pure function of the
context, which is what keeps a bootstrap over persisted candles and a running
scanner on the same number.

The scanner (T2.5) owns persistence and recovery of this state; T2.2 only
guarantees that it round-trips without losing a digit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hunter_indicators.features.atr import AtrCheckpoint

FEATURE_STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class FeatureState:
    """Per-market state carried between two feature computations."""

    atr_15m: AtrCheckpoint | None = None
    state_version: int = FEATURE_STATE_VERSION

    def as_wire(self) -> dict[str, Any]:
        return {
            "atr_15m": self.atr_15m.as_wire() if self.atr_15m else None,
            "state_version": self.state_version,
        }

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> FeatureState:
        checkpoint = data.get("atr_15m")
        return cls(
            atr_15m=AtrCheckpoint.from_wire(checkpoint) if checkpoint else None,
            state_version=int(data.get("state_version", FEATURE_STATE_VERSION)),
        )


EMPTY_STATE = FeatureState()
"""A cold start: every stateful calculator warms up from the context it is given."""

__all__ = ["EMPTY_STATE", "FEATURE_STATE_VERSION", "FeatureState"]
