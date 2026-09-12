"""Sizing — the minimum of the ceilings, with the binding one published (§5) — and
checks 21–25.

**On a curve the risk of a buy is the whole spend**, so every ceiling is in SOL
and the daily cap counts what open positions already commit. ``sol_final`` is the
total the buy takes from the wallet for the curve (curve amount + curve fees);
the fixed execution costs (network fee, priority fee, tip, ATA rent) are
accounted separately and must also fit ``available_sol`` (check 24).

Price impact is exact from the reserves: a pre-fee spend ``s`` on a curve with
virtual SOL reserve ``v`` moves the average price by ``s / v`` against the
marginal price, so the impact ceiling is ``max_price_impact_pct × v`` (§4, check 22).
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Final

from hunter_risk_meme.decision import (
    Counterfactual,
    LimitCap,
    MemeCheck,
    MemeSizing,
    check,
    unavailable,
)
from hunter_risk_meme.inputs import CurveState, MemeContext, MemeEntryProposal, MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = ["CAP_ORDER", "LAMPORTS_PER_SOL", "size_entry"]

CAP_ORDER: Final[tuple[str, ...]] = (
    "requested",
    "trade_cap",
    "daily_cap",
    "mint_cap",
    "wallet_cap",
    "participation",
    "impact",
    "available",
)
"""Stable tie-break order (§5): the first name wins, the rest are ``tied_limits``."""

LAMPORTS_PER_SOL = Decimal(1_000_000_000)
_ZERO = Decimal(0)
_LAMPORT = Decimal("0.000000001")
_ONE = Decimal(1)


def _quantize(value: Decimal) -> Decimal:
    return max(_ZERO, value).quantize(_LAMPORT, rounding=ROUND_DOWN)


def fixed_costs(proposal: MemeEntryProposal, limits: MemeLimits, *, creates_ata: bool) -> Decimal:
    rent = limits.ata_rent_sol if creates_ata else _ZERO
    return limits.network_fee_sol + proposal.priority_fee_sol + proposal.jito_tip_sol + rent


def _caps(
    proposal: MemeEntryProposal,
    wallet: MemeWalletState,
    limits: MemeLimits,
    curve: CurveState,
    context: MemeContext,
    *,
    costs: Decimal,
    curve_fee_pct: Decimal,
) -> tuple[list[LimitCap], MemeCheck]:
    """Every ceiling in SOL, and the participation check that may be unavailable."""
    committed = sum((p.sol_spent for p in wallet.positions), _ZERO) + wallet.reserved_sol
    caps = [
        LimitCap(name="requested", sol=proposal.requested_sol, limit=proposal.requested_sol),
        LimitCap(name="trade_cap", sol=limits.max_sol_per_trade, limit=limits.max_sol_per_trade),
        LimitCap(
            name="daily_cap",
            sol=_quantize(limits.daily_loss_cap_sol - wallet.daily_loss_sol - committed),
            limit=limits.daily_loss_cap_sol,
            detail="cap − loss today − loss already committed by open positions",
        ),
        LimitCap(
            name="mint_cap",
            sol=_quantize(
                limits.max_exposure_per_mint_sol - wallet.exposure_for_mint(proposal.mint)
            ),
            limit=limits.max_exposure_per_mint_sol,
        ),
        LimitCap(
            name="wallet_cap",
            sol=_quantize(limits.wallet_max_sol - wallet.exposure_total_sol),
            limit=limits.wallet_max_sol,
        ),
    ]
    if context.organic_volume_1m_sol is None or context.volume_ts is None:
        participation = unavailable(
            "participation",
            "volume_unavailable",
            "organic 1m volume unavailable",
            limit=limits.max_participation_pct,
        )
        caps.append(LimitCap(name="participation", sol=None, detail="volume_unavailable"))
    elif context.volume_window_complete is not True:
        participation = unavailable(
            "participation",
            "volume_window_incomplete",
            "1m window incomplete",
            limit=limits.max_participation_pct,
        )
        caps.append(LimitCap(name="participation", sol=None, detail="volume_window_incomplete"))
    else:
        budget = _quantize(
            limits.max_participation_pct * context.organic_volume_1m_sol
            - context.participation_used_sol
        )
        caps.append(
            LimitCap(
                name="participation",
                sol=budget,
                limit=limits.max_participation_pct,
                detail=f"volume_1m={context.organic_volume_1m_sol} used={context.participation_used_sol}",
            )
        )
        participation = check(
            "participation",
            True,
            "participation_above_cap",
            value=budget,
            limit=limits.max_participation_pct,
            input_ts=context.volume_ts.isoformat(),
        )
    # Impact: pre-fee spend s moves the average price by s/v; the buy's total is s×(1+fee).
    virtual_sol = Decimal(curve.virtual_sol_reserves) / LAMPORTS_PER_SOL
    impact_sol = _quantize(limits.max_price_impact_pct * virtual_sol * (_ONE + curve_fee_pct))
    caps.append(LimitCap(name="impact", sol=impact_sol, limit=limits.max_price_impact_pct))
    caps.append(
        LimitCap(
            name="available",
            sol=_quantize(wallet.available_sol - costs),
            limit=wallet.available_sol,
        )
    )
    return caps, participation


def size_entry(
    proposal: MemeEntryProposal,
    wallet: MemeWalletState,
    limits: MemeLimits,
    curve: CurveState,
    context: MemeContext,
    *,
    kill_switch_multiplier: Decimal,
    curve_fee_pct: Decimal,
    creates_ata: bool,
) -> tuple[MemeSizing | None, list[MemeCheck]]:
    """The §5 formula plus checks 21–25. ``None`` sizing when a ceiling is unavailable."""
    costs = fixed_costs(proposal, limits, creates_ata=creates_ata)
    caps, participation = _caps(
        proposal, wallet, limits, curve, context, costs=costs, curve_fee_pct=curve_fee_pct
    )
    checks: list[MemeCheck] = [participation]
    if participation.refusal is not None:
        for name, refusal in (
            ("price_impact", "price_impact_above_cap"),
            ("sizing", "below_min_sol"),
            ("sol_available", "insufficient_sol"),
            ("exposure_after", "exposure_after_above_cap"),
        ):
            checks.append(unavailable(name, refusal, f"not sized: {participation.refusal}"))
        return None, checks
    ordered = sorted(caps, key=lambda c: CAP_ORDER.index(c.name))
    constraining = [c for c in ordered if c.sol is not None]
    binding = min(constraining, key=lambda c: c.sol or _ZERO)
    gross = binding.sol or _ZERO
    tied = tuple(c.name for c in constraining if c is not binding and c.sol == gross)
    final = _quantize(gross * kill_switch_multiplier)
    without_participation = min(
        (c.sol for c in constraining if c.name != "participation" and c.sol is not None),
        default=None,
    )
    virtual_sol = Decimal(curve.virtual_sol_reserves) / LAMPORTS_PER_SOL
    impact = _ZERO if virtual_sol == 0 else (final / (_ONE + curve_fee_pct)) / virtual_sol
    sizing = MemeSizing(
        requested_sol=proposal.requested_sol,
        caps=tuple(ordered),
        binding_limit=binding,
        binding_constraint=binding.name,
        tied_limits=tied,
        size_without_multipliers=Counterfactual(
            name="size_without_multipliers", sol=_quantize(gross)
        ),
        size_without_participation=Counterfactual(
            name="size_without_participation",
            sol=None if without_participation is None else _quantize(without_participation),
        ),
        sol_before_multiplier=_quantize(gross),
        kill_switch_multiplier=kill_switch_multiplier,
        sol_final=final,
        fixed_costs_sol=costs,
        price_impact_pct=impact,
        max_sol_cost_sol=_quantize(final * (_ONE + proposal.max_slippage_pct)),
    )
    # Checks 21, 22 and 25 cannot be violated by ``final`` — it is the minimum of
    # their ceilings — so each one asks the question that *can* fail: does the
    # ceiling admit at least the minimum tradeable size? A budget that fits no
    # admissible buy is the refusal, named; the size is never rounded up to it.
    by_name = {c.name: c.sol or _ZERO for c in ordered}
    floor = limits.min_trade_sol
    if participation.passed:
        budget = by_name["participation"]
        checks[0] = check(
            "participation",
            budget >= floor and final <= budget,
            "participation_above_cap",
            value=final,
            limit=budget,
            input_ts=participation.input_ts,
        )
    checks.append(
        check(
            "price_impact",
            by_name["impact"] >= floor and impact <= limits.max_price_impact_pct,
            "price_impact_above_cap",
            value=impact,
            limit=limits.max_price_impact_pct,
        )
    )
    checks.append(
        check(
            "sizing",
            final >= floor,
            "below_min_sol",
            value=final,
            limit=floor,
            message=f"binding={binding.name}",
        )
    )
    checks.append(
        check(
            "sol_available",
            by_name["available"] >= floor and final + costs <= wallet.available_sol,
            "insufficient_sol",
            value=final + costs,
            limit=wallet.available_sol,
        )
    )
    after_total = wallet.exposure_total_sol + final
    after_mint = wallet.exposure_for_mint(proposal.mint) + final
    checks.append(
        check(
            "exposure_after",
            by_name["mint_cap"] >= floor
            and by_name["wallet_cap"] >= floor
            and after_total <= limits.wallet_max_sol
            and after_mint <= limits.max_exposure_per_mint_sol,
            "exposure_after_above_cap",
            value=after_total,
            limit=limits.wallet_max_sol,
        )
    )
    return sizing, checks
