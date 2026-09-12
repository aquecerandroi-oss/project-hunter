"""Repository rows → ``schemas/meme_desk.py`` payloads, and the one piece of
pricing the API does itself: a manual proposal's ``quote`` (T4.7). Split out
of ``services/meme_desk.py`` for the 350-line budget: this module derives and
maps. **JSONB is read tolerantly** — ``suggested``/``decision``/``params``/
``entry``/``exit``/``quote`` are the loop's (T4.6) or this API's own writes; a
missing key is ``None`` in the payload, never ``0``, never a guess (DESIGN.md §2).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from hunter_api.repositories.meme_desk_rows import (
    BetRow,
    CommandRow,
    CurveQuoteRow,
    DeskRow,
    RuleSetBalanceRow,
    RuleSetRow,
    SolUsdQuoteRow,
    TokenIdentity,
)
from hunter_api.schemas.meme_desk import (
    BetOut,
    CommandOut,
    DeskParamsIn,
    DeskParamsOut,
    DeskRowOut,
    DeskSummaryOut,
    QuoteOut,
    RuleSetBalanceOut,
    RuleSetOut,
    SolUsdQuoteOut,
    TokenIdentityOut,
)
from hunter_core.domain.types import ensure_utc
from hunter_indicators.meme.curve import CurveReserves, quote_buy

__all__ = [
    "MANUAL_QUOTE_FEE_PCT",
    "build_command_out",
    "build_desk_row_out",
    "build_manual_quote",
    "build_summary",
    "decimal_or_none",
    "decision_json",
    "params_from_json",
]

MANUAL_QUOTE_FEE_PCT: Final = Decimal("1.75")
"""Contract §Tabelas (``meme_proposals.quote``): "custo cotado para
``size_sol`` **com** taxa 1,75 %" — the curve's 1,25 % (``pump.fun/docs/fees``,
``hunter_indicators.meme.curve.CURVE_TRADE_FEE_PCT``) plus PumpPortal's
0,5 % Local Transaction API cut (RISK_ENGINE_MEME.md §15), the execution
path the paper simulator prices against."""


def decimal_or_none(value: object) -> Decimal | None:
    """A JSONB number written as string or number; anything else is ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    if isinstance(value, float):
        return Decimal(str(value))
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return None
    return None


