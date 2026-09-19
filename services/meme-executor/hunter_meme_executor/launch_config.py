"""T4.67b — the knobs of the launch lane (EXP-M18), read from the environment.

``MEME_LAUNCH_LANE`` is the **same** variable the radar's launch lane reads
(``off`` | ``paper`` | ``on``). The executor acts only in ``on``: in ``off`` and
``paper`` it never queries ``launch_v0/*`` proposals (they stay
``research_only``, filled by the paper loop in shadow), opens no loop and
publishes ``launch_lane_mode`` so the desk sees which. Anything else in the
variable reads as ``off`` with a warning — never a crash, never ``on``.

None of these is policy of capital (the five ``MEME_*`` of §3 stay where they
are): the ticket is clamped by ``max_sol_per_trade`` at use, the open cap is a
second cap under the global one, the priority floor is capped by
``MEME_PRIORITY_FEE_MAX_SOL`` and the buy tolerance by the 20 % ceiling of
T4.59. An unreadable or out-of-range value falls back to the default (the small
one), like ``send_tuning.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from hunter_core.execution.meme.gates import parse_flag
from hunter_core.logging import get_logger
from hunter_meme_executor.send_tuning import MAX_BUY_SLIPPAGE_PCT
from hunter_risk_meme import MemeLaunchProfile, MemeLimits

__all__ = [
    "BLOCKHASH_REFRESH_S",
    "ENV_LAUNCH_BUY_SLIPPAGE_PCT",
    "ENV_LAUNCH_LANE",
    "ENV_LAUNCH_MAX_AGE_S",
    "ENV_LAUNCH_MAX_OPEN",
    "ENV_LAUNCH_MAX_PARTICIPATION_PCT",
    "ENV_LAUNCH_PRIORITY_FLOOR",
    "ENV_LAUNCH_SKIP_SIMULATION",
    "ENV_LAUNCH_TICKET_SOL",
    "LAUNCH_EXIT_TICK_S",
    "LAUNCH_RULE_SET_NAME",
    "LAUNCH_SERIES",
    "LaunchConfig",
    "LaunchMode",
]

logger = get_logger(__name__)

ENV_LAUNCH_LANE = "MEME_LAUNCH_LANE"
ENV_LAUNCH_MAX_OPEN = "MEME_LAUNCH_MAX_OPEN"
ENV_LAUNCH_TICKET_SOL = "MEME_LAUNCH_TICKET_SOL"
ENV_LAUNCH_PRIORITY_FLOOR = "MEME_LAUNCH_PRIORITY_FLOOR_MICRO_LAMPORTS"
ENV_LAUNCH_BUY_SLIPPAGE_PCT = "MEME_LAUNCH_BUY_SLIPPAGE_PCT"
ENV_LAUNCH_SKIP_SIMULATION = "MEME_LAUNCH_SKIP_SIMULATION"
ENV_LAUNCH_MAX_PARTICIPATION_PCT = "MEME_LAUNCH_MAX_PARTICIPATION_PCT"
ENV_LAUNCH_MAX_AGE_S = "MEME_LAUNCH_MAX_AGE_S"

LaunchMode = Literal["off", "paper", "on"]
_MODES: frozenset[str] = frozenset({"off", "paper", "on"})

LAUNCH_RULE_SET_NAME = "launch_v0"
"""``meme_rule_sets.name`` of the launch set (T4.67a) — every version of it."""
LAUNCH_SERIES = "meme_launch_lane_v1"
"""``reasons[0].series`` the radar's launch lane writes on its proposals."""

DEFAULT_MAX_OPEN = 2
DEFAULT_TICKET_SOL = Decimal("0.01")
DEFAULT_PRIORITY_FLOOR = 1_000_000
"""µL/CU — 0,0004 SOL with 400 000 CU: the block after a ``create`` is fought over."""
DEFAULT_BUY_SLIPPAGE_PCT = Decimal(10)
DEFAULT_MAX_PARTICIPATION_PCT = Decimal("0.10")
"""Of the real SOL already in the curve at the quote: a 0,01 ticket needs 0,1 SOL
of buys before ours. Not the profile's 1 % (that would need 1 SOL in the first
second) — a launch number, owned by the owner (``docs/RISK_ENGINE_MEME.md``)."""
DEFAULT_MAX_AGE_S = 5
"""Older than this at the admission the launch is over (EXP-M18: the bet is ≤ 1 s;
+3 s already reads 1,01×) — measured from the proposal's create stamp."""
BLOCKHASH_REFRESH_S = 5.0
"""The cached blockhash is refreshed when older than this (the launch loop and
the kill-switch tick both do it); a blockhash lives ~60 s, so a buy never signs
against one older than the refresh cadence plus one loop."""
LAUNCH_EXIT_TICK_S = 2.0
"""The fallback tick for launch positions (the desk's is ``mark_s``, 5–10 s)."""


