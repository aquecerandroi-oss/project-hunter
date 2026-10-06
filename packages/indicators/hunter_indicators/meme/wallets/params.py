"""Frozen parameters of the wallet engine (H-030) and their registered definitions.

Every number below is the design's (``docs/design/seguir-carteiras-lucrativas.md``
§1, §1.1, §3) or the pre-registration's (``.claude/state/carteiras-lucro/PREREG.md``).
Changing any of them is a **new version** and, per the PREREG, a new hypothesis id
on new data — never an edit of these defaults.

Two parameters are engine assumptions the design does not fix; they are named
here so a reader can find them: :attr:`RankingParams.settle_seconds` (how long
after a slot its events are considered all received) and
:attr:`FollowPolicy.slot_seconds` (the nominal clock, see :mod:`.clock`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.canonical import params_hash
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "C_PNL_DEFINITION",
    "E_PNL_DEFINITION",
    "RANK_DEFINITION",
    "W_PNL_DEFINITION",
    "FollowPolicy",
    "NonFiniteParameter",
    "RankingParams",
    "manifest_hash",
]

SOL: Final = 1_000_000_000


class NonFiniteParameter(ValueError):
    """A Decimal parameter is NaN/sNaN/±Infinity: it prices nothing and makes comparisons raise
    or go silently false by the ambient Decimal traps (Astra, step-2 review)."""

    def __init__(self, owner: str, field: str, value: Decimal) -> None:
        super().__init__(f"{owner}.{field} must be a finite Decimal, got {value!r}")
        self.field = field


def _finite(params: object) -> None:
    for f in fields(params):  # type: ignore[arg-type]  # a dataclass instance
        value = getattr(params, f.name)
        if isinstance(value, Decimal) and not value.is_finite():
            raise NonFiniteParameter(type(params).__name__, f.name, value)


@dataclass(frozen=True, slots=True)
class FollowPolicy:
    """The copy policy — the `follow` arm **and** the C-PnL of the ranking (§1.3, §3)."""

    version: int = 1
    delay_slots: int = 5
    """Base scenario (p75 of 62 real buys, KB-0182); the stress run uses 13."""
    decision_seconds: Decimal = Decimal("0.4")
    slot_seconds: Decimal = Decimal("0.4")
    min_trigger_lamports: int = SOL // 10
    create_block_slots: int = 2
    budget_lamports: int = SOL // 20
    exit_sold_fraction: Decimal = Decimal("0.5")
    stop_fraction: Decimal = Decimal("0.5")
    time_cap_seconds: int = 3600
    network_leg_lamports: int = 50_000
    ata_close_lamports: int = 5_000
    ata_rent_lost_lamports: int = 0
    """Sensitivity only (rent lost instead of recovered); 0 in the primary."""
    r_unit: Decimal = Decimal("0.5")
    censored_r: Decimal = Decimal(-1)
    max_bets_per_entity_day: int = 20
    mint_cooldown_seconds: int = 1800

    def __post_init__(self) -> None:
        _finite(self)


@dataclass(frozen=True, slots=True)
class RankingParams:
    """Eligibility, exclusions and the top-N of a daily snapshot (§1, §1.1)."""

    version: int = 1
    window_days: int = 7
    top_n: int = 30
    min_episodes: int = 20
    min_mints: int = 15
    min_active_days: int = 4
    neutral_fraction: Decimal = Decimal("0.01")
    min_e_pnl_lamports: int = 2 * SOL
    min_positive_days: int = 4
    drawdown_floor_lamports: int = SOL
    drawdown_fraction: Decimal = Decimal("0.5")
    max_episode_fraction: Decimal = Decimal("0.5")
    min_median_hold_seconds: int = 60
    short_hold_seconds: int = 10
    max_short_hold_share: Decimal = Decimal("0.25")
    max_unmatched_share: Decimal = Decimal("0.2")
    max_creator_share: Decimal = Decimal("0.2")
    max_create_block_share: Decimal = Decimal("0.3")
    mev_slots: int = 2
    create_block_slots: int = 2
    min_h2_entities: int = 10
    """§3.2: fewer eligible entities outside the top than this → H2 unsupported that day."""
    max_trades_previous_day: int = 500
    settle_seconds: int = 2
    """Engine assumption: a slot is settled (all its events received) 2 s after the
    cut; the PREREG drops a day whose ``received_at − block_time`` p50 exceeds 2 s."""

    def __post_init__(self) -> None:
        _finite(self)


def manifest_hash(policy: FollowPolicy, ranking: RankingParams) -> str:
    """Canonical hash of both parameter sets — goes into every snapshot manifest."""
    return params_hash({"follow": asdict(policy), "ranking": asdict(ranking)})


_INPUTS = (
    "meme_wallet_fills",
    "meme_wallet_lots",
    "meme_wallet_links",
    "solana_rpc_ws.pump.create_event",
)

W_PNL_DEFINITION: Final = FeatureDefinition(
    key="wallet_w_pnl_lamports",
    version=1,
    category=FeatureCategory.MICROSTRUCTURE,
    inputs=_INPUTS,
    description="Realized FIFO PnL per entity over the window, net of event fees and 5 000 lamports/tx.",
    params={"window_days": 7, "tx_fee_lamports": 5_000},
)
E_PNL_DEFINITION: Final = FeatureDefinition(
    key="wallet_e_pnl_lamports",
    version=1,
    category=FeatureCategory.MICROSTRUCTURE,
    inputs=_INPUTS,
    description=(
        "Window cash flows (matched only) + liquidation value of the inventory at the end − at the "
        "start; liquidation = full sale against the valid state, real-SOL ceiling, 0 without state."
    ),
    params={"window_days": 7, "tx_fee_lamports": 5_000},
)
C_PNL_DEFINITION: Final = FeatureDefinition(
    key="wallet_c_pnl_lamports",
    version=1,
    category=FeatureCategory.MICROSTRUCTURE,
    inputs=_INPUTS,
    description="Sum of the follow policy's net lamports over the entity's complete simulated copies.",
    params={"delay_slots": 5, "budget_lamports": SOL // 20, "time_cap_seconds": 3600},
)
RANK_DEFINITION: Final = FeatureDefinition(
    key="wallet_follow_rank",
    version=1,
    category=FeatureCategory.MICROSTRUCTURE,
    inputs=_INPUTS,
    description="Rank by C-PnL among eligible entities; top 30 followed; ties by entity hash.",
    params={"top_n": 30, "window_days": 7},
)
