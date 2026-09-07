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
        assert validate_fx_observation(_observation(), as_of=_NOW) is None

    def test_five_minutes_of_availability_is_the_edge_and_is_allowed(self) -> None:
        assert (
            validate_fx_observation(
                _observation(observed_at=_NOW - timedelta(seconds=300)), as_of=_NOW
            )
            is None
        )

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


class TestThePlausibilityBand:
    """Adversarial review of ``8a6a69f``, blocking 3: a scale error or an
    inverted quote must not open a wallet just because it happens to be
    positive and pass every other check."""

    def test_a_scale_error_ten_billion_times_too_small_is_refused(self) -> None:
        with pytest.raises(FxObservationRejected, match=r"outside the plausible band"):
            validate_fx_observation(_observation(rate=Decimal("1e-10")), as_of=_NOW)

    def test_a_decimal_point_typed_one_digit_short_is_refused(self) -> None:
        """``0,54321`` typed for ``5,4321`` — the exact scale error the review
        names, one order of magnitude below the band's floor of 1."""
        with pytest.raises(FxObservationRejected, match=r"outside the plausible band"):
            validate_fx_observation(_observation(rate=Decimal("0.54321")), as_of=_NOW)

    def test_the_true_rate_is_accepted(self) -> None:
        assert validate_fx_observation(_observation(rate=Decimal("5.4321")), as_of=_NOW) is None

    def test_the_band_is_declared_on_the_policy_not_hard_coded(self) -> None:
        narrow = FxPolicy(plausible_rate_min=Decimal("6"), plausible_rate_max=Decimal("7"))
        with pytest.raises(FxObservationRejected, match=r"outside the plausible band \[6, 7\]"):
            validate_fx_observation(_observation(rate=Decimal("5.4321")), as_of=_NOW, policy=narrow)


class TestTheDeviationFromTheLastAccepted:
    """Optional second check (blocking 3): a rate far from the last one this
    same policy accepted, within a short window, is refused too — even though
    it is, on its own, inside the plausible band."""

    def test_a_rate_more_than_20_percent_off_within_ten_minutes_is_refused(self) -> None:
        last_accepted = _observation(rate=Decimal("5.0"), observed_at=_NOW - timedelta(minutes=5))
        with pytest.raises(FxObservationRejected, match="deviates"):
            validate_fx_observation(
                _observation(rate=Decimal("6.5"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=last_accepted,
            )

    def test_a_rate_within_20_percent_is_accepted(self) -> None:
        last_accepted = _observation(rate=Decimal("5.0"), observed_at=_NOW - timedelta(minutes=5))
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("5.9"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=last_accepted,
            )
            is None
        )

    def test_the_same_deviation_past_the_window_is_not_compared(self) -> None:
        """Past ten minutes a real move can explain 20%; the comparison stops
        applying rather than refusing a good quote against a stale anchor."""
        last_accepted = _observation(rate=Decimal("5.0"), observed_at=_NOW - timedelta(minutes=11))
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("6.5"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=last_accepted,
            )
            is None
        )

    def test_no_last_accepted_observation_skips_the_comparison(self) -> None:
        """The very first observation of a series has nothing to compare
        against; the caller passes ``last_accepted=None`` and only the
        absolute band applies."""
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("5.4321")), as_of=_NOW, last_accepted=None
            )
            is None
        )

    def test_a_last_accepted_of_a_different_pair_or_source_is_not_compared(self) -> None:
        """Comparing against an incompatible reading would refuse a good quote
        for a reason that has nothing to do with USDTBRL's own history."""
        wrong_pair = _observation(
            pair="USDBRL", rate=Decimal("5.0"), observed_at=_NOW - timedelta(minutes=5)
        )
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("6.5"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=wrong_pair,
            )
            is None
        )

    def test_a_last_accepted_not_strictly_before_the_current_one_is_not_compared(self) -> None:
        """``last_accepted`` observed at the same instant (or later) is not a
        *previous* reading; comparing against it would be comparing a rate
        against itself, or against the future."""
        same_instant = _observation(rate=Decimal("5.0"), observed_at=_NOW)
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("6.5"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=same_instant,
            )
            is None
        )

    def test_a_last_accepted_not_yet_available_at_the_current_instant_is_not_compared(
        self,
    ) -> None:
        """A replay at ``as_of`` must not change its verdict because a later
        accepted reading becomes known afterwards — the comparison only uses
        what was already available at ``as_of`` (Astra, follow-up review)."""
        not_yet_available = _observation(
            rate=Decimal("5.0"),
            observed_at=_NOW - timedelta(minutes=5),
            available_at=_NOW + timedelta(minutes=1),
        )
        assert (
            validate_fx_observation(
                _observation(rate=Decimal("6.5"), observed_at=_NOW),
                as_of=_NOW,
                last_accepted=not_yet_available,
            )
            is None
        )