def _datetime_or_none(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        try:
            return ensure_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def params_from_json(raw: dict[str, Any] | None) -> DeskParamsOut:
    data = raw or {}
    holds = data.get("exit_on_migration")  # T4.11: a switch is a bool or nothing
    return DeskParamsOut(
        size_sol=decimal_or_none(data.get("size_sol")),
        target_x=decimal_or_none(data.get("target_x")),
        trailing_pct=decimal_or_none(data.get("trailing_pct")),
        max_hold_s=_int_or_none(data.get("max_hold_s")),
        note=_str_or_none(data.get("note")),
        exit_on_migration=holds if isinstance(holds, bool) else None,
        trailing_arm_x=decimal_or_none(data.get("trailing_arm_x")),
    )


def decision_json(body: DeskParamsIn) -> dict[str, Any]:
    """Contract §Tabelas: ``decision = {size_sol, target_x, trailing_pct,
    max_hold_s, note}`` — money as strings, the JSONB convention every other
    table of this product already uses."""
    return {
        "size_sol": str(body.size_sol),
        "target_x": str(body.target_x),
        "trailing_pct": str(body.trailing_pct),
        "max_hold_s": body.max_hold_s,
        "note": body.note,
    }


def _quote_from_json(raw: dict[str, Any] | None) -> QuoteOut:
    data = raw or {}
    return QuoteOut(
        observed_at=_datetime_or_none(data.get("observed_at")),
        source=_str_or_none(data.get("source")),
        mcap_sol=decimal_or_none(data.get("mcap_sol")),
        curve_progress_pct=decimal_or_none(data.get("curve_progress_pct")),
        price_sol_per_token=decimal_or_none(data.get("price_sol_per_token")),
        size_sol=decimal_or_none(data.get("size_sol")),
        fee_pct=decimal_or_none(data.get("fee_pct")),
        fee_sol=decimal_or_none(data.get("fee_sol")),
        cost_sol=decimal_or_none(data.get("cost_sol")),
        tokens=decimal_or_none(data.get("tokens")),
        reason=_str_or_none(data.get("reason")),
    )


def build_manual_quote(quote: CurveQuoteRow | None, size_sol: Decimal) -> dict[str, Any]:
    """The ``quote`` JSONB of a manual proposal, priced on the mint's latest
    snapshot with ``hunter_indicators.meme.curve.quote_buy`` — the same
    arithmetic T4.5's paper simulator uses, so the cost the operator sees
    is the cost the loop will book. No snapshot yet → the size/fee half is
    still real; the price half is ``None`` with ``reason``."""
    fee_sol = size_sol * MANUAL_QUOTE_FEE_PCT / Decimal(100)
    base: dict[str, Any] = {
        "size_sol": str(size_sol),
        "fee_pct": str(MANUAL_QUOTE_FEE_PCT),
        "fee_sol": str(fee_sol),
        "cost_sol": str(size_sol),
    }
    if quote is None:
        return {
            **base,
            "observed_at": None,
            "source": None,
            "mcap_sol": None,
            "curve_progress_pct": None,
            "price_sol_per_token": None,
            "tokens": None,
            "reason": "no_snapshot_yet",
        }
    try:
        reserves = CurveReserves(
            virtual_sol_reserves=quote.virtual_sol_reserves,
            virtual_token_reserves=quote.virtual_token_reserves,
            real_token_reserves=quote.real_token_reserves,
            complete=quote.complete,
        )
        priced = quote_buy(reserves, size_sol, MANUAL_QUOTE_FEE_PCT)
    except (ValueError, ArithmeticError):
        return {
            **base,
            "observed_at": quote.observed_at.isoformat(),
            "source": quote.source,
            "mcap_sol": None if quote.mcap_sol is None else str(quote.mcap_sol),
            "curve_progress_pct": None,
            "price_sol_per_token": None,
            "tokens": None,
            "reason": "unpriceable_reserves",
        }
    return {
        **base,
        "fee_sol": str(priced.fee_sol),
        "cost_sol": str(priced.total_sol),
        "tokens": str(priced.tokens),
        "observed_at": quote.observed_at.isoformat(),
        "source": quote.source,
        "mcap_sol": None if quote.mcap_sol is None else str(quote.mcap_sol),
        "curve_progress_pct": None,
        "price_sol_per_token": str(quote.virtual_sol_reserves / quote.virtual_token_reserves),
        "reason": None,
    }


def _token_out(token: TokenIdentity) -> TokenIdentityOut:
    return TokenIdentityOut(
        mint=token.mint,
        name=token.name,
        symbol=token.symbol,
        creator=token.creator,
        created_at=token.created_at,
        mayhem_enabled=token.mayhem_enabled,
        mayhem_state=token.mayhem_state,
        completed_at=token.completed_at,
        migrated_at=token.migrated_at,
    )


def _rule_set_out(rule_set: RuleSetRow) -> RuleSetOut:
    return RuleSetOut(
        id=rule_set.id,
        name=rule_set.name,
        version=rule_set.version,
        kind=rule_set.kind,
        max_sol_per_bet=decimal_or_none(rule_set.params.get("max_sol_per_bet")),
    )


def _bet_out(bet: BetRow) -> BetOut:
    params = params_from_json(bet.params)
    exit_data = bet.exit or {}
    deadline = (
        bet.entry_at + timedelta(seconds=params.max_hold_s)
        if params.max_hold_s is not None
        else None
    )
    sol_spent = decimal_or_none(bet.entry.get("sol_spent"))
    unrealized = (
        bet.mark_sol - sol_spent
        if bet.status == "open" and bet.mark_sol is not None and sol_spent is not None
        else None
    )
    unrealized_r = (
        unrealized / bet.initial_risk_sol
        if unrealized is not None and bet.initial_risk_sol > 0
        else None
    )
    return BetOut(
        id=bet.id,
        status=bet.status,
        mode=bet.mode,
        entry_at=bet.entry_at,
        sol_spent=sol_spent,
        fee_sol=decimal_or_none(bet.entry.get("fee_sol")),
        tokens=decimal_or_none(bet.entry.get("tokens")),
        initial_risk_sol=bet.initial_risk_sol,
        params=params,
        hold_deadline_at=deadline,
        mark_sol=bet.mark_sol,
        mark_at=bet.mark_at,
        high_water_x=bet.high_water_x,
        pnl_sol=bet.pnl_sol,
        r_multiple=bet.r_multiple,
        unrealized_pnl_sol=unrealized,
        unrealized_r=unrealized_r,
        exit_at=bet.exit_at,
        exit_reason=_str_or_none(exit_data.get("reason")),
        sol_received=decimal_or_none(exit_data.get("sol_received")),
        sol_usd_at_entry=bet.sol_usd_at_entry,
        sol_usd_at_exit=bet.sol_usd_at_exit,
        leg=bet.leg,
        parent_bet_id=bet.parent_bet_id,
        mark_source=bet.mark_source,
        mark_stale_s=bet.mark_stale_s,
        outcome_quality=bet.outcome_quality,
        outcome_quality_reason=bet.outcome_quality_reason,
        decision_to_fill_s=_int_or_none(bet.entry.get("decision_to_fill_s")),
    )


def build_desk_row_out(row: DeskRow) -> DeskRowOut:
    p = row.proposal
    return DeskRowOut(
        id=p.id,
        mint=p.mint,
        origin=p.origin,
        status=p.status,
        proposed_at=p.proposed_at,
        expires_at=p.expires_at,
        features_end_time=p.features_end_time,
        quote=_quote_from_json(p.quote),
        reasons=list(p.reasons or []),
        suggested=params_from_json(p.suggested),
        decision=params_from_json(p.decision) if p.decision is not None else None,
        decided_by=p.decided_by,
        decided_at=p.decided_at,
        refusal=p.refusal,
        token=_token_out(row.token) if row.token is not None else None,
        rule_set=_rule_set_out(row.rule_set) if row.rule_set is not None else None,
        bet=_bet_out(row.bet) if row.bet is not None else None,
    )


def build_command_out(row: CommandRow) -> CommandOut:
    return CommandOut(
        id=row.id,
        command=row.command,
        bet_id=row.bet_id,
        proposal_id=row.proposal_id,
        issued_by=row.issued_by,
        issued_at=row.issued_at,
        applied_at=row.applied_at,
        result=row.result,
    )


def _balance_out(row: RuleSetBalanceRow) -> RuleSetBalanceOut:
    wallet_max = decimal_or_none(row.rule_set.params.get("wallet_max_sol"))
    balance = wallet_max + row.realized_total_sol - row.open_sol if wallet_max is not None else None
    return RuleSetBalanceOut(
        rule_set=_rule_set_out(row.rule_set),
        wallet_max_sol=wallet_max,
        daily_loss_cap_sol=decimal_or_none(row.rule_set.params.get("daily_loss_cap_sol")),
        open_sol=row.open_sol,
        open_bets=row.open_bets,
        realized_today_sol=row.realized_today_sol,
        closed_today=row.closed_today,
        realized_total_sol=row.realized_total_sol,
        balance_sol=balance,
        balance_reason=None if wallet_max is not None else "wallet_max_sol_missing",
    )


def build_summary(
    balances: list[RuleSetBalanceRow], sol_usd: SolUsdQuoteRow | None
) -> DeskSummaryOut:
    rule_sets = [_balance_out(b) for b in balances]
    day_pnl = sum((b.realized_today_sol for b in balances), Decimal(0))
    return DeskSummaryOut(
        rule_sets=rule_sets,
        day_pnl_sol=day_pnl,
        sol_usd=(
            SolUsdQuoteOut(
                rate=sol_usd.rate, observed_at=sol_usd.observed_at, source=sol_usd.source
            )
            if sol_usd is not None
            else None
        ),
        sol_usd_reason=None if sol_usd is not None else "no_observed_quote",
    )
