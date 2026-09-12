"""The one model base of the meme risk core: frozen, closed and float-free.

A deliberate **copy** of ``hunter_risk.base.RiskModel`` rather than an import:
``docs/RISK_ENGINE_MEME.md`` §13 makes this package a sibling that *never*
imports ``hunter_risk`` (and vice versa), and a base class shared by import would
be the first thread between the two doctrines. The three properties are the
same, for the same reasons: a decision is evidence (frozen); a misspelled limit
is a limit that never applies (``extra="forbid"``); ``Decimal(0.1)`` is not
``Decimal("0.1")`` (no float on any money field, enforced at construction).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, model_validator


class MemeModel(BaseModel):
    """Base of every value object in ``hunter_risk_meme``."""

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
