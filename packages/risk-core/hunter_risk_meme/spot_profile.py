"""T4.74-2 — the **spot** admission profile (``docs/RISK_ENGINE_MEME.md`` §19;
design ``docs/design/spot1-lab-solana.md`` §2–§3): a Lab signal (Binance
``mean_reversion``) bought on Solana through Jupiter with the meme wallet.

Same engine, same doctrine, no curve: none of §4's coin checks run. What runs is
the wallet (kill switch, status, daily loss with the treasury inflow, wallet cap,
the global open cap over every lane), the desk's slots, the signal, parity and
impact (a market vs a homonym), what the trade pays in R, and the "ticket or
nothing" sizing: the ticket is the request **and** a ceiling; any ceiling below it
refuses ``below_ticket:<binding_constraint>``. Pure (the instant is ``now`` or
``wallet.as_of``); every check recorded; a missing input refuses ``*_unavailable``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Final

from pydantic import Field, model_validator

from hunter_risk_meme.base import MemeModel
from hunter_risk_meme.checks import kill_switch_check
from hunter_risk_meme.checks_wallet import (
    concurrent_positions_check,
    daily_loss_check,
    wallet_cap_check,
)
from hunter_risk_meme.decision import (
    Counterfactual,
    LimitCap,
    MemeCheck,
    MemeDecision,
    MemeSizing,
    check,
    unavailable,
)
from hunter_risk_meme.inputs import MemeKillSwitchInputs, MemeWalletState
from hunter_risk_meme.kill_switch import assess
from hunter_risk_meme.limits import MemeLimits

# fmt: off
__all__ = [
    "SPOT_CAP_ORDER", "SPOT_CHECK_NAMES", "SPOT_LANE", "SPOT_REFUSAL_NAMES",
    "MemeSpotProfile", "SpotSignalInputs", "evaluate_spot_entry",
]

SPOT_LANE: Final = "spot"
"""``OpenMemePosition.lane`` / ``PendingMemeIntent.lane`` of what this desk opened."""
BELOW_TICKET: Final = "below_ticket"
"""Prefix of the sizing refusal: ``below_ticket:<binding_constraint>``."""
SPOT_ROUND_TRIP_PCT: Final = Decimal("0.003")
"""Design §3: the round trip's proportional cost (Jupiter fees + spread); two legs pay twice."""
SPOT_LEGS: Final = Decimal(2)

SPOT_CHECK_NAMES: Final[tuple[str, ...]] = (
    "kill_switch", "wallet_status", "daily_loss", "wallet_cap", "concurrent_positions",
    "spot1_open_cap", "duplicate_market", "signal_stale", "signal_expired", "geometry_invalid",
    "parity", "impact", "fee_caps", "cost_r", "sizing",
)
"""The checks of §19, in evaluation order — always all of them, in this order."""

SPOT_REFUSAL_NAMES: Final[frozenset[str]] = frozenset({
    "kill_switch_blocked", "daily_loss_cap_latched", "wallet_inactive", "marks_incomplete",
    "daily_loss_cap_reached", "wallet_over_max_sol", "wallet_unrecognized_holdings",
    "max_open_positions", "spot_max_open_reached", "duplicate_market", "signal_stale",
    "signal_expired", "geometry_invalid", "parity_above_cap", "parity_unavailable",
    "impact_above_cap", "impact_unavailable", "priority_fee_above_cap", "cost_above_r_cap",
    "cost_unavailable", "sizing_unavailable", "signal_clock_skew",
})
"""Every fixed refusal name; the sizing's is dynamic (``below_ticket:<binding cap>``)."""

SPOT_CAP_ORDER: Final[tuple[str, ...]] = (
    "requested", "trade_cap", "daily_cap", "wallet_cap", "available", "kill_switch_multiplier",
)
"""§5's order for this profile's ceilings; ``kill_switch_multiplier`` constrains only below one."""
# fmt: on

_ZERO = Decimal(0)
_ONE = Decimal(1)
_LAMPORT = Decimal("0.000000001")
_MICROSECOND = timedelta(microseconds=1)
_MICROS_PER_S = Decimal(1_000_000)
_NO_PARTICIPATION = Counterfactual(
    name="size_without_participation", unavailable_reason="none in spot"
)


