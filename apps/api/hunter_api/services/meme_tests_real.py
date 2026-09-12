"""The observed wallet's positions (T4.12, ``meme_wallet_positions``) as rows
of the test record (T4.13) — read **tolerantly**: that table is being built in
parallel and its column list is the brief's, not a frozen contract. Every
field is looked up by the names brief T4.12 §2 gives (with the obvious
synonyms); a column that is not there is ``None`` in the row, never a guess.
A row without the two identity columns (``wallet``, ``mint``) is skipped and
counted in the log, never rendered half-empty.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_api.schemas.meme_tests import (
    REAL_OBSERVED_LABEL,
    LabContextOut,
    TestEntryOut,
    TestExitOut,
    TestRowOut,
    TestRuleSetOut,
)
from hunter_api.services.meme_desk_out import decimal_or_none
from hunter_api.services.meme_tests import exit_reason_label, str_or_none
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger

__all__ = ["real_rows_out", "wallet_label"]

logger = get_logger(__name__)


def wallet_label(wallet: str) -> str:
    """Brief T4.12 §3: the scoreboard's set name for a wallet, ``wallet:<8 chars>``."""
    return f"wallet:{wallet[:8]}"


def _first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _decimal(row: dict[str, Any], *names: str) -> Decimal | None:
    return decimal_or_none(_first(row, *names))


def _datetime(row: dict[str, Any], *names: str) -> datetime | None:
    value = _first(row, *names)
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        try:
            return ensure_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


def _lab_context(row: dict[str, Any]) -> LabContextOut:
    context = _first(row, "lab_context")
    data: dict[str, Any] = dict(context) if isinstance(context, dict) else {}  # type: ignore[arg-type]
    return LabContextOut(
        features_end_time=_datetime(data, "features_end_time", "end_time"),
        features_version=str_or_none(data.get("features_version")),
        reason=None if data else "no_features_row",
        gate_reasons=list(data.get("gate_reasons") or data.get("verdicts") or []),
        line_drawn=None,
        line_reason=str_or_none(_first(row, "line_reason") or data.get("line_reason")),
        support_line_sol=None,
        distance_to_support_pct=None,
        higher_lows=None,
        breakout_15m=None,
        hype_score=decimal_or_none(_first(row, "hype_score") or data.get("hype_score")),
        hype_reason=None,
        creator_sold=None,
        creator_sold_reason=None,
        curve_progress_pct=None,
        progress_reason=None,
        age_minutes=None,
        unique_buyers=None,
        mcap_sol=None,
    )


def _real_row_out(row: dict[str, Any]) -> TestRowOut | None:
    wallet = str_or_none(_first(row, "wallet", "wallet_address", "owner"))
    mint = str_or_none(_first(row, "mint"))
    first_buy_at = _datetime(row, "first_buy_at", "opened_at")
    if wallet is None or mint is None or first_buy_at is None:
        return None
    state = str_or_none(_first(row, "state", "status")) or "open"
    status = "closed" if state == "closed" else "open"
    sol_spent = _decimal(row, "sol_spent", "sol_spent_total")
    sol_received = _decimal(row, "sol_received", "sol_received_total")
    mark_sol = _decimal(row, "mark_sol", "mark_value_sol")
    realized = _decimal(row, "realized_pnl_sol", "pnl_sol")
    last_trade_at = _datetime(row, "last_trade_at", "closed_at")
    exit_at = last_trade_at if status == "closed" else _datetime(row, "mark_at", "marked_at")
    provisional = status != "closed"
    pnl_sol = realized if status == "closed" else _provisional_pnl(mark_sol, sol_spent)
    r_multiple = _decimal(row, "r_multiple", "r")
    if r_multiple is None and pnl_sol is not None and sol_spent is not None and sol_spent > 0:
        r_multiple = pnl_sol / sol_spent
    entry = TestEntryOut(
        at=first_buy_at,
        price_sol_per_token=_decimal(row, "avg_cost_sol_per_token", "average_cost_sol"),
        average_price_sol=_decimal(row, "avg_cost_sol_per_token", "average_cost_sol"),
        mcap_sol=_decimal(row, "entry_mcap_sol"),
        sol_spent=sol_spent,
        tokens=_decimal(row, "tokens_bought", "tokens_total_bought", "tokens"),
        fee_sol=_decimal(row, "fee_sol", "fees_sol"),
        fee_pct=None,
        fill_delay_s=None,
        fill_delay_snapshots=None,
        source="chain",
    )
    exit_ = TestExitOut(
        at=exit_at,
        provisional=provisional,
        price_sol_per_token=None,
        mcap_sol=_decimal(row, "exit_mcap_sol"),
        sol_received=sol_received if status == "closed" else mark_sol,
        fee_sol=None,
        reason=None,
        reason_label=exit_reason_label(None, provisional=provisional),
        trigger="wallet",
        pending_reason=None,
    )
    duration = int((exit_at - first_buy_at).total_seconds()) if exit_at is not None else None
    identifier = _first(row, "id")
    return TestRowOut(
        id=str(identifier) if identifier is not None else f"{wallet}:{mint}",
        kind="real_observed",
        kind_label=REAL_OBSERVED_LABEL,
        bet_id=None,
        proposal_id=None,
        mint=mint,
        token_name=str_or_none(_first(row, "name", "token_name")),
        token_symbol=str_or_none(_first(row, "symbol", "token_symbol")),
        status=status,
        rule_set=TestRuleSetOut(
            name=wallet_label(wallet),
            version=None,
            kind="real_observed",
            label=wallet_label(wallet),
        ),
        leg="single",
        parent_bet_id=None,
        origin="wallet",
        decided_by=None,
        entry=entry,
        exit=exit_,
        duration_s=duration,
        pnl_sol=pnl_sol,
        pnl_usd=None,
        pnl_usd_basis=None,
        pnl_usd_reason="no_exit_quote",
        r_multiple=r_multiple,
        sol_usd_at_entry=None,
        sol_usd_at_exit=None,
        sol_usd_source=None,
        lab_context=_lab_context(row),
        wallet=wallet,
        mark_source=str_or_none(_first(row, "mark_source")),
    )


def _provisional_pnl(mark_sol: Decimal | None, sol_spent: Decimal | None) -> Decimal | None:
    if mark_sol is None or sol_spent is None:
        return None
    return mark_sol - sol_spent


def real_rows_out(rows: list[dict[str, Any]]) -> list[TestRowOut]:
    out: list[TestRowOut] = []
    skipped = 0
    for row in rows:
        built = _real_row_out(row)
        if built is None:
            skipped += 1
            continue
        out.append(built)
    if skipped:
        logger.warning("meme_tests_real_rows_skipped", skipped=skipped, shown=len(out))
    return out
