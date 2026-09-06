"""The one model base of the risk core: frozen, closed and float-free.

Three properties every input and every output of the engine needs, stated once:

- **frozen** — a decision is evidence. Nothing that was evaluated may be
  rebound afterwards, so the object persisted in ``trade_proposals`` is the
  object the checks ran against;
- **``extra="forbid"``** — a misspelled field is a silent limit that never
  applies. ``max_asset_exposure`` instead of ``max_asset_exposure_pct`` would
  otherwise be accepted and ignored;
- **no ``float``** — ``Decimal("0.1") != Decimal(0.1)``, and pydantic coerces a
  float to ``Decimal`` without complaining. CLAUDE.md forbids float for money;
  here the ban is enforced at construction instead of by review, because the
  error it produces (a limit that is 0.10000000000000000555… of the equity)
  never fails a test and never shows up in a log.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, model_validator


class RiskModel(BaseModel):
    """Base of every value object in ``hunter_risk``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _refuse_float(cls, data: Any) -> Any:
        untouched: Any = data
        if isinstance(data, Mapping):
            for key, value in cast("Mapping[object, object]", data).items():
                if isinstance(value, float):
                    raise TypeError(
                        f"{cls.__name__}.{key} received a float; money and limits are Decimal"
                    )
        return untouched
