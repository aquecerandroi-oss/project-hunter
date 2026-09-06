"""Feature engine (T2.2): hot state -> ``MarketContext`` -> ``FeatureVector``.

Read ``.claude/state/notes-T2.2.md`` for the frozen decisions (units, ``_live``
rule, ATR origin, what ``relative_volume_*`` means and what it does not).
"""

from hunter_indicators.features.atr import (
    ATR_METHOD,
    ATR_ORIGIN,
    ATR_PERIOD,
    AtrCheckpoint,
    advance_from_context,
    atr_percent,
)
from hunter_indicators.features.context import (
    INPUT_BOOK,
    INPUT_CANDLES,
    INPUT_DERIV_HISTORY,
    INPUT_FORMING,
    INPUT_FUNDING,
    INPUT_MARK,
    INPUT_OI,
    INPUT_TRADES,
    BookSnapshot,
    DerivObservation,
    DerivSnapshot,
    MarketContext,
    SourceEntry,
    TapeTrade,
    build_context,
)
from hunter_indicators.features.definitions import (
    LIVE_SUFFIX,
    FeatureCalculator,
    FeatureDefinition,
    FeatureRegistry,
    feature_set_version,
)
from hunter_indicators.features.engine import (
    DEFAULT_REGISTRY,
    FeatureResult,
    compute_features,
    default_calculators,
    default_definitions_rows,
)
from hunter_indicators.features.hotstate import HotStateRaw, load_context, read_hot_state
from hunter_indicators.features.quality import (
    QUALITY_POLICY_VERSION,
    FreshnessPolicy,
    provenance_for,
)
from hunter_indicators.features.state import EMPTY_STATE, FeatureState
from hunter_indicators.features.vector import (
    FeatureValue,
    FeatureVector,
    InputProvenance,
    Quality,
    Reason,
)

__all__ = [
    "ATR_METHOD",
    "ATR_ORIGIN",
    "ATR_PERIOD",
    "DEFAULT_REGISTRY",
    "EMPTY_STATE",
    "INPUT_BOOK",
    "INPUT_CANDLES",
    "INPUT_DERIV_HISTORY",
    "INPUT_FORMING",
    "INPUT_FUNDING",
    "INPUT_MARK",
    "INPUT_OI",
    "INPUT_TRADES",
    "LIVE_SUFFIX",
    "QUALITY_POLICY_VERSION",
    "AtrCheckpoint",
    "BookSnapshot",
    "DerivObservation",
    "DerivSnapshot",
    "FeatureCalculator",
    "FeatureDefinition",
    "FeatureRegistry",
    "FeatureResult",
    "FeatureState",
    "FeatureValue",
    "FeatureVector",
    "FreshnessPolicy",
    "HotStateRaw",
    "InputProvenance",
    "MarketContext",
    "Quality",
    "Reason",
    "SourceEntry",
    "TapeTrade",
    "advance_from_context",
    "atr_percent",
    "build_context",
    "compute_features",
    "default_calculators",
    "default_definitions_rows",
    "feature_set_version",
    "load_context",
    "provenance_for",
    "read_hot_state",
]
