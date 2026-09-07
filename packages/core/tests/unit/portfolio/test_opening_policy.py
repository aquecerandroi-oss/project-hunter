"""The FX admission policy of the opening — pure, no database.

"Fonte inválida não abre" (T3.11). Every refusal below is a way an opening could
otherwise convert R$100.000 at a rate that was never true at that instant, and
each one names the field it refused on so the audit can say why.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.db.models.fx import FxObservation
from hunter_core.portfolio.opening import (
    PAPER_FX_POLICY,
    FxObservationRejected,
    FxPolicy,
    validate_fx_observation,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)


def _observation(
    *,
    pair: str = "USDTBRL",
    source: str = PAPER_FX_POLICY.source,
    rate: Decimal = Decimal("5.4321"),
    observed_at: datetime = _NOW,
    available_at: datetime | None = None,
) -> FxObservation:
    """A real ``fx_observations`` row, unattached: the validation is pure."""
    return FxObservation(
        id=uuid.uuid4(),
        pair=pair,
        source=source,
        rate=rate,
        observed_at=observed_at,
        available_at=available_at if available_at is not None else observed_at,
    )


class TestWhatMayOpenAWallet:
    def test_a_fresh_observation_from_the_declared_source_passes(self) -> None:
        validate_fx_observation(_observation(), as_of=_NOW)

    def test_five_minutes_of_availability_is_the_edge_and_is_allowed(self) -> None:
        validate_fx_observation(_observation(observed_at=_NOW - timedelta(seconds=300)), as_of=_NOW)

    def test_a_second_past_the_edge_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match="available_at is 301s old"):
            validate_fx_observation(
                _observation(observed_at=_NOW - timedelta(seconds=301)), as_of=_NOW
            )

    def test_a_backfill_cannot_make_an_old_quote_fresh(self) -> None:
        """Available a minute ago, quoted twenty minutes ago: two limits, not one."""
        with pytest.raises(FxObservationRejected, match="observed_at is 1200s old"):
            validate_fx_observation(
                _observation(
                    observed_at=_NOW - timedelta(minutes=20),
                    available_at=_NOW - timedelta(minutes=1),
                ),
                as_of=_NOW,
            )

    def test_a_rate_that_had_not_reached_us_yet_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match="had not reached us"):
            validate_fx_observation(
                _observation(observed_at=_NOW + timedelta(seconds=1)), as_of=_NOW
            )

    def test_an_observation_available_before_it_was_observed_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match="ahead of available_at"):
            validate_fx_observation(
                _observation(observed_at=_NOW, available_at=_NOW - timedelta(seconds=5)),
                as_of=_NOW,
            )

    def test_another_source_is_refused_even_with_a_plausible_rate(self) -> None:
        with pytest.raises(FxObservationRejected, match="source"):
            validate_fx_observation(_observation(source="some.blog.rss"), as_of=_NOW)

    def test_another_pair_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match="pair"):
            validate_fx_observation(_observation(pair="USDBRL"), as_of=_NOW)

    def test_a_non_positive_rate_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match="not positive"):
            validate_fx_observation(_observation(rate=Decimal(0)), as_of=_NOW)

    def test_the_policy_is_a_parameter_not_a_constant_in_the_code(self) -> None:
        strict = FxPolicy(availability_max_age_s=30, observation_max_age_s=30)
        with pytest.raises(FxObservationRejected, match="30s the policy allows"):
            validate_fx_observation(
                _observation(observed_at=_NOW - timedelta(seconds=60)), as_of=_NOW, policy=strict
            )

    def test_a_naive_instant_is_refused_rather_than_assumed_to_be_utc(self) -> None:
        with pytest.raises(ValueError, match="naive datetime"):
            validate_fx_observation(_observation(), as_of=datetime(2026, 9, 6, 15, 30))  # noqa: DTZ001
