"""``hunter_indicators.baselines`` — the robust reference every detector compares against.

Four layers, deliberately separate (Astra, T2.3 design review):

1. **computation** (``compute.py``) — pure median/MAD of one bucket, its counts
   and its ``input_fingerprint``;
2. **usability** (``revision.py``) — the versioned gate a *reader* applies to a
   stored revision, never a boolean frozen into the row;
3. **causal projection** (``projection.py``) — the revisions a consumer is
   allowed to see at one cut, validated once and carried by value so a detector
   stays a pure function;
4. **the port** (``store.py``, ``sql.py``) — append-only access to
   ``feature_baselines``, in memory for tests and over SQL in the scanner.

``bootstrap.py`` fills the archive from persisted candles with the **same** T2.2
calculators. Nothing here ever calls an exchange: the scanner is not a REST
client (``docs/plans/M2.md`` §REST).
"""

from hunter_indicators.baselines.bootstrap import (
    BOOTSTRAP_ALGO_VERSION,
    REASON_HISTORICAL_SOURCE_UNAVAILABLE,
    REASON_PARTIAL_CANDLE,
    REASON_SEMANTICS_UNPROVEN,
    BootstrapExclusion,
    BootstrapResult,
    bootstrap_exclusions,
    bootstrap_feature_keys,
    bootstrap_observations,
    bootstrap_revisions,
)
from hunter_indicators.baselines.collect import (
    ObservationCollector,
    ObservationRejection,
    observations_from_vector,
)
from hunter_indicators.baselines.compute import (
    compute_revision,
    input_fingerprint,
    median,
    median_absolute_deviation,
)
from hunter_indicators.baselines.projection import (
    REASON_NO_BASELINE,
    REASON_VERSION_MISMATCH,
    BaselineCut,
    BaselineLookup,
    BaselineProjection,
)
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    COVERAGE_QUANTUM,
    REASON_INSUFFICIENT_HISTORY,
    REASON_NO_OBSERVATIONS,
    STAT_QUANTUM,
    BaselineGate,
    BaselineKey,
    BaselineRevision,
    BaselineUnavailable,
    Observation,
    StoredBaseline,
    quantize_coverage,
    quantize_stat,
)
from hunter_indicators.baselines.sql import SqlBaselineStore, insert_revisions, select_projection
from hunter_indicators.baselines.store import (
    BaselineRequest,
    BaselineStore,
    InMemoryBaselineStore,
)

__all__ = [
    "ALGO_VERSION",
    "BOOTSTRAP_ALGO_VERSION",
    "COVERAGE_QUANTUM",
    "REASON_HISTORICAL_SOURCE_UNAVAILABLE",
    "REASON_INSUFFICIENT_HISTORY",
    "REASON_NO_BASELINE",
    "REASON_NO_OBSERVATIONS",
    "REASON_PARTIAL_CANDLE",
    "REASON_VERSION_MISMATCH",
    "REASON_SEMANTICS_UNPROVEN",
    "STAT_QUANTUM",
    "BaselineCut",
    "BaselineGate",
    "BaselineKey",
    "BaselineLookup",
    "BaselineProjection",
    "BaselineRequest",
    "BaselineRevision",
    "BaselineStore",
    "BaselineUnavailable",
    "BootstrapExclusion",
    "BootstrapResult",
    "InMemoryBaselineStore",
    "Observation",
    "ObservationCollector",
    "ObservationRejection",
    "SqlBaselineStore",
    "StoredBaseline",
    "bootstrap_exclusions",
    "bootstrap_feature_keys",
    "bootstrap_observations",
    "bootstrap_revisions",
    "compute_revision",
    "input_fingerprint",
    "insert_revisions",
    "median",
    "median_absolute_deviation",
    "observations_from_vector",
    "quantize_coverage",
    "quantize_stat",
    "select_projection",
]
