"""The one model base of the B3 risk core: frozen, closed, float-free and UTC.

A deliberate **copy** of ``hunter_risk.base.RiskModel`` (as ``hunter_risk_meme.base`` is):
``docs/RISK_ENGINE_B3.md`` makes this package a sibling that never imports
``hunter_risk`` nor ``hunter_risk_meme`` (``tests/unit/b3/test_boundary.py``). The four
properties: a decision is evidence (frozen); a misspelled limit never applies
(``extra="forbid"``); ``Decimal(0.1)`` is not ``Decimal("0.1")`` (no float anywhere, refused
at construction, contract §8.1); and every instant is timezone-aware and normalised to UTC
(a naive ``datetime`` is refused, never assumed — CLAUDE.md "time is always UTC").
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

__all__ = ["B3Model", "UtcDatetime", "as_utc"]


def as_utc(value: datetime) -> datetime:
    """``value`` in UTC; a naive ``datetime`` is refused."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetimes must be timezone-aware (UTC is never assumed)")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(as_utc)]


class B3Model(BaseModel):
    """Base of every value object in ``hunter_risk_b3``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _refuse_float(cls, data: Any) -> Any:
        """Walks the raw input, containers included: ``per_volume={1: 100.1}`` must not
        be coerced to ``Decimal('100.1')`` silently (Astra, R1 review must-fix 2)."""
        untouched: Any = data
        if isinstance(data, Mapping):
            for key, value in cast("Mapping[object, object]", data).items():
                if _has_float(value):
                    raise TypeError(
                        f"{cls.__name__}.{key} received a float; money, prices, volumes and "
                        "limits are Decimal"
                    )
        return untouched


def _has_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value).items()
        return any(_has_float(k) or _has_float(v) for k, v in items)
    if isinstance(value, list | tuple | set | frozenset):
        return any(_has_float(v) for v in cast("Iterable[object]", value))
    return False
