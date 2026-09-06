"""Shapes shared by every Shadow Lab schema module.

``.claude/state/contract-S3-lab.md`` is the fixed contract; SHADOW-LAB.md §9 is
where the metric names come from. Everything here is read-only research over
global (non-tenant) tables — DATABASE.md §16.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]

LAB_LABEL = "SOMBRA — hipotético, sem capital, custos assumidos"
"""Fixed label required on every summary response (SHADOW-LAB.md §9)."""


class NullableMetric(BaseModel):
    """A rate/expectancy that is ``null`` with a reason instead of a lie.

    Never a bare ``None``: a denominator of zero always says *why* — "no
    sample" is a different fact from "no losses" (SHADOW-LAB.md §9).
    """

    value: DecimalStr | None
    reason: str | None = None


class ProfitFactorOut(BaseModel):
    """PF with its denominator spelled out (Astra, contract review, must-fix 3).

    ``sum_positive``/``sum_negative_abs``/``sample_size`` are always present,
    even when ``value`` is null, so a caller can tell "PF is null because there
    is no sample" from "PF is null because nobody has lost yet" without
    re-deriving the sums itself.
    """

    value: DecimalStr | None
    reason: str | None = None
    sum_positive: DecimalStr
    sum_negative_abs: DecimalStr
    sample_size: int


class SumOfROut(BaseModel):
    """``sum_of_hypothetical_r`` — named and ordered explicitly (SHADOW-LAB.md §9)."""

    value: DecimalStr | None
    reason: str | None = None
    count: int
    ordered_by: str = "exit_ts"
