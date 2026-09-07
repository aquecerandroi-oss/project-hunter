"""``FxPolicy`` — which FX observations may open or value the paper wallet.

Split out of ``opening.py`` (file-size budget, not a change of ownership): the
policy is what both the opening and the equity curve validate an observation
against (``hunter_core.portfolio.ledger.record_equity_point``), so it lives
where neither of those two write paths has to reach into the other.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from hunter_core.domain.types import ensure_utc
from hunter_core.portfolio.attribution import FX_PAIR

if TYPE_CHECKING:
    from hunter_core.db.models.fx import FxObservation


class FxPolicy(BaseModel):
    """Which observations may open a wallet. Declared by the service, not the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str = FX_PAIR
    source: str = "binance.spot.ticker"
    """The named producer of T3.11. Compared exactly: a rate without the source
    we declared is a rate from somewhere nobody reviewed."""

    availability_max_age_s: int = Field(default=300, gt=0)
    """How old the observation may be **at the instant we could act on it**.
    Five minutes: the opening is a single auditable act, and a wallet must not
    be converted at a rate that stopped being reachable a quarter of an hour
    ago. Measured on ``available_at``."""

    observation_max_age_s: int = Field(default=600, gt=0)
    """How old the *quote itself* may be. Ten minutes, a second and separate
    limit (Astra, T3.3 policy review, answer 3): without it a backfill that
    arrives now turns an hour-old quote into a fresh one, because its
    ``available_at`` is honest and its ``observed_at`` is not recent."""

    plausible_rate_min: Decimal = Decimal("1")
    plausible_rate_max: Decimal = Decimal("100")
    """The declared, versioned plausibility band for ``USDTBRL`` (adversarial
    review of ``8a6a69f``, blocking 3). The real has never traded outside
    ``[1, 100]`` per dollar since the Plano Real (1994); a collector's scale
    error (``0,54321`` typed for ``5,4321``) or an inverted quote lands outside
    it, while every true print since 1994 sits inside it. A ``rate`` of
    ``1e-10`` credits ``10**15`` USDT for R$100.000 with the money CHECK
    closing and the anchor immutable the instant it is written (D7) — this
    band is what refuses that before anything is credited. Declared as fields
    of the policy, never as a literal in the validator, so widening or
    narrowing it is a reviewed change to a named object, not a magic number a
    caller stumbled on."""

    max_relative_deviation: Decimal | None = Decimal("0.20")
    """Refuse an observation more than this fraction away from the last
    **accepted** one, when that last one is itself no older than
    :attr:`max_deviation_window_s`. ``None`` disables the comparison — the
    opening of the very first wallet has no prior accepted observation, and a
    caller with nothing to compare against passes ``last_accepted=None`` rather
    than disabling the policy for everyone. The comparison only ever applies
    when ``last_accepted`` shares this policy's pair and source, was observed
    strictly before ``observation`` and was itself already available at
    ``as_of`` — a replay must not change its verdict because a *later* accepted
    reading became known in the meantime (Astra, follow-up on the adversarial
    review of ``8a6a69f``)."""

    max_deviation_window_s: int = Field(default=600, gt=0)
    """How recent the last accepted observation must be for
    :attr:`max_relative_deviation` to apply. Ten minutes: past that, a genuine
    market move can plausibly explain 20%, and comparing against a stale
    anchor would refuse a good quote instead of a bad one."""


PAPER_FX_POLICY = FxPolicy()
"""The policy the paper wallet opens under."""


class FxObservationRejected(Exception):
    """The observation may not open a wallet. Carries the reason, for the audit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def validate_fx_observation(
    observation: FxObservation,
    *,
    as_of: datetime,
    policy: FxPolicy = PAPER_FX_POLICY,
    last_accepted: FxObservation | None = None,
) -> None:
    """Raise :class:`FxObservationRejected` unless ``observation`` may open a wallet.

    Pure and clock-free: ``as_of`` is the instant of the act, passed in, so a
    replay decides the same way the original did. ``last_accepted``, when
    given, is the previous observation this same policy already approved; it
    is optional because the very first observation of a fresh series has none
    to compare against (adversarial review of ``8a6a69f``, blocking 3).
    """
    moment = ensure_utc(as_of)
    if observation.pair != policy.pair:
        raise FxObservationRejected(
            f"pair {observation.pair!r} is not the declared {policy.pair!r}"
        )
    if observation.source != policy.source:
        raise FxObservationRejected(
            f"source {observation.source!r} is not the declared {policy.source!r}"
        )
    if observation.rate <= 0:
        raise FxObservationRejected(f"rate {observation.rate} is not positive")
    if not (policy.plausible_rate_min <= observation.rate <= policy.plausible_rate_max):
        raise FxObservationRejected(
            f"rate {observation.rate} is outside the plausible band "
            f"[{policy.plausible_rate_min}, {policy.plausible_rate_max}] declared for "
            f"{policy.pair}"
        )
    if (
        last_accepted is not None
        and policy.max_relative_deviation is not None
        and last_accepted.rate > 0
        and last_accepted.pair == policy.pair
        and last_accepted.source == policy.source
        and ensure_utc(last_accepted.observed_at) < ensure_utc(observation.observed_at)
        and ensure_utc(last_accepted.available_at) <= moment
    ):
        elapsed = (
            ensure_utc(observation.observed_at) - ensure_utc(last_accepted.observed_at)
        ).total_seconds()
        if elapsed <= policy.max_deviation_window_s:
            deviation = abs(observation.rate - last_accepted.rate) / last_accepted.rate
            if deviation > policy.max_relative_deviation:
                raise FxObservationRejected(
                    f"rate {observation.rate} deviates {deviation:.2%} from the last accepted "
                    f"{last_accepted.rate} observed {elapsed:.0f}s ago, over the "
                    f"{policy.max_relative_deviation:.0%} the policy allows within "
                    f"{policy.max_deviation_window_s}s"
                )

    observed_at = ensure_utc(observation.observed_at)
    available_at = ensure_utc(observation.available_at)
    if observed_at > available_at:
        raise FxObservationRejected(
            f"observed_at {observed_at.isoformat()} is ahead of available_at "
            f"{available_at.isoformat()}"
        )
    if available_at > moment:
        raise FxObservationRejected(
            f"available_at {available_at.isoformat()} is ahead of the opening "
            f"{moment.isoformat()}: the rate had not reached us yet"
        )
    availability_age = (moment - available_at).total_seconds()
    if availability_age > policy.availability_max_age_s:
        raise FxObservationRejected(
            f"available_at is {availability_age:.0f}s old, over the "
            f"{policy.availability_max_age_s}s the policy allows"
        )
    observation_age = (moment - observed_at).total_seconds()
    if observation_age > policy.observation_max_age_s:
        raise FxObservationRejected(
            f"observed_at is {observation_age:.0f}s old, over the "
            f"{policy.observation_max_age_s}s the policy allows"
        )
