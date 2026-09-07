"""Operational knobs of the execution-worker. Nothing here is a risk limit.

Every number that decides *money* — the 0,25 % of risk, the 2 % daily loss, the
1 % of participation, the 30 s reservation — lives in ``hunter_risk.limits`` and
in the ``paper_v1`` profile, never in an environment variable: a restart with a
different env must not be a different set of limits. What is here is cadence,
and the two flags the contract requires the process to refuse to start without.

``ENABLE_LIVE_TRADING=true`` is fatal at startup, by name. The worker is a paper
worker; ``LiveExecutionAdapter`` raises whatever the flag says, and a process
that came up anyway would be a process an operator believes is live.

``ENABLE_PAPER_AUTONOMY`` (default ``false``) gates the T3.14 bridge, which is
not in this task: with it off the worker only decides requests it is handed. The
flag exists here so the point of extension is explicit rather than implied.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "HEARTBEAT_KEY",
    "PRODUCER",
    "WORKER_ROLE",
    "ExecutionConfig",
    "LiveTradingRefused",
    "load_config",
]

HEARTBEAT_KEY = "hb:execution:paper"
"""``hb:execution:*`` — the shift report reads this one, next to the generic
``hb:{role}:{instance}`` the runtime already writes."""

PRODUCER = "execution-worker"
WORKER_ROLE = "hunter_worker"
"""Every cycle runs as the engine: ``portfolio_risk_state`` (the wallet lock and
``fifo_v1``), ``portfolios.kill_switch_state``, the equity curve and the outbox
are all worker-only since ``0007_paper_roles`` (§19.1)."""


class LiveTradingRefused(RuntimeError):
    """``ENABLE_LIVE_TRADING=true``: this process refuses to exist."""


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else float(raw)


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Cadence and gates. Defaults are what the compose service runs with."""

    admission_poll_s: float = 1.0
    """How often filed requests are looked at (T3.5 item 1)."""

    protection_poll_s: float = 1.0
    """Every tick of the tape is a chance for a stop to fire; ``/ready`` turns
    red past ``protection_max_delay_s``."""

    expiry_poll_s: float = 5.0
    """The 30 s reservation tenure, swept under the wallet lock (item 6)."""

    kill_switch_poll_s: float = 10.0
    """The re-read the contract's §5 rests on. The effect transactions re-read it
    again anyway; this is the *periodic* one, and it is what makes a blocked
    wallet cancel its pendings without waiting for an entry."""

    mtm_poll_s: float = 60.0
    """One point of the operational (1m) equity curve per minute."""

    mtm_max_age_s: float = 120.0
    protection_max_delay_s: float = 5.0
    outbox_lag_alert_s: float = 60.0

    exit_cost_rate: Decimal = Decimal("0.001")
    """The exit-cost hypothesis the wallet is marked with — the real SPOT taker
    fee (``SPOT_VIP0``, 10 bps). ``build_portfolio_state`` requires it with no
    default on purpose: the planned loss of a position includes getting out of
    it, and a ledger reporting the bare stop distance lets 190 of distance plus 2
    of cost fit under a ceiling of 200 (Astra, T3.3 review, must-fix B)."""

    enable_paper_autonomy: bool = False
    heartbeat_interval_s: float = 10.0


def load_config() -> ExecutionConfig:
    """Read the environment once, and refuse to run in a mode we do not have."""
    if _flag("ENABLE_LIVE_TRADING", False):
        raise LiveTradingRefused(
            "ENABLE_LIVE_TRADING is true and this is the paper execution worker. No live adapter "
            "exists (hunter_core.execution.live raises on construction and on every method), so a "
            "process that started anyway would be one an operator believes is trading real money"
        )
    return ExecutionConfig(
        admission_poll_s=_float("EXECUTION_ADMISSION_POLL_S", 1.0),
        protection_poll_s=_float("EXECUTION_PROTECTION_POLL_S", 1.0),
        expiry_poll_s=_float("EXECUTION_EXPIRY_POLL_S", 5.0),
        kill_switch_poll_s=_float("EXECUTION_KILL_SWITCH_POLL_S", 10.0),
        mtm_poll_s=_float("EXECUTION_MTM_POLL_S", 60.0),
        enable_paper_autonomy=_flag("ENABLE_PAPER_AUTONOMY", False),
    )
