"""T4.55 — the knobs of the *send* path, read from the environment, none of them
policy of capital (the five ``MEME_*`` of §3 stay where they are):

- ``MEME_PRIORITY_FEE_FLOOR_MICRO_LAMPORTS`` (default 100 000) and
  ``MEME_PRIORITY_FEE_MAX_SOL`` (default 0,002): the floor and the total-cost cap
  of the dynamic priority fee (``priority_fee.py``);
- ``MEME_EXIT_MAX_SLIPPAGE_PCT`` (default **5**, in per cent): the tolerance a
  sell's ``min_sol_output`` is built with — separate from the buy's
  ``max_slippage_pct`` (unchanged, 1 %). R56 §2: the second sell of PS died in
  simulation with ``6003 TooLittleSolReceived`` because the curve dropped 14 %
  in the second between the quote and the check, against a 1 % tolerance;
- ``MEME_PANIC_EXIT_MAX_SLIPPAGE_PCT`` (default **15**): the tolerance of a
  ``creator_dump`` / ``rug_signal`` exit — a sell that must happen on a curve
  that is melting;
- ``MEME_RESEND_INTERVAL_S`` (default 2): how often the same signed bytes are
  re-sent while unconfirmed (``submit.py``); ``0`` keeps the single send.

An unreadable or out-of-range value falls back to the default (the safe one),
never refuses the boot: these are tuning, not authorization (T4.28h's two
families). Slippage is capped at 50 % (``quote.MAX_SLIPPAGE_BPS``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from hunter_exchanges.pumpfun.quote import MAX_SLIPPAGE_BPS
from hunter_meme_executor.priority_fee import DEFAULT_FLOOR_MICRO_LAMPORTS, DEFAULT_MAX_SOL

__all__ = [
    "ENV_EXIT_MAX_SLIPPAGE_PCT",
    "ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT",
    "ENV_PRIORITY_FEE_FLOOR",
    "ENV_PRIORITY_FEE_MAX_SOL",
    "ENV_RESEND_INTERVAL_S",
    "PANIC_EXIT_REASONS",
    "SendTuning",
]

ENV_PRIORITY_FEE_FLOOR = "MEME_PRIORITY_FEE_FLOOR_MICRO_LAMPORTS"
ENV_PRIORITY_FEE_MAX_SOL = "MEME_PRIORITY_FEE_MAX_SOL"
ENV_EXIT_MAX_SLIPPAGE_PCT = "MEME_EXIT_MAX_SLIPPAGE_PCT"
ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT = "MEME_PANIC_EXIT_MAX_SLIPPAGE_PCT"
ENV_RESEND_INTERVAL_S = "MEME_RESEND_INTERVAL_S"

PANIC_EXIT_REASONS: frozenset[str] = frozenset({"creator_dump", "rug_signal"})
"""The exit reasons (``hunter_risk_meme.exits.decide_exit``) that may use the
panic tolerance. ``sell_now``, ``target``, ``trailing``, ``time_stop``,
``migrated``, ``curve_complete``, ``emergency_auto_close`` use the normal one."""

DEFAULT_EXIT_MAX_SLIPPAGE_PCT = Decimal(5)
DEFAULT_PANIC_EXIT_MAX_SLIPPAGE_PCT = Decimal(15)
DEFAULT_RESEND_INTERVAL_S = 2.0
MAX_SLIPPAGE_PCT = Decimal(MAX_SLIPPAGE_BPS) / 100


@dataclass(frozen=True, slots=True)
class SendTuning:
    priority_fee_floor_micro_lamports: int = DEFAULT_FLOOR_MICRO_LAMPORTS
    priority_fee_max_sol: Decimal = DEFAULT_MAX_SOL
    exit_max_slippage_pct: Decimal = DEFAULT_EXIT_MAX_SLIPPAGE_PCT
    """Per cent: ``5`` means 5 % (unlike ``MemeLimits.max_slippage_pct``, a fraction)."""
    panic_exit_max_slippage_pct: Decimal = DEFAULT_PANIC_EXIT_MAX_SLIPPAGE_PCT
    resend_interval_s: float = DEFAULT_RESEND_INTERVAL_S

    def exit_slippage_bps(self, reason: str) -> int:
        """The ``max_slippage_bps`` a sell for ``reason`` is quoted and built with."""
        pct = (
            self.panic_exit_max_slippage_pct
            if reason in PANIC_EXIT_REASONS
            else self.exit_max_slippage_pct
        )
        return int(pct * 100)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SendTuning:
        return cls(
            priority_fee_floor_micro_lamports=_int_at_least(
                env, ENV_PRIORITY_FEE_FLOOR, DEFAULT_FLOOR_MICRO_LAMPORTS, minimum=0
            ),
            priority_fee_max_sol=_positive_decimal(env, ENV_PRIORITY_FEE_MAX_SOL, DEFAULT_MAX_SOL),
            exit_max_slippage_pct=_slippage_pct(
                env, ENV_EXIT_MAX_SLIPPAGE_PCT, DEFAULT_EXIT_MAX_SLIPPAGE_PCT
            ),
            panic_exit_max_slippage_pct=_slippage_pct(
                env, ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT, DEFAULT_PANIC_EXIT_MAX_SLIPPAGE_PCT
            ),
            resend_interval_s=_float_at_least(
                env, ENV_RESEND_INTERVAL_S, DEFAULT_RESEND_INTERVAL_S, minimum=0.0
            ),
        )


def _raw(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _int_at_least(env: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _float_at_least(env: Mapping[str, str], name: str, default: float, *, minimum: float) -> float:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _positive_decimal(env: Mapping[str, str], name: str, default: Decimal) -> Decimal:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except (ArithmeticError, ValueError):
        return default
    return value if value > 0 else default


def _slippage_pct(env: Mapping[str, str], name: str, default: Decimal) -> Decimal:
    """``(0, 50]`` per cent — the quote refuses more than ``MAX_SLIPPAGE_BPS``."""
    value = _positive_decimal(env, name, default)
    return value if value <= MAX_SLIPPAGE_PCT else default
