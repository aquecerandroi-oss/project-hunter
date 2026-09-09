"""The reference data ``seed.py`` writes — DATABASE.md, PRODUCT.md §5,
RISK_ENGINE.md §2, PIPELINE.md §2 and §5.

Data only: no queries, no connection, no side effects. It moved out of
``seed.py`` when T2.1 added the M2 feature catalogue and the v2 weight profile
and the script went past the 350-line budget
(``infra/scripts/check_file_size.py``); splitting the *content* from the
*upserts* keeps each half readable and means a review of "what do we ship as
reference data" reads one file.

Two entries are **not** literals, on purpose. The feature catalogue is derived
from the ``hunter_indicators`` registry (:func:`feature_definition_rows`), which
is the only copy that also computes the numbers; and :data:`PAPER_V1_LIMITS` is
``hunter_risk.limits.PAPER_V1`` dumped, which is the only copy the Risk Engine
actually decides by. Both were second literals once, and both had drifted from
their originals before anyone looked.

The four **risk profiles** moved to the sibling :mod:`seed_risk_reference` in
T3.44c, when the ``planned`` venue label pushed this file past the budget again:
``risk_profiles`` is one table's content and the seam was already there. The five
names it owns (``RISK_LIMITS``, ``REGIME_MULTIPLIERS``, ``RISK_PRESETS``,
``PAPER_V1_NAME``, ``PAPER_V1_LIMITS``) are **re-exported above**, so every
caller keeps its import — including the three test modules that load *this* file
by path and read the attributes off it (DATABASE.md §18.10).

Fractions are JSON **strings**, never JSON numbers: a limit like ``0.0025`` has
no exact binary float and the Risk Engine and the scorer read these straight
into ``Decimal``. Counts, periods and booleans stay native — they are integers,
not measurements.

``seed.py`` imports this as a sibling module. Both are run as scripts from
``infra/scripts`` (``entrypoint.sh``, ``uv run python infra/scripts/seed.py``),
so the interpreter puts this directory on ``sys.path`` itself; the integration
test that loads ``seed.py`` by path does the same explicitly.
"""

from __future__ import annotations

from typing import Any

from seed_risk_reference import PAPER_V1_LIMITS as PAPER_V1_LIMITS
from seed_risk_reference import PAPER_V1_NAME as PAPER_V1_NAME
from seed_risk_reference import REGIME_MULTIPLIERS as REGIME_MULTIPLIERS
from seed_risk_reference import RISK_LIMITS as RISK_LIMITS
from seed_risk_reference import RISK_PRESETS as RISK_PRESETS

from hunter_core.domain.enums import ExchangeStatus
from hunter_indicators.features import default_definitions_rows

_CAPABILITIES = {
    "spot": True,
    "perpetual": True,
    "funding": True,
    "open_interest": True,
    "liquidations": True,
    "ws_depth": True,
}

EXCHANGES: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("binance", "Binance", ExchangeStatus.ACTIVE.value, _CAPABILITIES),
    ("bybit", "Bybit", ExchangeStatus.PLANNED.value, _CAPABILITIES),
)  # (code, name, status, capabilities) — status per row, never the column default (§28)

STRATEGIES: tuple[tuple[str, str, str, str], ...] = (
    ("momentum", "Momentum", "trend", "Continuation with relative volume and breakout strength."),
    (
        "breakout",
        "Breakout",
        "trend",
        "Breakout of the previous highs after a contraction of true range, confirmed by volume.",
    ),
    ("volume_anomaly", "Volume Anomaly", "anomaly", "Entry after a VOLUME_SPIKE with pressure."),
    ("order_flow", "Order Flow", "microstructure", "Book imbalance and taker pressure."),
    (
        "mean_reversion",
        "Mean Reversion",
        "reversion",
        "Pullback bought inside a higher-timeframe uptrend, on a close stretched below its mean.",
    ),
    (
        "mean_reversion_h1",
        "Mean Reversion 1h",
        "reversion",
        "The same pullback, decided on 1h bars: the ATR% of a 1h bar is 2.2x that "
        "of a 15m bar on the same market, so the assumed toll per R is 2.2x smaller. "
        "Needs >= 5820 min of candle context (SHADOW_CONTEXT_MINUTES / T3.54b); "
        "with the 1560 default it only ever answers atr_warmup.",
    ),
    ("derivatives", "Derivatives", "derivatives", "Funding, open interest and liquidation setups."),
    (
        "session_orb",
        "Session ORB",
        "trend",
        "Breakout of the opening range of a declared UTC session, confirmed by volume.",
    ),
    ("trendline_breakout", "Trendline Breakout", "trend", "Break of a drawn trend line."),
    (
        "sweep_reclaim",
        "Sweep and Reclaim",
        "reversion",
        "Long a bar that pierces a confirmed swing low and closes back above it, "
        "on above-median volume.",
    ),
    ("narrative", "Narrative", "intelligence", "Narrative and news driven flow (Phase 2)."),
    ("ensemble", "Ensemble", "meta", "Weighted combination of the other strategies."),
)

