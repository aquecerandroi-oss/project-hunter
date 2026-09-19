"""T4.74-3 — the ``SPOT1_*`` knobs of the ``spot/1`` lane (design
``docs/design/spot1-lab-solana.md`` §6), read from the environment once at boot.

Nothing here turns money on by itself: ``enabled`` is true only when
``SPOT1_ENABLED`` reads on **and** ``ENABLE_MEME_LIVE_TRADING`` is on **and**
the caller proved a signer exists (``signer_present`` — the key is popped from
the environment by ``boot_meme_execution``, so this module cannot see it and
does not try). Anything short of that is ``inert:<reason>`` in the heartbeat.

Percents are typed as percents (``SPOT1_MAX_PARITY_PCT=3``) and stored as
fractions (``0.03``), the unit ``MemeLimits`` and ``MemeSpotProfile`` speak. An
unreadable or out-of-range value falls back to the default with a warning, the
``launch_config.py`` rule — never a crash, never a bigger number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hunter_core.execution.meme.gates import ENV_LIVE_FLAG, parse_flag
from hunter_core.logging import get_logger
from hunter_risk_meme import MemeLimits, MemeSpotProfile

__all__ = [
    "DEFAULT_PRIORITY_FEE_MAX_LAMPORTS",
    "DEFAULT_STRATEGY_VERSION",
    "DEFAULT_TICKET_SOL",
    "ENV_SPOT_ENABLED",
    "ENV_SPOT_REFUTATION_RESET_AT",
    "ENV_SPOT_STRATEGY_VERSION",
    "SPOT_DECIDED_BY",
    "SPOT_STRATEGY_KEY",
    "SpotConfig",
]

logger = get_logger(__name__)

ENV_SPOT_ENABLED = "SPOT1_ENABLED"
ENV_SPOT_STRATEGY_VERSION = "SPOT1_STRATEGY_VERSION"
ENV_SPOT_TICKET_SOL = "SPOT1_TICKET_SOL"
ENV_SPOT_MAX_OPEN = "SPOT1_MAX_OPEN"
ENV_SPOT_MAX_SIGNAL_AGE_S = "SPOT1_MAX_SIGNAL_AGE_S"
ENV_SPOT_MAX_HOLD_S = "SPOT1_MAX_HOLD_S"
ENV_SPOT_MAX_PARITY_PCT = "SPOT1_MAX_PARITY_PCT"
ENV_SPOT_MAX_IMPACT_PCT = "SPOT1_MAX_IMPACT_PCT"
ENV_SPOT_MAX_COST_R = "SPOT1_MAX_COST_R"
ENV_SPOT_MARK_S = "SPOT1_MARK_S"
ENV_SPOT_EXIT_SLIPPAGE_BPS = "SPOT1_EXIT_SLIPPAGE_BPS"
ENV_SPOT_PANIC_SLIPPAGE_BPS = "SPOT1_PANIC_SLIPPAGE_BPS"
ENV_SPOT_PRIORITY_FEE_MAX_LAMPORTS = "SPOT1_PRIORITY_FEE_MAX_LAMPORTS"
ENV_SPOT_REFUTE_MIN_TRADES = "SPOT1_REFUTE_MIN_TRADES"
ENV_SPOT_REFUTE_MAX_LOSS_SOL = "SPOT1_REFUTE_MAX_LOSS_SOL"
ENV_SPOT_CONSECUTIVE_STOPS_PAUSE_S = "SPOT1_CONSECUTIVE_STOPS_PAUSE_S"
ENV_SPOT_REFUTATION_RESET_AT = "SPOT1_REFUTATION_RESET_AT"

SPOT_STRATEGY_KEY = "mean_reversion"
"""``strategies.key`` of the only strategy the desk operates (design §2)."""
SPOT_DECIDED_BY = "executor:spot1_auto"
"""``spot_orders.admission.decided_by`` — stage 1 has no click (§6)."""
DEFAULT_STRATEGY_VERSION = "v14"
DEFAULT_TICKET_SOL = Decimal("0.05")
DEFAULT_PRIORITY_FEE_MAX_LAMPORTS = 100_000
"""Per leg; 200 000 blew ``cost_r`` at 0,05 SOL (T4.74-2)."""
_HUNDRED = Decimal(100)
_INVALID = "meme_spot_config_invalid"


@dataclass(frozen=True, slots=True)
class SpotConfig:
    requested: bool = False
    """``SPOT1_ENABLED`` as written; :attr:`enabled` is what the executor obeys."""
    live: bool = False
    signer_present: bool = False
    strategy_version: str = DEFAULT_STRATEGY_VERSION
    ticket_sol: Decimal = DEFAULT_TICKET_SOL
    max_open: int = 3
    max_signal_age_s: int = 180
    max_hold_s: int = 14_400
    max_parity_pct: Decimal = Decimal("0.03")
    max_impact_pct: Decimal = Decimal("0.005")
    max_cost_r: Decimal = Decimal("0.5")
    mark_s: int = 20
    exit_slippage_bps: int = 50
    panic_slippage_bps: int = 300
    priority_fee_max_lamports: int = DEFAULT_PRIORITY_FEE_MAX_LAMPORTS
    refute_min_trades: int = 20
    refute_max_loss_sol: Decimal = Decimal("0.15")
    consecutive_stops_pause_s: int = 7_200
    refutation_reset_at: datetime | None = None

    @property
    def inert_reason(self) -> str | None:
        """Why the lane does nothing; ``None`` only when every gate is open."""
        if not self.requested:
            return "disabled"
        if not self.live:
            return "meme_live_disabled"
        if not self.signer_present:
            return "signer_missing"
        return None

    @property
    def enabled(self) -> bool:
        return self.inert_reason is None

    def ticket(self, limits: MemeLimits) -> Decimal:
        """Never above the policy's ``max_sol_per_trade`` (the scope clamps at the caller)."""
        return min(self.ticket_sol, limits.max_sol_per_trade)

    def profile(self, limits: MemeLimits) -> MemeSpotProfile:
        return MemeSpotProfile(
            ticket_sol=self.ticket(limits),
            max_open=self.max_open,
            max_parity_pct=self.max_parity_pct,
            max_impact_pct=self.max_impact_pct,
            max_cost_r=self.max_cost_r,
            max_signal_age_s=self.max_signal_age_s,
        )

    def as_json(self, limits: MemeLimits | None = None) -> dict[str, object]:
        reset = self.refutation_reset_at
        return {
            "mode": "on" if self.enabled else f"inert:{self.inert_reason}",
            "strategy_version": self.strategy_version,
            "ticket_sol": str(self.ticket_sol if limits is None else self.ticket(limits)),
            "max_open": self.max_open,
            "max_signal_age_s": self.max_signal_age_s,
            "max_hold_s": self.max_hold_s,
            "max_parity_pct": str(self.max_parity_pct),
            "max_impact_pct": str(self.max_impact_pct),
            "max_cost_r": str(self.max_cost_r),
            "mark_s": self.mark_s,
            "exit_slippage_bps": self.exit_slippage_bps,
            "panic_slippage_bps": self.panic_slippage_bps,
            "priority_fee_max_lamports": self.priority_fee_max_lamports,
            "refute_min_trades": self.refute_min_trades,
            "refute_max_loss_sol": str(self.refute_max_loss_sol),
            "consecutive_stops_pause_s": self.consecutive_stops_pause_s,
            "refutation_reset_at": None if reset is None else reset.isoformat(),
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, signer_present: bool = False) -> SpotConfig:
        """``signer_present`` is the caller's proof (``signer is not None`` after
        ``boot_meme_execution``); it defaults to the safe side."""
        one_micro, ten, week = Decimal("0.000001"), Decimal(10), 7 * 86_400
        return cls(
            requested=parse_flag(env.get(ENV_SPOT_ENABLED)),
            live=parse_flag(env.get(ENV_LIVE_FLAG)),
            signer_present=signer_present,
            strategy_version=_version(env, ENV_SPOT_STRATEGY_VERSION, DEFAULT_STRATEGY_VERSION),
            ticket_sol=_decimal_in(env, ENV_SPOT_TICKET_SOL, DEFAULT_TICKET_SOL, one_micro, ten),
            max_open=_int_in(env, ENV_SPOT_MAX_OPEN, 3, 1, 50),
            max_signal_age_s=_int_in(env, ENV_SPOT_MAX_SIGNAL_AGE_S, 180, 1, 3_600),
            max_hold_s=_int_in(env, ENV_SPOT_MAX_HOLD_S, 14_400, 60, week),
            max_parity_pct=_percent_in(env, ENV_SPOT_MAX_PARITY_PCT, Decimal("0.03")),
            max_impact_pct=_percent_in(env, ENV_SPOT_MAX_IMPACT_PCT, Decimal("0.005")),
            max_cost_r=_decimal_in(env, ENV_SPOT_MAX_COST_R, Decimal("0.5"), Decimal("0.01"), ten),
            mark_s=_int_in(env, ENV_SPOT_MARK_S, 20, 5, 300),
            exit_slippage_bps=_int_in(env, ENV_SPOT_EXIT_SLIPPAGE_BPS, 50, 1, 2_000),
            panic_slippage_bps=_int_in(env, ENV_SPOT_PANIC_SLIPPAGE_BPS, 300, 1, 2_000),
            priority_fee_max_lamports=_int_in(
                env, ENV_SPOT_PRIORITY_FEE_MAX_LAMPORTS, DEFAULT_PRIORITY_FEE_MAX_LAMPORTS, 0, 10**9
            ),
            refute_min_trades=_int_in(env, ENV_SPOT_REFUTE_MIN_TRADES, 20, 1, 1_000),
            refute_max_loss_sol=_decimal_in(
                env, ENV_SPOT_REFUTE_MAX_LOSS_SOL, Decimal("0.15"), one_micro, Decimal(100)
            ),
            consecutive_stops_pause_s=_int_in(
                env, ENV_SPOT_CONSECUTIVE_STOPS_PAUSE_S, 7_200, 0, week
            ),
            refutation_reset_at=_stamp(env, ENV_SPOT_REFUTATION_RESET_AT),
        )


