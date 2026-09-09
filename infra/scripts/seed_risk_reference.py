"""The four system risk profiles the seed writes — RISK_ENGINE.md §2.

One table's content, in one file: the three generic presets (their limit
vectors and the regime multipliers that ride along) and ``paper_v1``, the
wallet's own profile. ``seed.py``/``seed_dry_run.py`` build the first three from
:data:`RISK_PRESETS` × :data:`RISK_LIMITS` × :data:`REGIME_MULTIPLIERS`;
``seed_paper.py`` writes the fourth from :data:`PAPER_V1_LIMITS`.

Split out of ``seed_reference.py`` when T3.44c pushed that module past the
350-line budget (``infra/scripts/check_file_size.py``), along the seam it
already had — ``seed_reference`` keeps the catalogues (venues, strategies,
entitlements, flags, features) and the opportunity-weight profiles, and
``risk_profiles`` is neither. **``seed_reference`` re-exports all five names**,
so every existing import path (``from seed_reference import RISK_LIMITS``, and
the three test modules that load that file *by path* and read the attributes off
it) keeps working: a module split that breaks an import is a refactor that broke
something (DATABASE.md §18.10).

Data only: no queries, no connection, no side effects. Fractions are JSON
**strings**, never JSON numbers — a limit like ``0.0025`` has no exact binary
float and the Risk Engine reads these straight into ``Decimal``. Counts and
booleans stay native: they are integers, not measurements.
"""

from __future__ import annotations

from typing import Any

from hunter_core.domain.enums import RiskPreset
from hunter_risk.limits import PAPER_V1

RISK_LIMITS: dict[str, tuple[Any, Any, Any]] = {
    # key: (conservative, balanced, aggressive) — RISK_ENGINE.md §2
    "max_position_pct": ("0.02", "0.05", "0.10"),
    "risk_per_trade_pct": ("0.0025", "0.005", "0.01"),
    "max_total_exposure_pct": ("0.30", "0.60", "1.00"),
    "max_daily_loss_pct": ("0.01", "0.02", "0.04"),
    "max_drawdown_pct": ("0.05", "0.10", "0.20"),
    "max_concurrent_positions": (3, 6, 12),
    "max_asset_exposure_pct": ("0.05", "0.10", "0.20"),
    "max_exchange_exposure_pct": ("0.50", "0.70", "1.00"),
    "min_liquidity_usd_24h": ("50000000", "20000000", "5000000"),
    "max_spread_pct": ("0.0005", "0.001", "0.002"),
    "max_slippage_pct": ("0.001", "0.002", "0.005"),
    "max_leverage": (1, 2, 3),
    "max_correlated_positions": (2, 4, 8),
    "min_stop_distance_pct": ("0.003", "0.002", "0.001"),
    "max_stop_distance_pct": ("0.03", "0.05", "0.08"),
    "auto_close_on_emergency": (False, False, False),
}

REGIME_MULTIPLIERS: tuple[dict[str, str], ...] = (
    # RISK_ENGINE.md §2 grammar: `<REGIME>` or `<REGIME>_<DIRECTION>`, where
    # <REGIME> is a `market_regime` label and <DIRECTION> is a `trade_direction`
    # upper-cased. The engine looks up `<REGIME>_<DIRECTION>` first, then
    # `<REGIME>`, then falls back to 1.0 — so `BTC_BEAR_LONG` narrows longs in a
    # bear market while `HIGH_VOLATILITY` applies to both directions.
    {"BTC_BEAR_LONG": "0.5", "HIGH_VOLATILITY": "0.7"},
    {"BTC_BEAR_LONG": "0.5", "HIGH_VOLATILITY": "0.7"},
    {"HIGH_VOLATILITY": "0.85"},
)

RISK_PRESETS: tuple[tuple[RiskPreset, str], ...] = (
    (RiskPreset.CONSERVATIVE, "Conservative"),
    (RiskPreset.BALANCED, "Balanced"),
    (RiskPreset.AGGRESSIVE, "Aggressive"),
)


PAPER_V1_NAME = "Paper v1"

PAPER_V1_LIMITS: dict[str, Any] = PAPER_V1.model_dump(mode="json")
"""The wallet's profile - **derived from the engine, never retyped**.

Until the security review of ``0006_paper_wallet`` this was a second literal
next to ``hunter_risk.limits.PAPER_V1``, and the two had already drifted:
``RiskLimits.model_validate(profile.limits)`` failed with ten errors on the row
this seed writes. Six keys the engine requires were missing
(``max_entry_deviation_pct``, ``max_price_age_s``, ``max_book_age_s``,
``max_volume_age_s``, ``max_beta_age_s``, ``day_timezone``), so the ceilings the
v2.1 contract added existed only in code and never in the profile an
organization copies at onboarding; and four keys the engine has no field for
were present, which ``extra="forbid"`` rejects.

``model_dump(mode="json")`` rather than a hand-written mirror: pydantic renders
every ``Decimal`` as a JSON **string**, which is the rule this module already
follows for the weight vectors - the Risk Engine reads these straight back into
``Decimal``, and a JSON number has no exact binary form for 0.0025. **No value
of the directive changes**; the numbers are the ones in
``.claude/state/directive-risk-engine-2026-09-06.md``, and now there is one
place they are written down.

``max_exchange_exposure_pct`` and ``max_position_pct`` remain deliberately
**absent**: RISK_ENGINE.md §9.1 declares the first inapplicable while there is
one execution venue (it returns in M1b) and replaces the second with
``max_asset_exposure_pct`` plus the participation ceiling. Recording them as
``null`` would read as "no limit" rather than "not applicable here".

Four keys the old literal carried go with it, and each is declared rather than
dropped in silence (DATABASE.md §18.8): ``participation_reference`` is a formula
the engine computes from ``MarketLiquidity`` and never read from here;
``market_types: ["spot"]`` is what ``max_leverage = 1`` already means, kept true
by ``RiskLimits``' own validator; ``auto_close_on_emergency: false`` is the
absence of an automatic-liquidation path in ``hunter_risk.kill_switch``, not a
switch anything reads; and ``regime_size_multiplier`` names the v1 grammar of
RISK_ENGINE.md §2.1 that the M3 engine **does not implement** - carrying it in
the profile made an unimplemented control look configured.
"""