ENTITLEMENTS: dict[str, tuple[Any, Any, Any, Any]] = {
    # key: (FREE, PRO, QUANT, ENTERPRISE) — ``None`` means unlimited
    "max_agents": (2, 8, 30, None),
    "max_exchanges": (2, 4, 8, None),
    "max_portfolios": (1, 5, 20, None),
    "market_history_days": (30, 180, 730, None),
    "backtesting": (False, True, True, True),
    "advanced_intelligence": (False, False, True, True),
    "custom_agent_params": (False, True, True, True),
    "live_trading": (False, False, True, True),
    "api_access": (False, True, True, True),
}

FEATURE_FLAGS: tuple[tuple[str, str], ...] = (
    ("ENABLE_LIVE_TRADING", "Live execution. Stays off until Phase 4."),
    ("ENABLE_SOCIAL_INTELLIGENCE", "Social sources for the intelligence pipeline."),
    ("ENABLE_ONCHAIN", "On-chain sources for the intelligence pipeline."),
    ("ENABLE_STRIPE", "Billing through Stripe."),
    ("ENABLE_LLM_ANALYSIS", "LLM classification of external content."),
    ("ENABLE_ARENA", "Agent Arena."),
    ("ENABLE_BACKTESTS", "Backtest engine and UI."),
)


def feature_definition_rows() -> list[dict[str, Any]]:
    """The v1 feature catalogue, **derived from the engine** — not retyped here.

    ``hunter_indicators`` is the source of truth: its registry is what computes
    the numbers, and ``feature_snapshots.feature_set_version`` is a hash of the
    very identities ``as_row()`` returns (key, version, category, inputs,
    parameters). Two hand-kept lists cannot agree, and did not: this module used
    to ship ``volatility``/``volume_relative`` reading ``candles_1m``/``book_20``
    while the engine published ``atr_14_pct``/``relative_volume_5m`` reading
    ``candles:1m``/``book:20`` — 20 of 28 keys orphaned on one side or the other,
    which would have made every row of this table describe an engine nobody ran.

    ``parameters`` therefore comes from the calculators too, canonicalised (a
    number is a JSON *string*, as everywhere else here). ``seed.py`` adds the
    ``id``. Each call returns fresh dicts, so a caller may adapt one in place.

    The import is safe wherever the seed runs: ``hunter-indicators`` is a
    workspace member (root ``pyproject.toml``), ``uv sync --all-packages``
    installs it into the image venv, and ``Dockerfile.api-workers`` copies
    ``packages/indicators`` — the same image serves ``HUNTER_COMMAND=migrate``
    and ``HUNTER_COMMAND=seed``.
    """
    return default_definitions_rows()


OPPORTUNITY_WEIGHTS_V1: dict[str, Any] = {
    # The MVP vector of PIPELINE.md §5, flat, summing to 1.00 with Agent
    # Consensus at 0.05. Kept exactly as ``0001``-era deploys seeded it: it is
    # history, and a version whose content changes cannot explain a score that
    # named it.
    "momentum": "0.20",
    "volume": "0.20",
    "liquidity": "0.10",
    "order_flow": "0.15",
    "derivatives": "0.10",
    "market_regime": "0.10",
    "anomalies": "0.10",
    "agent_consensus": "0.05",
    "external_intelligence": "0.00",
}

