"""The immutable decision envelope — SHADOW-LAB.md "Decisão conjunta" §2.

``agent_signals.supporting_features`` is written once, at the decision, and
never again. It has to answer, months later and without the code at hand, "what
did the strategy see and what did it compute?": the observation instant (the
reference bar close, *not* the decision time), every feature it used with its
availability, the ATR reading with its seed and anchor so the number can be
reproduced, the assumed cost profile of the experiment, the universe
eligibility at that instant, and the labels that keep this research
(``purpose = "research_only"``, ``params_format``).

What is deliberately **not** here: ``decision_at`` and ``cohort``. Those belong
to the run, not to the observation, and the worker adds them when it persists —
keeping them out is what lets the same context replay to the same envelope.

Serialisation goes through :func:`hunter_core.strategies.canonical.canonical_json`,
so the persisted JSONB is exactly the canonical form (numbers as normalised
strings, timestamps as ISO-8601 ``Z``): a value read back is the value decided.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import PARAMS_FORMAT, canonical_json

PURPOSE_RESEARCH_ONLY = "research_only"
"""Label persisted in the envelope and in the event (SHADOW-LAB.md §10).

The proposal builder refuses a signal carrying it: shadow evidence never becomes
an order.
"""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AssumedCosts(_Frozen):
    """The declared cost hypothesis of the experiment — SHADOW-LAB.md §3.

    Assumptions, not verified exchange fees, and part of the frozen version:
    every hypothetical R only means something next to them. A typed frozen model
    rather than a dict, so the snapshot cannot be mutated between the decision
    and the write (``frozen=True`` does not freeze a nested dict).
    """

    spread_bps: Decimal = Field(ge=0)
    slippage_bps: Decimal = Field(ge=0)
    fee_bps: Decimal = Field(ge=0)
    max_entry_delay_s: int = Field(gt=0)


class FeatureEvidence(_Frozen):
    """One input of the decision, available or not, with why and over which window."""

    name: str
    value: Decimal | int | str | None = None
    available: bool = True
    unavailable_reason: str | None = None
    window: int | None = None
    source_ts: datetime | None = None

    @field_validator("source_ts", mode="after")
    @classmethod
    def _source_ts_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)


class AtrEvidence(_Frozen):
    """The ATR reading behind stop/target, with everything needed to *re-derive* it.

    Formula (``method``), initialisation policy (``origin``) and the exact window
    (``window_start``/``window_end``/``bars_used``) are all recorded: the same
    formula over a different window is a different number, so freezing the
    formula alone would not make the reading auditable.

    It is not self-sufficient, and does not claim to be: recomputing the true
    ranges still needs the bars of that window. Keeping those bars available for
    as long as the signal matters is the persistence side of the contract
    (SHADOW-LAB.md §8), not something a pure function can guarantee.
    """

    method: str
    origin: str
    timeframe: str
    period: int
    value: Decimal
    percent: Decimal
    seed: Decimal
    seed_anchor: datetime
    bars_used: int
    window_start: datetime
    window_end: datetime
    """Close of the last bar of the ATR window — for a 5m strategy this is the
    last *completed* 15m boundary at or before ``observation_ts``, never later."""

    @field_validator("seed_anchor", "window_start", "window_end", mode="after")
    @classmethod
    def _times_are_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class SupportingFeatures(_Frozen):
    """The whole envelope. Written once; :meth:`to_jsonable` is what is persisted."""

    observation_ts: datetime
    """``source_bar_close`` — the instant the strategy observed, not when it ran."""
    timeframe: str
    strategy_key: str
    strategy_version: str
    features: tuple[FeatureEvidence, ...] = ()
    """Ordered as the strategy computed them; the order is part of the snapshot."""
    atr: AtrEvidence | None = None
    assumed_costs: AssumedCosts
    confidence_method: str = "constant_uncalibrated_v1"
    """``confidence`` in v1 is a convention, not a probability: nothing in this
    system has been calibrated yet, and the Lab is what will measure it
    (Astra, S1 design review). A calibrated confidence is a new method name."""
    eligible: bool = True
    eligibility_reason: str | None = None
    purpose: str = PURPOSE_RESEARCH_ONLY
    params_format: int = PARAMS_FORMAT

    @field_validator("observation_ts", mode="after")
    @classmethod
    def _observation_ts_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    def to_jsonable(self) -> dict[str, Any]:
        """The canonical JSON object persisted in ``agent_signals.supporting_features``."""
        parsed: dict[str, Any] = json.loads(canonical_json(self.model_dump()))
        return parsed
