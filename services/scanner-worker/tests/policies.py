"""The versioned policy of a test run -- the **shipped** v2 vector, not a fixture.

``infra/scripts/seed_reference.py`` is what a real database is seeded with, so
importing it here means the scanner is tested against the numbers it will
actually read. A hand-written weight dict in this file would let a test pass
against thresholds nobody published, which is precisely the failure
``load_policy`` refuses to allow in production.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from hunter_indicators.anomalies import NormalizationConfig
from hunter_indicators.baselines import BaselineGate
from hunter_indicators.opportunity import StatusThresholds, WeightProfile
from hunter_indicators.regime import RegimeThresholds
from hunter_indicators.stage import StageThresholds
from hunter_scanner_worker.policy import Policy

_SCRIPTS = Path(__file__).resolve().parents[3] / "infra" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seed_reference  # type: ignore[reportMissingImports]  # noqa: E402

_SHIPPED: Any = cast("Any", seed_reference).OPPORTUNITY_WEIGHTS_V2
"""``infra/scripts`` is not a typed package on the pyright path, so the boundary
is narrowed here rather than sprinkled through the tests."""

VERSION = "v2"


def build_policy() -> Policy:
    """The active policy as the seed publishes it."""
    weights: dict[str, Any] = dict(cast("dict[str, Any]", _SHIPPED))
    return Policy(
        version=VERSION,
        profile=WeightProfile.from_weights(weights, version=VERSION),
        normalization=NormalizationConfig.from_weights(weights, version=VERSION),
        gate=BaselineGate.from_weights(weights),
        stage=StageThresholds.from_weights(weights, version=VERSION),
        status=StatusThresholds.from_weights(weights, version=VERSION),
        regime=RegimeThresholds(),
    )
