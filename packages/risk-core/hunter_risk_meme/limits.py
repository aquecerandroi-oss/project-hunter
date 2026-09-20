"""``MemeLimits`` — the wallet policy of ``docs/RISK_ENGINE_MEME.md`` §3.1, and where it comes from.

Two families of number, two owners (§3): the **capital policy** (how much may be
lost — the five ``MEME_*`` variables below, Everton's alone) and the **strategy
parameters** (what is believed about the market — the paper preset, revisable by
evidence). :data:`MEME_PAPER_V0` carries the paper column of §3.1 as defaults for
the strategy parameters and the paper values for the policy; :func:`limits_from_env`
builds the **live** profile by reading the five policy variables from the
environment and refuses — :class:`MemePolicyMissing`, every missing or malformed
name listed — when any of them is absent. The executor calls it only with the live
flag on: paper never needs a policy from the environment.

T4.58: the **curve-progress window** (``0.02``–``0.50`` in the paper column) may be
overridden by ``MEME_CURVE_PROGRESS_MIN_PCT`` / ``MEME_CURVE_PROGRESS_MAX_PCT`` so the
owner can align the admission with the desk gate (``operator/5`` ``max_progress_pct``)
— absent keeps the base's values; unreadable or empty refuses the boot by name.
T4.61c: the live floor ``MEME_MIN_TRADE_SOL`` (:data:`LIVE_MIN_TRADE_SOL`) is optional too.
T4.78: ``MEME_MINT_COOLDOWN_AFTER_LOSS_S`` (check 28, 300 s by default, ``0`` disables).
The parsers of every optional variable live in :mod:`hunter_risk_meme.limits_env`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from pydantic import Field, model_validator

from hunter_risk_meme.base import MemeModel
from hunter_risk_meme.limits_env import (
    DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S,
    ENV_CREATOR_UNKNOWN_ALLOWED,
    ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE,
    ENV_CURVE_PROGRESS_MAX,
    ENV_CURVE_PROGRESS_MIN,
    ENV_MIN_TRADE_SOL,
    ENV_MINT_COOLDOWN_AFTER_LOSS,
    LIVE_MIN_TRADE_SOL,
    creator_unknown_allowance,
    curve_progress_window,
    min_trade_sol,
    mint_cooldown_after_loss_s,
    parse_decimal,
)

# fmt: off
__all__ = [
    "ENV_CREATOR_UNKNOWN_ALLOWED", "ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE", "ENV_CURVE_PROGRESS_MAX",
    "ENV_CURVE_PROGRESS_MIN", "ENV_MINT_COOLDOWN_AFTER_LOSS", "ENV_MIN_TRADE_SOL",
    "LIVE_MIN_TRADE_SOL", "MEME_PAPER_V0", "POLICY_ENV", "MemeLimits", "MemePolicyMissing",
    "limits_from_env",
]
# fmt: on

POLICY_ENV: Final[tuple[str, ...]] = (
    "MEME_WALLET_MAX_SOL",
    "MEME_MAX_SOL_PER_TRADE",
    "MEME_DAILY_LOSS_CAP_SOL",
    "MEME_MAX_OPEN_POSITIONS",
    "MEME_COOLDOWN_S",
)
"""The five numbers only the owner writes (§3, "política de capital")."""


class MemePolicyMissing(RuntimeError):
    """The live flag is on and the wallet policy is incomplete: boot refusal, by name."""

    def __init__(
        self, missing: tuple[str, ...], invalid: tuple[str, ...] = (), detail: str = ""
    ) -> None:
        self.reason = "policy_missing"
        self.missing = missing
        self.invalid = invalid
        self.detail = detail
        parts = [f"missing={list(missing)}"] if missing else []
        if invalid:
            parts.append(f"invalid={list(invalid)}")
        if detail:
            parts.append(detail)
        super().__init__(f"{self.reason}: " + ", ".join(parts))


class MemeLimits(MemeModel):
    """§3.1 — the wallet profile. Fractions are ``Decimal`` fractions (``0.01`` = 1 %)."""

    profile: str = Field(min_length=1)
    # ---- capital policy (owner) --------------------------------------------
    wallet_max_sol: Decimal = Field(gt=0)
    max_sol_per_trade: Decimal = Field(gt=0)
    daily_loss_cap_sol: Decimal = Field(gt=0)
    max_open_positions: int = Field(ge=1)
    rug_cooldown_s: int = Field(ge=0)
    max_exposure_per_mint_sol: Decimal = Field(gt=0)
    max_participation_pct: Decimal = Field(gt=0, le=1)
    max_price_impact_pct: Decimal = Field(gt=0, lt=1)
    max_slippage_pct: Decimal = Field(gt=0, le=Decimal("0.5"))
    max_priority_fee_sol: Decimal = Field(ge=0)
    max_priority_fee_pct_of_trade: Decimal = Field(ge=0, le=1)
    max_jito_tip_sol: Decimal = Field(ge=0)
    # ---- strategy parameters (pre-registered hypothesis) --------------------
    token_age_min_s: int = Field(ge=0)
    token_age_max_s: int = Field(ge=1)
    curve_progress_min_pct: Decimal = Field(ge=0, le=1)
    curve_progress_max_pct: Decimal = Field(ge=0, le=1)
    max_bundled_share_pct: Decimal = Field(ge=0, le=1)
    max_top10_share_pct: Decimal = Field(ge=0, le=1)
    max_state_age_s: int = Field(ge=1)
    clock_skew_tolerance_s: int = Field(ge=0)
    min_commitment: Literal["confirmed", "finalized"] = "confirmed"
    reservation_ttl_s: int = Field(ge=1)
    target_multiple: Decimal = Field(gt=1)
    trailing_from_peak_pct: Decimal = Field(gt=0, lt=1)
    time_stop_s: int = Field(ge=1)
    # ---- kill switch (§7) ---------------------------------------------------
    warning_daily_loss_fraction: Decimal = Field(gt=0, lt=1)
    """WARNING at this fraction of the daily cap ("metade do teto diário", §7)."""
    warning_size_multiplier: Decimal = Field(gt=0, le=1)
    # ---- execution costs the sizing must cover (§5) -------------------------
    min_trade_sol: Decimal = Field(gt=0)
    """Below this a buy cannot pay its own fees and rent (check 23)."""
    network_fee_sol: Decimal = Field(ge=0)
    ata_rent_sol: Decimal = Field(ge=0)
    """Rent of the buyer's token account when it has to be created (§3.2)."""
    day_timezone: str = "America/Sao_Paulo"
    max_leverage: Literal[1] = 1
    quote: Literal["SOL"] = "SOL"
    # ---- the owner's allowance on check 10 (§4, T4.28h) ---------------------
    creator_unknown_allowed_if_dev_measured: bool = False
    """**Off** by default: an unknown creator flow refuses ``creator_flow_unknown``.
    On (``MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED``, the owner's decision
    alone) a **measured** ``dev_share_pct`` within
    :attr:`creator_unknown_max_dev_share_pct` lets the unknown creator pass — the
    same allowance the desk's ``operator/5`` gate already applies (E1 arm 2). It
    never rescues a *known* net seller."""
    creator_unknown_max_dev_share_pct: Decimal = Field(ge=0, le=1, default=Decimal("0.10"))
    """``MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT`` — the desk's 10 % by default."""
    # ---- repeated exposure on one mint (§4 check 28, T4.78) ------------------
    mint_cooldown_after_loss_s: int = Field(ge=0, default=DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S)
    """``MEME_MINT_COOLDOWN_AFTER_LOSS_S`` — after a live position on a mint closed
    with ``pnl_sol < 0``, no new buy on that mint for this many seconds; ``0``
    disables. Everton's decision (20/09/2026), applied as a limit on repeated
    exposure, **not** as a demonstrated edge — see ``checks_wallet.py`` for the
    evidence and the counter-example. Sells are never touched."""

    @model_validator(mode="after")
    def _coherent(self) -> MemeLimits:
        if self.max_sol_per_trade > self.wallet_max_sol:
            raise ValueError("max_sol_per_trade cannot exceed wallet_max_sol")
        if self.max_exposure_per_mint_sol > self.wallet_max_sol:
            raise ValueError("max_exposure_per_mint_sol cannot exceed wallet_max_sol")
        if self.curve_progress_min_pct >= self.curve_progress_max_pct:
            raise ValueError("curve_progress window is empty")
        if self.token_age_min_s >= self.token_age_max_s:
            raise ValueError("token_age window is empty")
        if self.min_trade_sol > self.max_sol_per_trade:
            raise ValueError("min_trade_sol cannot exceed max_sol_per_trade")
        return self


