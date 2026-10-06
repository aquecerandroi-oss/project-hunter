"""The engine's parameters refuse non-finite Decimals by name (CPU plan step 2 review, 06/10/2026).

A NaN/sNaN/Infinity in a Decimal parameter does not price anything: it turns comparisons into
exceptions or silent ``False`` depending on the ambient Decimal traps, so where the engine
computes it (eagerly or lazily) would change the outcome (Astra, review of the step-2 diff).
Synthetic values (not data).
"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

import pytest

from hunter_indicators.meme.wallets.params import FollowPolicy, NonFiniteParameter, RankingParams

pytestmark = pytest.mark.unit

_ODD = (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"))


def _decimal_fields(cls: type[FollowPolicy] | type[RankingParams]) -> list[str]:
    return [f.name for f in fields(cls) if f.type in ("Decimal", Decimal)]


@pytest.mark.parametrize("cls", [FollowPolicy, RankingParams])
def test_every_decimal_parameter_refuses_a_non_finite_value(
    cls: type[FollowPolicy] | type[RankingParams],
) -> None:
    names = _decimal_fields(cls)
    assert names  # the class still has Decimal parameters to guard
    for name in names:
        for odd in _ODD:
            with pytest.raises(NonFiniteParameter, match=name) as caught:
                cls(**{name: odd})  # pyright: ignore[reportArgumentType]
            assert caught.value.field == name


def test_the_stop_fraction_named_in_the_review_is_refused() -> None:
    with pytest.raises(NonFiniteParameter, match="stop_fraction"):
        FollowPolicy(stop_fraction=Decimal("sNaN"))


def test_finite_values_still_build() -> None:
    assert FollowPolicy(stop_fraction=Decimal("0.25")).stop_fraction == Decimal("0.25")
    assert RankingParams(neutral_fraction=Decimal(0)).neutral_fraction == 0