def _raw(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _warn(name: str, raw: str) -> None:
    logger.warning(_INVALID, variable=name, value=raw[:20])


def _int_in(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _warn(name, raw)
        return default
    if not low <= value <= high:
        _warn(name, raw)
        return default
    return value


def _decimal_in(
    env: Mapping[str, str], name: str, default: Decimal, low: Decimal, high: Decimal
) -> Decimal:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except (ArithmeticError, ValueError):
        _warn(name, raw)
        return default
    if not value.is_finite() or not low <= value <= high:
        _warn(name, raw)
        return default
    return value


def _percent_in(env: Mapping[str, str], name: str, default_fraction: Decimal) -> Decimal:
    """Typed in percent (``3`` = 3 %), bounded to ``(0, 100]``, stored as a fraction."""
    default_pct = default_fraction * _HUNDRED
    pct = _decimal_in(env, name, default_pct, Decimal("0.0001"), _HUNDRED)
    return default_fraction if pct == default_pct else pct / _HUNDRED


def _version(env: Mapping[str, str], name: str, default: str) -> str:
    raw = _raw(env, name)
    if not raw:
        return default
    if len(raw) > 32 or not all(ch.isalnum() or ch in "._-" for ch in raw):
        _warn(name, raw)
        return default
    return raw


def _stamp(env: Mapping[str, str], name: str) -> datetime | None:
    """ISO 8601 **with** an offset; a naive stamp is refused (a 3 h ambiguity on
    the owner's own "signature" would reopen the desk at the wrong instant)."""
    raw = _raw(env, name)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        _warn(name, raw)
        return None
    if value.tzinfo is None:
        _warn(name, raw)
        return None
    return value
