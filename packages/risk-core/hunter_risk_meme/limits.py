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

T4.58: the **curve-progress window** (a strategy parameter, ``0.02``–``0.50`` in the
paper column) may be overridden by two optional variables,
``MEME_CURVE_PROGRESS_MIN_PCT`` / ``MEME_CURVE_PROGRESS_MAX_PCT``, so the owner can
align the executor's admission with the desk gate (``operator/5``
``max_progress_pct``) from the ``.env`` — absent keeps the base's values, and a
window that cannot be read or is empty refuses the boot by name, like the five.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from pydantic import Field, model_validator

from hunter_risk_meme.base import MemeModel

__all__ = [
    "ENV_CURVE_PROGRESS_MAX",
    "ENV_CURVE_PROGRESS_MIN",
    "MEME_PAPER_V0",
    "POLICY_ENV",
    "MemeLimits",
    "MemePolicyMissing",
    "limits_from_env",
]

POLICY_ENV: Final[tuple[str, ...]] = (
    "MEME_WALLET_MAX_SOL",
    "MEME_MAX_SOL_PER_TRADE",
    "MEME_DAILY_LOSS_CAP_SOL",
    "MEME_MAX_OPEN_POSITIONS",
    "MEME_COOLDOWN_S",
)
"""The five numbers only the owner writes (§3, "política de capital")."""

ENV_CREATOR_UNKNOWN_ALLOWED: Final = "MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED"
ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE: Final = "MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT"
"""T4.28h — **not** part of :data:`POLICY_ENV`: absent is a valid, complete policy
(the allowance stays off). Present and unreadable refuses the boot by name."""

ENV_CURVE_PROGRESS_MIN: Final = "MEME_CURVE_PROGRESS_MIN_PCT"
ENV_CURVE_PROGRESS_MAX: Final = "MEME_CURVE_PROGRESS_MAX_PCT"
"""T4.58 — optional, fractions in ``[0, 1]``: the window check 9 admits. Absent ⇒
the base's ``0.02``–``0.50``; unreadable, out of range or ``min >= max`` ⇒
:class:`MemePolicyMissing` naming the variable(s), like the five."""


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


def _decimal(raw: str) -> Decimal:
    value = Decimal(raw.strip())
    if not value.is_finite():
        raise InvalidOperation(raw)
    return value


_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


def _flag(raw: str) -> bool:
    """The vocabulary of every other flag of this system — and **nothing else**.

    A word nobody can read is not a "no": it is an owner who believes they wrote
    one thing and got another, so it joins ``invalid`` and the boot refuses by name.
    """
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(raw)


def _creator_unknown_allowance(
    env: Mapping[str, str], invalid: list[str]
) -> dict[str, bool | Decimal]:
    """T4.28h's two optional variables: absent ⇒ the base's values (off, 10 %);
    present and unreadable ⇒ named in the boot refusal, like the five."""
    values: dict[str, bool | Decimal] = {}
    raw_flag = (env.get(ENV_CREATOR_UNKNOWN_ALLOWED) or "").strip()
    if raw_flag:
        try:
            values["creator_unknown_allowed_if_dev_measured"] = _flag(raw_flag)
        except ValueError:
            invalid.append(ENV_CREATOR_UNKNOWN_ALLOWED)
    raw_cap = (env.get(ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE) or "").strip()
    if not raw_cap:
        return values
    try:
        cap = _decimal(raw_cap)
    except (InvalidOperation, ValueError):
        invalid.append(ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE)
        return values
    if not (0 <= cap <= 1):
        invalid.append(ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE)
        return values
    values["creator_unknown_max_dev_share_pct"] = cap
    return values


def _fraction(env: Mapping[str, str], name: str, invalid: list[str]) -> Decimal | None:
    """An optional fraction in ``[0, 1]``: absent ⇒ ``None``; unreadable or out of
    range ⇒ named in ``invalid`` and ``None``."""
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = _decimal(raw)
    except (InvalidOperation, ValueError):
        invalid.append(name)
        return None
    if not (0 <= value <= 1):
        invalid.append(name)
        return None
    return value


def _curve_progress_window(
    env: Mapping[str, str], base: MemeLimits, invalid: list[str]
) -> tuple[dict[str, Decimal], str]:
    """T4.58's two optional variables: absent ⇒ the base's window; the effective
    window (env over base) must be non-empty, or the variable(s) that were given
    are named in ``invalid`` with the window spelled out in the detail."""
    given: dict[str, Decimal] = {}
    low = _fraction(env, ENV_CURVE_PROGRESS_MIN, invalid)
    high = _fraction(env, ENV_CURVE_PROGRESS_MAX, invalid)
    if low is not None:
        given["curve_progress_min_pct"] = low
    if high is not None:
        given["curve_progress_max_pct"] = high
    if not given:
        return given, ""
    lo = base.curve_progress_min_pct if low is None else low
    hi = base.curve_progress_max_pct if high is None else high
    if lo >= hi:
        invalid.extend(
            name
            for name, v in ((ENV_CURVE_PROGRESS_MIN, low), (ENV_CURVE_PROGRESS_MAX, high))
            if v is not None
        )
        return {}, f"curve_progress window is empty (min={lo} >= max={hi})"
    return given, ""


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
                values[name] = _decimal(raw)
        except (InvalidOperation, ValueError):
            invalid.append(name)
    allowance = _creator_unknown_allowance(env, invalid)
    window, detail = _curve_progress_window(env, base, invalid)
    if missing or invalid:
        raise MemePolicyMissing(missing, tuple(invalid), detail)
    per_trade = values["MEME_MAX_SOL_PER_TRADE"]
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
            **allowance,
            **window,
        }
    )