OPPORTUNITY_WEIGHTS_V2: dict[str, Any] = {
    # The M2 profile of the joint Claude/Astra decision. Nested rather than flat
    # because the decision puts the stage thresholds under
    # ``weights["stage"]`` — "versionados, nunca hardcoded" — and a flat map
    # could not tell a component weight from a threshold. v1 stays flat; the
    # shape is read per version, never guessed.
    "profile": "M2",
    "components_frozen": False,
    "components": {
        # Sum exactly 0.90; the remaining 0.10 of the budget is the signed
        # Early-Movement term below. ``agent_consensus`` is 0.00 by the joint
        # decision (no agent emits before M4) and returns as v3 in M4.
        #
        # **T2.4 ratified these numbers unchanged** (2026-09-06): the scorer that
        # reads them is the one that was just built, and it found no reason to
        # move a weight that no historical study supports either way. The vector
        # is v1's, with agent_consensus zeroed and the remaining 0.05 taken from
        # ``anomalies`` — the component whose signal is already counted twice in
        # M2 (it drives the ANOMALY status and the EARLY confirmations). It stays
        # **policy, not calibration**: the first weeks of real scores (EXP-0003)
        # are what a v3 would be built on, and the M4 profile is where
        # ``agent_consensus`` stops being zero.
        #
        # ``components_frozen`` **stays false here on purpose.** Flipping it is a
        # coordinated two-file change and T2.4 owns only this one: the seed
        # refuses to rewrite a published vector (``seed_weights.py``), and
        # ``packages/core/tests/integration/test_schema_seed_and_partitions.py``
        # ::test_the_seed_refuses_to_rewrite_a_published_weight_vector uses
        # exactly this flip as its *divergence fixture* — shipping ``true`` makes
        # that test's UPDATE a no-op and turns it red, and its ``_reset_shipped_
        # weights`` then drags the next test down with it. What T2.4 does freeze
        # is mechanical anyway: ``packages/indicators/tests/unit/
        # test_weights_contract.py::TestT24RatifiedTheV2Vector`` pins every number
        # of this block, so a silent edit fails a test either way.
        "momentum": "0.20",
        "volume": "0.20",
        "order_flow": "0.15",
        "liquidity": "0.10",
        "derivatives": "0.10",
        "market_regime": "0.10",
        "anomalies": "0.05",
        "agent_consensus": "0.00",
        "external_intelligence": "0.00",
    },
    "early_movement": {
        # score = clip(sum(w_i * c_i) + magnitude * e, 0, 100), e in {-1, 0, +1}
        "magnitude": "10",
        "values": [-1, 0, 1],
    },
    "normalization": {
        # d = (x - median) / MAD, piecewise: flat to 1 MAD, linear to 100 at
        # 6 MADs, saturated above. Direction is carried separately.
        "method": "mad_piecewise_v1",
        "deadband_mad": "1",
        "saturation_mad": "6",
        "saturation_score": "100",
    },
    "stage": {
        # r = |return_1h| / atr_pct, both fractions.
        "r_early_max": "1.5",
        "r_developing_max": "4",
        "relative_volume_1h_min": "3",
        "trade_velocity_baseline_multiple_min": "2",
        "open_interest_change_1h_min": "0.02",
        "buy_pressure_5m_long_min": "0.60",
        "buy_pressure_5m_short_max": "0.40",
        "extended_return_4h_atr_multiple": "3",
        "extended_relative_volume_15m_declines": 3,
        "extended_relative_volume_15m_closes": 4,
        "confirmations": 2,
        "atr_period": 14,
        "atr_bar_minutes": 15,
    },
    "status": {
        # PIPELINE.md §5. ENTRY_CANDIDATE stays unreachable until M4 supplies an
        # agreeing agent signal.
        "watching_min": "40",
        "hot_min": "75",
        "entry_candidate_min": "80",
        "anomaly_severity_min": "60",
    },
    "expiry": {
        "score_floor": "40",
        "below_floor_minutes": 15,
    },
    "baseline_gate": {
        "min_distinct_days": 3,
        "min_valid_observations": 120,
        "expected_size": 420,
    },
    "precision": {
        "score_decimals": 2,
        "confidence_decimals": 4,
        "component_decimals": 4,
        "rounding": "ROUND_HALF_EVEN",
    },
}

OPPORTUNITY_WEIGHTS: tuple[tuple[str, dict[str, Any], str], ...] = (
    (
        "v1",
        OPPORTUNITY_WEIGHTS_V1,
        "MVP component weights for the opportunity score "
        "(PIPELINE.md §5). Retired by v2; kept for the scores that name it.",
    ),
    (
        "v2",
        OPPORTUNITY_WEIGHTS_V2,
        "M2 profile: components sum 0.90, Agent Consensus 0, "
        "signed Early-Movement +/-10, stage/status/normalization thresholds versioned. "
        "Component weights ratified unchanged by T2.4 (2026-09-06); the frozen flag "
        "waits for the coordinated change described in the vector above.",
    ),
)

ACTIVE_WEIGHTS_VERSION = "v2"
"""The profile this release ships as active."""

PROMOTED_FROM: tuple[str, ...] = ("v1",)
"""Versions the seed may retire when it first creates :data:`ACTIVE_WEIGHTS_VERSION`.

The promotion happens **once**, on the run that creates the v2 row, and never
again — which is what keeps ``test_reseeding_never_reactivates_a_retired_weight
_version`` true. An operator who later rolls back to another profile keeps it,
because v2 already exists by then. And a version outside this tuple is never
demoted: if some future v3 is live and v2 has been deleted, the seed recreates
v2 inactive rather than taking the live profile away from a running scorer.
"""
