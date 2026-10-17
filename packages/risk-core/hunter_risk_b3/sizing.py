"""Sizing and checks 16–18 (docs/RISK_ENGINE_B3.md §8.3).

``risk_per_contract = |limit_price − stop| / tick × tick_value + stop_slippage_ticks ×
tick_value + 2 × per_leg`` — from the **worst admissible price**, never the reference.
``n_raw = min(caps)``, the winner published as ``binding_constraint`` (ties by the order of
``CAP_ORDER``); WARNING halves (1 becomes 0); the volume is normalised downwards. Then
checks 16, 17 and 18 are evaluated at the final volume — at ``max(n_final, 1)`` when the
size is zero, so the winning ceiling fails with its own reason (§8.3 "n_final < 1").

Floors use ``Decimal.__floordiv__`` (exact divide-integer) on positive operands, so a
quotient like 2.99999… never rounds up to 3 under the 28-digit context.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from hunter_risk_b3.context import SpecPin
from hunter_risk_b3.decision import B3Check, B3Sizing, check_failed, check_passed, check_unavailable
from hunter_risk_b3.enums import KillSwitchState
from hunter_risk_b3.frame import Done, Frame, upstream
from hunter_risk_b3.kill_switch import halve_for_warning

__all__ = ["CAP_ORDER", "SizingResult", "check_margin", "check_trade_risk_cap",
           "check_trade_risk_vs_allowance", "compute_sizing", "normalize_volume",
           "risk_per_contract_brl"]  # fmt: skip

CAP_ORDER: Final[tuple[str, ...]] = (
    "requested", "max_contracts_per_order", "max_contracts_per_position", "alloc_margin",
    "free_margin", "trade_risk_cap", "daily_allowance",
)  # fmt: skip
_ZERO = Decimal(0)


def risk_per_contract_brl(
    *, limit_price: Decimal, stop: Decimal, pin: SpecPin, stop_slippage_ticks: int,
    per_leg_brl: Decimal,
) -> Decimal:  # fmt: skip
    distance = abs(limit_price - stop) * pin.trade_tick_value / pin.trade_tick_size
    return distance + stop_slippage_ticks * pin.trade_tick_value + 2 * per_leg_brl


def _floor_div(numerator: Decimal, denominator: Decimal) -> int:
    if denominator <= 0:
        raise ValueError("ceiling denominators are positive")
    return 0 if numerator <= 0 else int(numerator // denominator)


def normalize_volume(n: int, pin: SpecPin) -> int:
    """The largest admissible volume ``≤ n`` (``volume_min``/``volume_step``/``volume_max``),
    or 0. Always downwards."""
    k = min(n, int(pin.volume_max // 1))
    while k >= 1:
        kd = Decimal(k)
        if kd >= pin.volume_min and (kd - pin.volume_min) % pin.volume_step == 0:
            return k
        k -= 1
    return 0


@dataclass(frozen=True, slots=True)
class SizingResult:
    sizing: B3Sizing
    risk: Decimal | None
    allowance: Decimal | None

    @property
    def n_checked(self) -> int:
        """The volume checks 16–18 are evaluated at (§8.3)."""
        return max(self.sizing.n_final, 1)


def _risk(f: Frame) -> Decimal | None:
    fee = f.ops.fee_schedule
    stop = f.proposal.stop_price
    if not fee.valid or fee.per_leg_brl is None or stop is None:
        return None
    return risk_per_contract_brl(
        limit_price=f.limit_price, stop=stop, pin=f.spec.pin,
        stop_slippage_ticks=f.limits.stop_slippage_ticks, per_leg_brl=fee.per_leg_brl,
    )  # fmt: skip


def _caps(f: Frame, risk: Decimal | None, allowance: Decimal | None) -> dict[str, int | None]:
    lim, acc = f.limits, f.account
    one = f.margin.per_volume.get(1) if f.margin.read_ok else None
    margin_ok = one is not None and one > 0
    free_ok = margin_ok and acc.read_ok and acc.currency == "BRL" and acc.margin_free is not None
    return {
        "requested": max(f.proposal.requested_contracts, 0),
        "max_contracts_per_order": lim.max_contracts_per_order,
        "max_contracts_per_position": lim.max_contracts_per_position,
        "alloc_margin": _floor_div(lim.alloc_per_trade_brl, one) if margin_ok and one else None,
        "free_margin": (
            _floor_div((acc.margin_free or _ZERO) * lim.margin_use_max_pct, one)
            if free_ok and one else None
        ),
        "trade_risk_cap": _floor_div(lim.max_loss_per_trade_brl, risk) if risk else None,
        "daily_allowance": (
            _floor_div(allowance, risk) if risk and allowance is not None else None
        ),
    }  # fmt: skip


def compute_sizing(f: Frame, loss: Decimal | None, effective: KillSwitchState) -> SizingResult:
    risk = _risk(f)
    allowance = None if loss is None else f.limits.daily_loss_limit_brl - loss
    caps = _caps(f, risk, allowance)
    n_raw: int | None = None
    n_final = 0
    binding: str | None = None
    if all(v is not None for v in caps.values()):
        known = {k: v for k, v in caps.items() if v is not None}
        n_raw = min(known.values())
        binding = next(k for k in CAP_ORDER if known[k] == n_raw)
        n = n_raw
        if effective is KillSwitchState.WARNING:
            halved = halve_for_warning(n)
            if halved != n:
                binding = "warning_halving"
            n = halved
        n_final = normalize_volume(n, f.spec.pin)
        if n_final != n:
            binding = "volume_step"
    sizing = B3Sizing(
        caps=caps,
        n_raw=n_raw,
        n_final=n_final,
        binding_constraint=binding,
        risk_per_contract_brl=risk,
        risk_modeled_brl=None if risk is None else n_final * risk,
        allowance_brl=allowance,
        limit_price=f.limit_price,
    )
    return SizingResult(sizing=sizing, risk=risk, allowance=allowance)


def _risk_unavailable(cid: int, f: Frame) -> B3Check:
    fee = f.ops.fee_schedule
    if not fee.valid or fee.per_leg_brl is None:
        return check_unavailable(
            cid, "fee_schedule_missing", message="no fee table with source and date"
        )
    return check_unavailable(
        cid, "upstream_unavailable:15", message="no stop to measure the risk to"
    )


def check_trade_risk_vs_allowance(f: Frame, done: Done, s: SizingResult) -> B3Check:
    if s.risk is None:
        return _risk_unavailable(16, f)
    if upstream(done, 14) or s.allowance is None:
        return check_unavailable(16, "upstream_unavailable:14")
    modelled = s.n_checked * s.risk
    msg = f"{s.n_checked} contract(s) x {s.risk}"
    if modelled <= s.allowance:
        return check_passed(16, value=modelled, limit=s.allowance, message=msg)
    return check_failed(16, "trade_risk_exceeds_daily_allowance", value=modelled, limit=s.allowance,
                        message=msg)  # fmt: skip


def check_trade_risk_cap(f: Frame, s: SizingResult) -> B3Check:
    if s.risk is None:
        return _risk_unavailable(17, f)
    cap = f.limits.max_loss_per_trade_brl
    modelled = s.n_checked * s.risk
    if modelled <= cap:
        return check_passed(17, value=modelled, limit=cap)
    return check_failed(17, "trade_risk_exceeds_cap", value=modelled, limit=cap)


def check_margin(f: Frame, done: Done, s: SizingResult) -> B3Check:
    acc, lim, n = f.account, f.limits, s.n_checked
    if upstream(done, 2):
        return check_unavailable(18, "upstream_unavailable:2", value=n)
    if acc.currency != "BRL":
        return check_failed(18, "account_currency_not_brl", value=acc.currency, limit="BRL")
    if acc.margin_mode != f.spec.pin.account_margin_mode:
        return check_failed(18, "margin_mode_changed", value=acc.margin_mode,
                            limit=f.spec.pin.account_margin_mode)  # fmt: skip
    needed = f.margin.per_volume.get(n) if f.margin.read_ok else None
    verdict = f.margin.order_check.get(n) if f.margin.read_ok else None
    if needed is None or needed <= 0 or verdict is None:
        return check_unavailable(18, "margin_unavailable", value=n,
                                 message=f"no usable (positive) margin or order_check for volume {n}")  # fmt: skip
    free_cap = (acc.margin_free or _ZERO) * lim.margin_use_max_pct
    if needed > lim.alloc_per_trade_brl:
        return check_failed(
            18, "margin_exceeds_allocation", value=needed, limit=lim.alloc_per_trade_brl
        )
    if needed > free_cap:
        return check_failed(18, "margin_exceeds_free_margin", value=needed, limit=free_cap)
    if not verdict.ok:
        return check_failed(18, "order_check_refused", value=n, message=verdict.reason or "")
    return check_passed(18, value=n, limit=min(lim.alloc_per_trade_brl, free_cap),
                        message=f"margin {needed} for {n} contract(s)")  # fmt: skip