MEME_PAPER_V0 = MemeLimits(
    profile="meme_paper_v0",
    wallet_max_sol=Decimal("2.0"),
    max_sol_per_trade=Decimal("0.05"),
    daily_loss_cap_sol=Decimal("0.20"),
    max_open_positions=3,
    rug_cooldown_s=3600,
    max_exposure_per_mint_sol=Decimal("0.05"),
    max_participation_pct=Decimal("0.01"),
    max_price_impact_pct=Decimal("0.005"),
    max_slippage_pct=Decimal("0.01"),
    max_priority_fee_sol=Decimal("0.002"),
    max_priority_fee_pct_of_trade=Decimal("0.05"),
    max_jito_tip_sol=Decimal("0.001"),
    token_age_min_s=30,
    token_age_max_s=600,
    curve_progress_min_pct=Decimal("0.02"),
    curve_progress_max_pct=Decimal("0.50"),
    max_bundled_share_pct=Decimal("0.20"),
    max_top10_share_pct=Decimal("0.25"),
    max_state_age_s=5,
    clock_skew_tolerance_s=2,
    reservation_ttl_s=5,
    target_multiple=Decimal("2.0"),
    trailing_from_peak_pct=Decimal("0.30"),
    time_stop_s=900,
    warning_daily_loss_fraction=Decimal("0.5"),
    warning_size_multiplier=Decimal("0.5"),
    min_trade_sol=Decimal("0.001"),
    network_fee_sol=Decimal("0.000005"),
    ata_rent_sol=Decimal("0.00203928"),
)
"""§3.1's paper column. **Not** an approved live limit: the live profile is
:func:`limits_from_env` with the owner's numbers."""


