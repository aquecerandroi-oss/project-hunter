"""The **optional** environment variables of :func:`hunter_risk_meme.limits.limits_from_env`
— split out of ``limits.py`` in T4.78 (350-line budget), behaviour unchanged.

None of these is one of the five policy variables (``POLICY_ENV``): absent is a
complete policy and the base's value applies. Present and unreadable is not a
"no" — it is an owner who believes they wrote one thing and got another — so
every helper here appends the variable's name to ``invalid`` and the boot
refuses by name (``MemePolicyMissing``), exactly like the five.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hunter_risk_meme.limits import MemeLimits

__all__ = [
    "DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S",
    "ENV_CREATOR_UNKNOWN_ALLOWED",
    "ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE",
    "ENV_CURVE_PROGRESS_MAX",
    "ENV_CURVE_PROGRESS_MIN",
    "ENV_MINT_COOLDOWN_AFTER_LOSS",
    "ENV_MIN_TRADE_SOL",
    "LIVE_MIN_TRADE_SOL",
    "creator_unknown_allowance",
    "curve_progress_window",
    "min_trade_sol",
    "mint_cooldown_after_loss_s",
    "parse_decimal",
]

ENV_CREATOR_UNKNOWN_ALLOWED: Final = "MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED"
ENV_CREATOR_UNKNOWN_MAX_DEV_SHARE: Final = "MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT"
"""T4.28h — **not** part of ``POLICY_ENV``: absent is a valid, complete policy
(the allowance stays off). Present and unreadable refuses the boot by name."""

ENV_CURVE_PROGRESS_MIN: Final = "MEME_CURVE_PROGRESS_MIN_PCT"
ENV_CURVE_PROGRESS_MAX: Final = "MEME_CURVE_PROGRESS_MAX_PCT"
"""T4.58 — optional, fractions in ``[0, 1]``: the window check 9 admits. Absent ⇒
the base's ``0.02``–``0.50``; unreadable, out of range or ``min >= max`` ⇒
``MemePolicyMissing`` naming the variable(s), like the five."""

ENV_MIN_TRADE_SOL: Final = "MEME_MIN_TRADE_SOL"
LIVE_MIN_TRADE_SOL: Final = Decimal("0.02")
"""T4.61c — optional, SOL: the smallest buy the live profile sends (check 23, and
check 26's ``conviction_too_small``). Absent ⇒ 0,02 — never the paper preset's 0,001:
against ~0,0025 SOL of fixed costs (ATA rent 0,00204 + fees) a 0,0175 SOL buy pays 12 %
to exist, and was being sent. Unreadable, ``<= 0`` or above ``MEME_MAX_SOL_PER_TRADE``
⇒ ``MemePolicyMissing`` naming it."""

ENV_MINT_COOLDOWN_AFTER_LOSS: Final = "MEME_MINT_COOLDOWN_AFTER_LOSS_S"
DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S: Final = 300
"""T4.78 — optional, whole seconds ``>= 0``: how long check 28 refuses a new buy
on a mint whose last live close lost (``0`` disables). Absent ⇒ 300 — every
re-entry R64 observed (paper and real, 19/09/2026) came in under 5 min, so a
longer window has no evidence behind it. Unreadable or negative ⇒
``MemePolicyMissing`` naming it: this number is Everton's, like the five."""

_TRUE: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


def parse_decimal(raw: str) -> Decimal:
    value = Decimal(raw.strip())
    if not value.is_finite():
        raise InvalidOperation(raw)
    return value


def _flag(raw: str) -> bool:
    """The vocabulary of every other flag of this system — and **nothing else**."""
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(raw)


def creator_unknown_allowance(
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
        cap = parse_decimal(raw_cap)
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
        value = parse_decimal(raw)
    except (InvalidOperation, ValueError):
        invalid.append(name)
        return None
    if not (0 <= value <= 1):
        invalid.append(name)
        return None
    return value


def curve_progress_window(
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


def min_trade_sol(env: Mapping[str, str], invalid: list[str]) -> Decimal:
    raw = (env.get(ENV_MIN_TRADE_SOL) or "").strip()
    try:
        value = parse_decimal(raw) if raw else LIVE_MIN_TRADE_SOL
    except (InvalidOperation, ValueError):
        value = Decimal(0)
    if value <= 0:
        invalid.append(ENV_MIN_TRADE_SOL)
        return LIVE_MIN_TRADE_SOL
    return value


def mint_cooldown_after_loss_s(env: Mapping[str, str], invalid: list[str]) -> int:
    """T4.78: whole seconds ``>= 0``; absent ⇒ :data:`DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S`.
    ``1.5``, ``abc`` or ``-1`` are named in ``invalid`` (the default is returned
    only so the caller can finish collecting names before refusing)."""
    raw = (env.get(ENV_MINT_COOLDOWN_AFTER_LOSS) or "").strip()
    if not raw:
        return DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S
    try:
        value = int(raw)
    except ValueError:
        invalid.append(ENV_MINT_COOLDOWN_AFTER_LOSS)
        return DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S
    if value < 0:
        invalid.append(ENV_MINT_COOLDOWN_AFTER_LOSS)
        return DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S
    return value