@dataclass(frozen=True, slots=True)
class LaunchConfig:
    mode: LaunchMode = "off"
    max_open: int = DEFAULT_MAX_OPEN
    ticket_sol: Decimal = DEFAULT_TICKET_SOL
    priority_floor_micro_lamports: int = DEFAULT_PRIORITY_FLOOR
    buy_slippage_pct: Decimal = DEFAULT_BUY_SLIPPAGE_PCT
    skip_simulation: bool = False
    max_participation_pct: Decimal = DEFAULT_MAX_PARTICIPATION_PCT
    max_age_s: int = DEFAULT_MAX_AGE_S

    @property
    def enabled(self) -> bool:
        """``on`` — the only mode in which the executor touches a launch proposal."""
        return self.mode == "on"

    def buy_slippage_bps(self) -> int:
        return int(self.buy_slippage_pct * 100)

    def ticket(self, limits: MemeLimits) -> Decimal:
        """The effective ticket: never above the policy's ``max_sol_per_trade``."""
        return min(self.ticket_sol, limits.max_sol_per_trade)

    def profile(self, limits: MemeLimits) -> MemeLaunchProfile:
        """What the engine receives (``hunter_risk_meme.profile``)."""
        return MemeLaunchProfile(
            ticket_sol=self.ticket(limits),
            max_open=self.max_open,
            max_participation_pct=self.max_participation_pct,
            max_token_age_s=self.max_age_s,
        )

    def as_json(self, limits: MemeLimits | None = None) -> dict[str, object]:
        return {
            "mode": self.mode,
            "max_open": self.max_open,
            "ticket_sol": str(self.ticket_sol if limits is None else self.ticket(limits)),
            "priority_floor_micro_lamports": self.priority_floor_micro_lamports,
            "buy_slippage_pct": str(self.buy_slippage_pct),
            "skip_simulation": self.skip_simulation,
            "max_participation_pct": str(self.max_participation_pct),
            "max_age_s": self.max_age_s,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> LaunchConfig:
        mode = _raw(env, ENV_LAUNCH_LANE).lower()
        if mode and mode not in _MODES:
            logger.warning("meme_launch_config_invalid", variable=ENV_LAUNCH_LANE, value=mode[:20])
            mode = "off"
        return cls(
            mode="on" if mode == "on" else ("paper" if mode == "paper" else "off"),
            max_open=_int_in(env, ENV_LAUNCH_MAX_OPEN, DEFAULT_MAX_OPEN, low=1, high=50),
            ticket_sol=_decimal_in(
                env,
                ENV_LAUNCH_TICKET_SOL,
                DEFAULT_TICKET_SOL,
                low=Decimal("0.000001"),
                high=Decimal(10),
            ),
            priority_floor_micro_lamports=_int_in(
                env, ENV_LAUNCH_PRIORITY_FLOOR, DEFAULT_PRIORITY_FLOOR, low=0, high=10**12
            ),
            buy_slippage_pct=_decimal_in(
                env,
                ENV_LAUNCH_BUY_SLIPPAGE_PCT,
                DEFAULT_BUY_SLIPPAGE_PCT,
                low=Decimal("0.01"),
                high=MAX_BUY_SLIPPAGE_PCT,
            ),
            skip_simulation=parse_flag(env.get(ENV_LAUNCH_SKIP_SIMULATION), default=False),
            max_participation_pct=_decimal_in(
                env,
                ENV_LAUNCH_MAX_PARTICIPATION_PCT,
                DEFAULT_MAX_PARTICIPATION_PCT,
                low=Decimal("0.0001"),
                high=Decimal(1),
            ),
            max_age_s=_int_in(env, ENV_LAUNCH_MAX_AGE_S, DEFAULT_MAX_AGE_S, low=1, high=600),
        )


def _raw(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _int_in(env: Mapping[str, str], name: str, default: int, *, low: int, high: int) -> int:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("meme_launch_config_invalid", variable=name, value=raw[:20])
        return default
    if not low <= value <= high:
        logger.warning("meme_launch_config_invalid", variable=name, value=raw[:20])
        return default
    return value


def _decimal_in(
    env: Mapping[str, str], name: str, default: Decimal, *, low: Decimal, high: Decimal
) -> Decimal:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except (ArithmeticError, ValueError):
        logger.warning("meme_launch_config_invalid", variable=name, value=raw[:20])
        return default
    if not value.is_finite() or not low <= value <= high:
        logger.warning("meme_launch_config_invalid", variable=name, value=raw[:20])
        return default
    return value