class MemeSpotProfile(MemeModel):
    """The desk's numbers (``SPOT1_*``, read by the executor's ``spot_config``; nothing
    here reads an environment), fractions like ``MemeLimits`` (``0.03`` = 3 %). Defaults:
    ticket 0,05 (clamped by the scope at the caller, by ``max_sol_per_trade`` here), 3 open
    (``lane = spot`` + pending), parity 0,03, impact 0,005, cost 0,5 R, age 180 s."""

    ticket_sol: Decimal = Field(gt=0)
    max_open: int = Field(ge=1)
    max_parity_pct: Decimal = Field(gt=0, le=1)
    max_impact_pct: Decimal = Field(gt=0, le=1)
    max_cost_r: Decimal = Field(gt=0)
    max_signal_age_s: int = Field(ge=1)


class SpotSignalInputs(MemeModel):
    """One Lab signal as read, plus the caller's two market readings: ``parity_ratio`` =
    ``jup_usd ÷ bin_usd`` (design §2; ``None`` with ``parity_reason``) and the buy quote's
    adverse ``quote_impact_pct`` ≥ 0 (``None`` = no quote); ``priority_fee_sol`` is per leg."""

    signal_id: str = Field(min_length=1)
    market_symbol: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    reference_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    target1_price: Decimal = Field(gt=0)
    emitted_at: datetime
    expires_at: datetime
    parity_ratio: Decimal | None = Field(default=None, gt=0)
    parity_reason: str | None = None
    quote_impact_pct: Decimal | None = Field(default=None, ge=0)
    priority_fee_sol: Decimal = Field(ge=0)
    open_spot_markets: tuple[str, ...] = ()
    pending_spot_markets: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _stamped(self) -> SpotSignalInputs:
        if self.emitted_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("emitted_at and expires_at must be timezone-aware")
        return self

    @property
    def stop_frac(self) -> Decimal:
        return (self.reference_price - self.stop_price) / self.reference_price

    @property
    def target_frac(self) -> Decimal:
        return (self.target1_price - self.reference_price) / self.reference_price