def limits_from_env(
    env: Mapping[str, str], *, base: MemeLimits = MEME_PAPER_V0, profile: str = "meme_live_v0"
) -> MemeLimits:
    """The live profile: ``base`` with the five policy numbers replaced by the
    environment's. Any of the five absent or malformed ⇒ :class:`MemePolicyMissing`."""
    missing = tuple(name for name in POLICY_ENV if not (env.get(name) or "").strip())
    invalid: list[str] = []
    values: dict[str, Decimal | int] = {}
    for name in POLICY_ENV:
        if name in missing:
            continue
        raw = env[name]
        try:
            if name in ("MEME_MAX_OPEN_POSITIONS", "MEME_COOLDOWN_S"):
                values[name] = int(raw.strip())
            else:
                values[name] = parse_decimal(raw)
        except (InvalidOperation, ValueError):
            invalid.append(name)
    allowance = creator_unknown_allowance(env, invalid)
    window, detail = curve_progress_window(env, base, invalid)
    floor = min_trade_sol(env, invalid)
    cooldown = mint_cooldown_after_loss_s(env, invalid)
    per_trade = values.get("MEME_MAX_SOL_PER_TRADE")
    if per_trade is not None and floor > per_trade and ENV_MIN_TRADE_SOL not in invalid:
        invalid.append(ENV_MIN_TRADE_SOL)
        detail = f"{detail}; " if detail else ""
        detail += f"min_trade_sol {floor} exceeds max_sol_per_trade {per_trade}"
    if missing or invalid:
        raise MemePolicyMissing(missing, tuple(invalid), detail)
    # Re-validated as a whole: the cross-field rules (`per_trade <= wallet_max`)
    # must hold for the owner's numbers, not only for the paper preset.
    return MemeLimits.model_validate(
        {
            **base.model_dump(),
            "profile": profile,
            "wallet_max_sol": values["MEME_WALLET_MAX_SOL"],
            "max_sol_per_trade": per_trade,
            "daily_loss_cap_sol": values["MEME_DAILY_LOSS_CAP_SOL"],
            "max_open_positions": values["MEME_MAX_OPEN_POSITIONS"],
            "rug_cooldown_s": values["MEME_COOLDOWN_S"],
            # v0: no position reinforcement, so the per-mint cap *is* the per-trade cap.
            "max_exposure_per_mint_sol": per_trade,
            "min_trade_sol": floor,
            "mint_cooldown_after_loss_s": cooldown,
            **allowance,
            **window,
        }
    )
