"""The versioned policy of one run, read from ``opportunity_weights``.

Every threshold the scanner applies comes from the active weight vector, never
from a constant in this package: the joint M2 decision made the stage, status,
normalization and baseline-gate blocks versioned precisely so a decision can be
replayed against the numbers that produced it. A scanner that fell back to a
default would score with thresholds nobody published.

Refusing to start is therefore the right failure. There is no "sensible default"
for a gate that decides whether a market has enough history to be judged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.analysis import OpportunityWeights
from hunter_core.logging import get_logger
from hunter_indicators.anomalies import NormalizationConfig
from hunter_indicators.baselines import BaselineGate
from hunter_indicators.opportunity import StatusThresholds, WeightProfile
from hunter_indicators.regime import RegimeThresholds
from hunter_indicators.stage import StageThresholds

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

__all__ = ["Policy", "load_policy"]


class MissingWeightsError(RuntimeError):
    """No active ``opportunity_weights`` row: there is nothing to score with."""


@dataclass(frozen=True, slots=True)
class Policy:
    """Everything versioned, parsed once at startup."""

    version: str
    profile: WeightProfile
    normalization: NormalizationConfig
    gate: BaselineGate
    stage: StageThresholds
    status: StatusThresholds
    regime: RegimeThresholds

    @property
    def versions(self) -> dict[str, str]:
        return {
            "weights": self.version,
            "normalization": self.normalization.identity,
            "stage": self.stage.weights_version,
            "status": self.status.weights_version,
            "regime": self.regime.identity,
        }


async def load_policy(session: AsyncSession) -> Policy:
    """Parse the active weight vector into every threshold the run will use."""
    row = (
        (
            await session.execute(
                select(OpportunityWeights).where(OpportunityWeights.is_active.is_(True))
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise MissingWeightsError(
            "no active opportunity_weights row; refusing to score with unpublished thresholds"
        )
    weights: dict[str, Any] = dict(row.weights)
    policy = Policy(
        version=row.version,
        profile=WeightProfile.from_weights(weights, version=row.version),
        normalization=NormalizationConfig.from_weights(weights, version=row.version),
        gate=BaselineGate.from_weights(weights),
        stage=StageThresholds.from_weights(weights, version=row.version),
        status=StatusThresholds.from_weights(weights, version=row.version),
        regime=RegimeThresholds(),
    )
    logger.info("scanner_policy_loaded", **policy.versions)
    return policy