def _fmt(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _quantize(value: Decimal) -> Decimal:
    return max(_ZERO, value).quantize(_LAMPORT, rounding=ROUND_DOWN)


def _age_s(now: datetime, stamp: datetime) -> Decimal:  # exact: integer microseconds
    return Decimal((now - stamp) // _MICROSECOND) / _MICROS_PER_S


def wallet_status_check(wallet: MemeWalletState) -> MemeCheck:
    refusal = "wallet_inactive" if not wallet.is_active else "marks_incomplete"
    return check("wallet_status", wallet.is_active and wallet.marks_complete, refusal)


def spot_open_cap_check(wallet: MemeWalletState, profile: MemeSpotProfile) -> MemeCheck:
    """The desk's own cap over ``lane = spot`` only; the global cap still counts every slot."""
    positions = sum(1 for p in wallet.positions if p.lane == SPOT_LANE)
    pending = sum(1 for i in wallet.pending_intents if i.lane == SPOT_LANE)
    n, cap = Decimal(positions + pending), Decimal(profile.max_open)
    ok, note = n < cap, f"spot positions={positions} pending={pending}"
    return check("spot1_open_cap", ok, "spot_max_open_reached", value=n, limit=cap, message=note)


def duplicate_market_check(wallet: MemeWalletState, signal: SpotSignalInputs) -> MemeCheck:
    """One per market: open **or** pending, by symbol (the desk's rows) and by mint (any lane)."""
    hits = (
        ("market_open", signal.market_symbol in signal.open_spot_markets),
        ("market_pending", signal.market_symbol in signal.pending_spot_markets),
        ("mint_held", any(p.mint == signal.mint for p in wallet.positions)),
        ("mint_pending", any(i.mint == signal.mint for i in wallet.pending_intents)),
    )
    reasons = [tag for tag, hit in hits if hit]
    note = f"{signal.market_symbol}:" + ",".join(reasons)
    return check("duplicate_market", not reasons, "duplicate_market", message=note)


def signal_checks(
    signal: SpotSignalInputs, profile: MemeSpotProfile, at: datetime, skew_s: int
) -> list[MemeCheck]:
    """``skew_s`` is ``limits.clock_skew_tolerance_s``: a stamp further in the future is a
    clock problem (``signal_clock_skew``), never a fresh signal."""
    age, left = _age_s(at, signal.emitted_at), _age_s(signal.expires_at, at)
    stop_frac, target_frac = signal.stop_frac, signal.target_frac
    max_age, skew = Decimal(profile.max_signal_age_s), Decimal(skew_s)
    fresh, why = -skew <= age <= max_age, "signal_clock_skew" if age < -skew else "signal_stale"
    stamps = {"input_ts": signal.emitted_at.isoformat()}
    expiry = {"input_ts": signal.expires_at.isoformat(), "message": "seconds until expires_at"}
    ref = _fmt(signal.reference_price)
    geometry = f"ref={ref} stop_frac={_fmt(stop_frac)} target_frac={_fmt(target_frac)}"
    return [
        check("signal_stale", fresh, why, value=age, limit=max_age, **stamps),
        check("signal_expired", left > _ZERO, "signal_expired", value=left, limit=_ZERO, **expiry),
        check(
            "geometry_invalid",
            stop_frac > _ZERO and target_frac > _ZERO,
            "geometry_invalid",
            value=stop_frac,
            limit=_ZERO,
            message=geometry,
        ),
    ]


def parity_check(signal: SpotSignalInputs, profile: MemeSpotProfile) -> MemeCheck:
    cap = profile.max_parity_pct
    if signal.parity_ratio is None:
        reason = signal.parity_reason or "parity_unavailable"
        return unavailable("parity", "parity_unavailable", reason, limit=cap)
    dev = abs(signal.parity_ratio - _ONE)
    note = f"jup_usd/bin_usd={_fmt(signal.parity_ratio)}"
    return check("parity", dev <= cap, "parity_above_cap", value=dev, limit=cap, message=note)


def impact_check(signal: SpotSignalInputs, profile: MemeSpotProfile) -> MemeCheck:
    cap, impact = profile.max_impact_pct, signal.quote_impact_pct
    if impact is None:
        return unavailable("impact", "impact_unavailable", "no buy quote", limit=cap)
    return check("impact", impact <= cap, "impact_above_cap", value=impact, limit=cap)


def fee_caps_check(signal: SpotSignalInputs, limits: MemeLimits, ticket: Decimal) -> MemeCheck:
    relative = ticket * limits.max_priority_fee_pct_of_trade
    cap, fee = min(limits.max_priority_fee_sol, relative), signal.priority_fee_sol
    ok, note = fee <= cap, f"per leg; abs={_fmt(limits.max_priority_fee_sol)} rel={_fmt(relative)}"
    return check("fee_caps", ok, "priority_fee_above_cap", value=fee, limit=cap, message=note)


def cost_r_check(
    signal: SpotSignalInputs, profile: MemeSpotProfile, ticket: Decimal, leg_fee: Decimal
) -> MemeCheck:
    """Design §3: ``2 × leg_fee + ticket × (2 × impact + 0,003)`` over ``ticket × stop_frac``;
    ``leg_fee`` = priority + network fee of one leg (the network fee is the one cost §3 omits)."""
    impact = signal.quote_impact_pct
    if impact is None:
        return unavailable("cost_r", "cost_unavailable", "not computed: impact_unavailable")
    if signal.stop_frac <= _ZERO:
        return unavailable("cost_r", "cost_unavailable", "not computed: geometry_invalid")
    est = SPOT_LEGS * leg_fee + ticket * (SPOT_LEGS * impact + SPOT_ROUND_TRIP_PCT)
    r_unit = ticket * signal.stop_frac
    ratio, cap = est / r_unit, profile.max_cost_r
    note = f"est_cost_sol={_fmt(est)} r_unit_sol={_fmt(r_unit)} leg_fee_sol={_fmt(leg_fee)}"
    note += f" impact={_fmt(impact)} round_trip={_fmt(SPOT_ROUND_TRIP_PCT)} ticket={_fmt(ticket)}"
    return check("cost_r", ratio <= cap, "cost_above_r_cap", value=ratio, limit=cap, message=note)


def size_spot_entry(
    wallet: MemeWalletState,
    limits: MemeLimits,
    profile: MemeSpotProfile,
    signal: SpotSignalInputs,
    ticket: Decimal,
    *,
    multiplier: Decimal,
) -> tuple[MemeSizing | None, MemeCheck]:
    """Ticket or nothing (§5's ceilings, ``requested`` = the ticket): ``min(caps) < ticket``
    refuses ``below_ticket:<binding>``; approved ⇒ ``sol_final == ticket``."""
    if signal.quote_impact_pct is None:
        return None, unavailable("sizing", "sizing_unavailable", "not sized: impact_unavailable")
    costs = limits.ata_rent_sol + SPOT_LEGS * (signal.priority_fee_sol + limits.network_fee_sol)
    committed = sum((p.sol_spent for p in wallet.positions), _ZERO) + wallet.reserved_sol
    daily = _quantize(limits.daily_loss_cap_sol - wallet.daily_loss_sol - committed)
    daily_note = f"cap − loss today {_fmt(wallet.daily_loss_sol)} − committed by open positions"
    daily_note += f" of every lane + reservations {_fmt(committed)}"
    room = _quantize(limits.wallet_max_sol - wallet.exposure_total_sol)
    free = _quantize(wallet.available_sol - costs)
    free_note = f"balance − reservations − rent reserved − fixed costs {_fmt(costs)}"
    halved = None if multiplier >= _ONE else _quantize(ticket * multiplier)
    halved_note = "ticket × multiplier; constrains only under WARNING"
    clamp = "" if ticket == profile.ticket_sol else f" clamped from {_fmt(profile.ticket_sol)}"
    caps = (
        LimitCap(name="requested", sol=ticket, limit=ticket, detail=f"ticket{clamp}"),
        LimitCap(name="trade_cap", sol=limits.max_sol_per_trade, limit=limits.max_sol_per_trade),
        LimitCap(name="daily_cap", sol=daily, limit=limits.daily_loss_cap_sol, detail=daily_note),
        LimitCap(name="wallet_cap", sol=room, limit=limits.wallet_max_sol),
        LimitCap(name="available", sol=free, limit=wallet.available_sol, detail=free_note),
        LimitCap(name="kill_switch_multiplier", sol=halved, limit=multiplier, detail=halved_note),
    )
    constraining = [c for c in caps if c.sol is not None]
    binding = min(constraining, key=lambda c: c.sol or _ZERO)
    final = binding.sol or _ZERO
    tied = tuple(c.name for c in constraining if c is not binding and c.sol == final)
    plain = [c.sol or _ZERO for c in constraining if c.name != "kill_switch_multiplier"]
    unmultiplied = _quantize(min(plain))
    sizing = MemeSizing(
        requested_sol=ticket,
        caps=caps,
        binding_limit=binding,
        binding_constraint=binding.name,
        tied_limits=tied,
        size_without_multipliers=Counterfactual(name="size_without_multipliers", sol=unmultiplied),
        size_without_participation=_NO_PARTICIPATION,
        sol_before_multiplier=unmultiplied,
        kill_switch_multiplier=multiplier,
        sol_final=final,
        fixed_costs_sol=costs,
        price_impact_pct=signal.quote_impact_pct,
        max_sol_cost_sol=final,
    )
    refusal, note = f"{BELOW_TICKET}:{binding.name}", f"ticket or nothing; binding={binding.name}"
    return sizing, check(
        "sizing", final >= ticket, refusal, value=final, limit=ticket, message=note
    )


def evaluate_spot_entry(
    wallet: MemeWalletState,
    limits: MemeLimits,
    profile: MemeSpotProfile,
    signal: SpotSignalInputs,
    kill_switch: MemeKillSwitchInputs,
    now: datetime | None = None,
) -> MemeDecision:
    """§19: :data:`SPOT_CHECK_NAMES` in order, all recorded, then the sizing.
    ``now`` defaults to ``wallet.as_of`` (one instant per decision)."""
    instant = wallet.as_of if now is None else now
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    ticket = min(profile.ticket_sol, limits.max_sol_per_trade)
    ks = assess(wallet, limits, kill_switch)
    checks: list[MemeCheck] = [
        kill_switch_check(ks.effective, kill_switch.daily_loss_latched),
        wallet_status_check(wallet),
        daily_loss_check(wallet, limits),
        wallet_cap_check(wallet, limits),
        concurrent_positions_check(wallet, limits),
        spot_open_cap_check(wallet, profile),
        duplicate_market_check(wallet, signal),
        *signal_checks(signal, profile, instant, limits.clock_skew_tolerance_s),
        parity_check(signal, profile),
        impact_check(signal, profile),
        fee_caps_check(signal, limits, ticket),
        cost_r_check(signal, profile, ticket, signal.priority_fee_sol + limits.network_fee_sol),
    ]
    sizing, sizing_check = size_spot_entry(
        wallet, limits, profile, signal, ticket, multiplier=ks.entry_size_multiplier
    )
    checks.append(sizing_check)
    return MemeDecision(
        approved=all(c.passed for c in checks) and sizing is not None,
        kind="entry",
        proposal_id=signal.signal_id,
        wallet_id=wallet.wallet_id,
        mint=signal.mint,
        limits_profile=limits.profile,
        effective_kill_switch=ks.effective,
        cancel_pending=ks.cancel_pending,
        checks=tuple(checks),
        sizing=sizing,
        profile="spot",
    )
