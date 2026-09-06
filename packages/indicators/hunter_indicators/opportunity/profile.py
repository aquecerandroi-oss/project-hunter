"""The frozen roster: which feature each component reads, and how it is read.

``components_v1``. The columns of ``docs/PIPELINE.md`` §5 mapped onto the feature
set T2.2 actually publishes — and where the two differ, the gap is **declared**
(``not_implemented``) instead of being papered over with a feature that happens
to exist. Three gaps, all inherited and all recorded in ``.claude/state/
notes-T2.4.md``:

- Liquidity should read ``quote_volume_1h``, the top-25 depth and the spread; only
  the spread exists, so this build's liquidity component is a **spread-based**
  one and says so. It measures relative *tightening* against the market's own
  median, which is not a claim about absolute depth or about being able to
  execute (Astra, T2.4 design review, item 2);
- Derivatives should read ``liquidation_pressure_1h`` and an OI/price divergence;
  neither exists (the liquidation feed is not in ``MarketContext`` v1);
- Momentum should read an EMA ratio, which the T2.2 set does not publish.

``sell_pressure_5m`` is deliberately **not** an input: it is
``1 - buy_pressure_5m`` over the same window, and counting both would put the same
evidence in the average twice under two names (Astra, item 5).

Sides follow the meaning of the feature, not its convenience: ``spread_pct`` is a
``DOWN`` reading (a spread *below* its median is the unusual, useful event) and
volume is an ``UP`` one. Directions follow :class:`DirectionRule`.
"""

from __future__ import annotations

from types import MappingProxyType

from hunter_indicators.anomalies.severity import DetectorSide
from hunter_indicators.opportunity.model import (
    REASON_NOT_IMPLEMENTED,
    ComponentDefinition,
    ComponentInput,
    ComponentKind,
    DirectionRule,
)


def _input(
    feature: str,
    side: DetectorSide,
    direction: DirectionRule = DirectionRule.NONE,
    version: int = 1,
) -> ComponentInput:
    return ComponentInput(
        feature=feature, feature_version=version, side=side, direction_rule=direction
    )


_GAP = REASON_NOT_IMPLEMENTED

MOMENTUM = ComponentDefinition(
    name="momentum",
    kind=ComponentKind.MAD,
    transform="mad_piecewise_v1",
    description="how far and how fast the price is travelling, in ATR units",
    inputs=(
        _input("momentum_15m", DetectorSide.BOTH, DirectionRule.SIGN),
        _input("momentum_acceleration", DetectorSide.BOTH, DirectionRule.SIGN),
        _input("breakout_strength_20", DetectorSide.UP, DirectionRule.POSITIVE_LONG),
    ),
    not_implemented=MappingProxyType({"ema_ratio": _GAP}),
)

VOLUME = ComponentDefinition(
    name="volume",
    kind=ComponentKind.MAD,
    transform="mad_piecewise_v1",
    description="how unusual the traded volume is across three windows",
    inputs=(
        _input("relative_volume_5m", DetectorSide.UP),
        _input("relative_volume_15m", DetectorSide.UP),
        _input("relative_volume_1h", DetectorSide.UP),
        _input("volume_acceleration", DetectorSide.UP),
    ),
)

LIQUIDITY = ComponentDefinition(
    name="liquidity",
    kind=ComponentKind.MAD,
    transform="mad_piecewise_v1",
    description="spread-based liquidity: how tight the book is against its own median",
    inputs=(_input("spread_pct", DetectorSide.DOWN),),
    not_implemented=MappingProxyType({"quote_volume_1h": _GAP, "depth_top_25": _GAP}),
)

ORDER_FLOW = ComponentDefinition(
    name="order_flow",
    kind=ComponentKind.MAD,
    transform="mad_piecewise_v1",
    description="who is lifting the offers, and how fast the tape is printing",
    inputs=(
        _input("buy_pressure_5m", DetectorSide.BOTH, DirectionRule.FRACTION_HALF),
        _input("orderbook_imbalance_20", DetectorSide.BOTH, DirectionRule.SIGN),
        _input("trade_velocity_1m", DetectorSide.UP),
    ),
)

DERIVATIVES = ComponentDefinition(
    name="derivatives",
    kind=ComponentKind.MAD,
    transform="mad_piecewise_v1",
    description="open interest and funding against their own baselines",
    inputs=(
        _input("open_interest_change_1h", DetectorSide.BOTH),
        _input("open_interest_change_4h", DetectorSide.BOTH),
        _input("funding_rate", DetectorSide.BOTH),
        _input("funding_change_8h", DetectorSide.BOTH),
    ),
    not_implemented=MappingProxyType(
        {"liquidation_pressure_1h": _GAP, "oi_price_divergence": _GAP}
    ),
)

MARKET_REGIME = ComponentDefinition(
    name="market_regime",
    kind=ComponentKind.REGIME,
    transform="regime_compat_v1",
    description="whether the proposed side agrees with the regime pair",
)

ANOMALIES = ComponentDefinition(
    name="anomalies",
    kind=ComponentKind.ANOMALIES,
    transform="anomaly_stack_v1",
    description="the eligible active anomalies, strongest first and discounted",
)

AGENT_CONSENSUS = ComponentDefinition(
    name="agent_consensus",
    kind=ComponentKind.CONSENSUS,
    transform="agent_consensus_v1",
    description="agreeing agent signals — zero until M4, and weighted zero",
)

EXTERNAL_INTELLIGENCE = ComponentDefinition(
    name="external_intelligence",
    kind=ComponentKind.EXTERNAL,
    transform="none",
    description="registered with weight zero, as PIPELINE.md §5 requires",
)

COMPONENTS: tuple[ComponentDefinition, ...] = (
    AGENT_CONSENSUS,
    ANOMALIES,
    DERIVATIVES,
    EXTERNAL_INTELLIGENCE,
    LIQUIDITY,
    MARKET_REGIME,
    MOMENTUM,
    ORDER_FLOW,
    VOLUME,
)
"""Ordered by name: the decomposition is sorted, and so is the roster."""

_BY_NAME = {definition.name: definition for definition in COMPONENTS}


def component_for(name: str) -> ComponentDefinition:
    """The definition of ``name``; an unknown component raises."""
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"{name} is not a component of {COMPONENTS[0].name}'s profile") from exc


__all__ = ["COMPONENTS", "component_for"]
