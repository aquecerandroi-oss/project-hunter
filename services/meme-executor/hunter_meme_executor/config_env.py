"""The environment helpers of ``config.boot`` — split out in T4.55 (file-size
budget). Every helper here falls back to its default on an unreadable value;
none of them is one of the five policy variables (those refuse the boot in
``hunter_risk_meme.limits_from_env``) and none is an authorization (T4.28h).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from hunter_core.execution.meme.gates import MemeLiveTradingRefused
from hunter_meme_executor.creator_flow import DEFAULT_SELL_TOLERANCE_PCT

__all__ = ["Cluster", "bps", "cluster", "float_env", "int_env", "positive_decimal", "tolerance"]

Cluster = Literal["mainnet", "devnet"]


def float_env(env: Mapping[str, str], name: str, default: float) -> float:
    raw = (env.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def int_env(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def tolerance(env: Mapping[str, str]) -> Decimal:
    """``MEME_CREATOR_SELL_TOLERANCE_PCT`` in ``[0, 1)``.

    Unreadable or out of range falls back to the default instead of refusing the
    boot: this is not policy of capital and not an authorization (the two
    families of T4.28h), it is the dust margin of one inference, and its safe
    value is the small one. A ``1`` would make every creator a holder, so the
    range stops before it.
    """
    raw = (env.get("MEME_CREATOR_SELL_TOLERANCE_PCT") or "").strip()
    if not raw:
        return DEFAULT_SELL_TOLERANCE_PCT
    try:
        value = Decimal(raw)
    except (ArithmeticError, ValueError):
        return DEFAULT_SELL_TOLERANCE_PCT
    return value if Decimal(0) <= value < Decimal(1) else DEFAULT_SELL_TOLERANCE_PCT


def positive_decimal(env: Mapping[str, str], name: str, default: Decimal) -> Decimal:
    """A ``Decimal`` that must be ``> 0`` — an unreadable or non-positive value
    falls back to the default (the safe, small value) rather than refusing the
    boot: these are treasury sizing knobs, not the five policy variables."""
    try:
        value = Decimal((env.get(name) or "").strip() or default)
    except (ArithmeticError, ValueError):
        return default
    return value if value > 0 else default


def bps(env: Mapping[str, str], name: str, default: int) -> int:
    """Basis points in ``[1, 10_000]`` — outside that range falls back to the
    default rather than building a quote nobody asked for."""
    try:
        value = int((env.get(name) or "").strip() or default)
    except ValueError:
        return default
    return value if 0 < value <= 10_000 else default


def cluster(env: Mapping[str, str]) -> Cluster:
    raw = (env.get("MEME_EXECUTOR_CLUSTER") or "mainnet").strip().lower()
    if raw not in ("mainnet", "devnet"):
        raise MemeLiveTradingRefused("cluster_unknown", raw)
    return "devnet" if raw == "devnet" else "mainnet"
