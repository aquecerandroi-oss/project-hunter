"""Repository rows → the test record (T4.13): one ``TestRowOut`` per paper
bet with every derived number computed here in ``Decimal``, the day's totals,
and the Brasília day bounds every read is scoped by.

**JSONB is read tolerantly** — the same ``decimal_or_none`` discipline as
``services/meme_desk_out.py``: a key the loop did not write is ``None`` in
the payload, never ``0``. The keys read are the ones ``paper_fill.py``/
``paper_engine.py`` actually write (``entry.snapshot``, ``decision_to_fill_s``,
``marginal_price_before_sol``, ``exit.marginal_price_after_sol``, …).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from hunter_api.repositories.meme_desk_rows import BetRow
from hunter_api.repositories.meme_tests import (
    PREFERRED_FEATURES_VERSION,
    BetRecord,
    DayTotalsRow,
    FeaturesAtMinute,
    IndeterminateTotals,
)
from hunter_api.schemas.meme_tests import (
    EXIT_REASON_PT,
    NO_EXIT_LABEL,
    OUTCOME_QUALITY_PT,
    PROVISIONAL_EXIT_LABEL,
    UNKNOWN_EXIT_LABEL,
    UNKNOWN_QUALITY_LABEL,
    LabContextOut,
    LabContextReason,
    PnlUsdBasis,
    PnlUsdReason,
    TestEntryOut,
    TestExitOut,
    TestRowOut,
    TestRuleSetOut,
    TestsSourcesOut,
    TestsTotalsOut,
    WalletsSource,
)
from hunter_api.services.meme_desk_out import decimal_or_none

__all__ = [
    "BRASILIA",
    "PAPER_KIND_LABEL",
    "brasilia_day",
    "brasilia_day_bounds",
    "build_lab_context",
    "build_sources",
    "build_test_row",
    "build_totals",
    "exit_reason_label",
    "int_or_none",
    "outcome_quality_label",
    "str_or_none",
]

BRASILIA = ZoneInfo("America/Sao_Paulo")
PAPER_KIND_LABEL = "PAPEL — aposta simulada do laço"


def brasilia_day(now: datetime) -> date:
    return now.astimezone(BRASILIA).date()


def brasilia_day_bounds(day: date) -> tuple[datetime, datetime]:
    """``[00:00, 24:00)`` of the Brasília day, as UTC instants."""
    start = datetime.combine(day, time(0), tzinfo=BRASILIA)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def exit_reason_label(reason: str | None, *, provisional: bool) -> str:
    if provisional:
        return PROVISIONAL_EXIT_LABEL
    if reason is None:
        return NO_EXIT_LABEL
    return EXIT_REASON_PT.get(reason, UNKNOWN_EXIT_LABEL)


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(Decimal(str(value)))
        except (ArithmeticError, ValueError):
            return None
    return None


def str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}  # type: ignore[return-value]


def _entry_out(bet: BetRow) -> TestEntryOut:
    entry = bet.entry
    snapshot = _dict(entry.get("snapshot"))
    return TestEntryOut(
        at=bet.entry_at,
        price_sol_per_token=decimal_or_none(entry.get("marginal_price_before_sol")),
        average_price_sol=decimal_or_none(entry.get("average_price_sol")),
        mcap_sol=decimal_or_none(snapshot.get("mcap_sol")),
        sol_spent=decimal_or_none(entry.get("sol_spent")),
        tokens=decimal_or_none(entry.get("tokens")),
        fee_sol=decimal_or_none(entry.get("fee_sol")),
        fee_pct=decimal_or_none(entry.get("fee_pct")),
        fill_delay_s=int_or_none(entry.get("decision_to_fill_s")),
        fill_delay_snapshots=int_or_none(entry.get("fill_delay_snapshots")),
        source=str_or_none(snapshot.get("source")),
    )


def _exit_out(bet: BetRow) -> TestExitOut:
    if bet.status == "closed" and bet.exit is not None:
        data = bet.exit
        snapshot = _dict(data.get("snapshot"))
        reason = str_or_none(data.get("reason"))
        return TestExitOut(
            at=bet.exit_at,
            provisional=False,
            price_sol_per_token=decimal_or_none(data.get("marginal_price_after_sol")),
            mcap_sol=decimal_or_none(snapshot.get("mcap_sol")),
            sol_received=decimal_or_none(data.get("sol_received")),
            fee_sol=decimal_or_none(data.get("fee_sol")),
            reason=reason,
            reason_label=exit_reason_label(reason, provisional=False),
            trigger=str_or_none(data.get("trigger")),
            pending_reason=str_or_none(data.get("pending_reason")),
        )
    return TestExitOut(
        at=bet.mark_at,
        provisional=True,
        price_sol_per_token=None,
        mcap_sol=None,
        sol_received=bet.mark_sol,
        fee_sol=None,
        reason=None,
        reason_label=exit_reason_label(None, provisional=True),
        trigger=None,
        pending_reason=None,
    )


def _pnl(bet: BetRow, exit_: TestExitOut) -> tuple[Decimal | None, Decimal | None]:
    """``(pnl_sol, r_multiple)`` — the loop's own numbers once closed; while
    open, the mark against what was spent (the desk's ``unrealized_*``)."""
    if bet.status == "closed":
        return bet.pnl_sol, bet.r_multiple
    spent = decimal_or_none(bet.entry.get("sol_spent"))
    if exit_.sol_received is None or spent is None:
        return None, None
    pnl = exit_.sol_received - spent
    r = pnl / bet.initial_risk_sol if bet.initial_risk_sol > 0 else None
    return pnl, r


def _pnl_usd(
    bet: BetRow, pnl_sol: Decimal | None
) -> tuple[Decimal | None, PnlUsdBasis | None, PnlUsdReason | None]:
    """``(pnl_usd, basis, reason)``: closed = ``pnl_sol × sol_usd_at_exit``
    (``meme_lab_scoreboard_v1``'s formula); open = provisional at the entry
    quote. Never a rate this API did not observe on the bet."""
    if pnl_sol is None:
        return None, None, "no_pnl"
    if bet.status == "closed":
        if bet.sol_usd_at_exit is None:
            return None, None, "no_exit_quote"
        return pnl_sol * bet.sol_usd_at_exit, "exit_quote", None
    if bet.sol_usd_at_entry is None:
        return None, None, "no_entry_quote"
    return pnl_sol * bet.sol_usd_at_entry, "entry_quote_provisional", None


def build_lab_context(row: BetRecord, features: FeaturesAtMinute | None) -> LabContextOut:
    proposal = row.proposal
    reasons = list(proposal.reasons or []) if proposal is not None else []
    end_time = proposal.features_end_time if proposal is not None else None
    if end_time is None:
        return _empty_context(None, reasons, "manual_no_minute")
    if features is None:
        return _empty_context(end_time, reasons, "no_features_row")
    return LabContextOut(
        features_end_time=features.end_time,
        features_version=features.features_version,
        reason=None,
        gate_reasons=reasons,
        line_drawn=features.support_line_sol is not None,
        line_reason=features.line_reason,
        support_line_sol=features.support_line_sol,
        distance_to_support_pct=features.distance_to_support_pct,
        higher_lows=features.higher_lows,
        breakout_15m=features.breakout_15m,
        hype_score=features.hype_score,
        hype_reason=features.hype_reason,
        creator_sold=features.creator_sold,
        creator_sold_reason=features.creator_sold_reason,
        curve_progress_pct=features.curve_progress_pct,
        progress_reason=features.progress_reason,
        age_minutes=features.age_minutes,
        unique_buyers=features.unique_buyers,
        mcap_sol=features.mcap_sol,
    )


def _empty_context(
    end_time: datetime | None, reasons: list[Any], reason: LabContextReason
) -> LabContextOut:
    return LabContextOut(
        features_end_time=end_time,
        features_version=None,
        reason=reason,
        gate_reasons=reasons,
        line_drawn=None,
        line_reason=None,
        support_line_sol=None,
        distance_to_support_pct=None,
        higher_lows=None,
        breakout_15m=None,
        hype_score=None,
        hype_reason=None,
        creator_sold=None,
        creator_sold_reason=None,
        curve_progress_pct=None,
        progress_reason=None,
        age_minutes=None,
        unique_buyers=None,
        mcap_sol=None,
    )


def _rule_set_out(row: BetRecord) -> TestRuleSetOut:
    rs = row.rule_set
    if rs is None:
        return TestRuleSetOut(name=None, version=None, kind=None, label="conjunto desconhecido")
    return TestRuleSetOut(
        name=rs.name, version=rs.version, kind=rs.kind, label=f"{rs.name}/{rs.version}"
    )


def build_test_row(row: BetRecord, features: FeaturesAtMinute | None) -> TestRowOut:
    bet = row.bet
    entry = _entry_out(bet)
    exit_ = _exit_out(bet)
    pnl_sol, r_multiple = _pnl(bet, exit_)
    pnl_usd, basis, usd_reason = _pnl_usd(bet, pnl_sol)
    exit_source = str_or_none((bet.exit or {}).get("sol_usd_source"))
    duration = int((exit_.at - bet.entry_at).total_seconds()) if exit_.at is not None else None
    return TestRowOut(
        id=str(bet.id),
        kind="paper",
        kind_label=PAPER_KIND_LABEL,
        bet_id=bet.id,
        proposal_id=bet.proposal_id,
        mint=bet.mint,
        token_name=row.token.name if row.token is not None else None,
        token_symbol=row.token.symbol if row.token is not None else None,
        status=bet.status,
        rule_set=_rule_set_out(row),
        leg=bet.leg,
        parent_bet_id=bet.parent_bet_id,
        origin=row.proposal.origin if row.proposal is not None else None,
        decided_by=row.proposal.decided_by if row.proposal is not None else None,
        entry=entry,
        exit=exit_,
        duration_s=duration,
        pnl_sol=pnl_sol,
        pnl_usd=pnl_usd,
        pnl_usd_basis=basis,
        pnl_usd_reason=usd_reason,
        r_multiple=r_multiple,
        sol_usd_at_entry=bet.sol_usd_at_entry,
        sol_usd_at_exit=bet.sol_usd_at_exit,
        sol_usd_source=exit_source or str_or_none(bet.entry.get("sol_usd_source")),
        lab_context=build_lab_context(row, features),
        wallet=None,
        mark_source=None,
        outcome_quality=bet.outcome_quality,
        outcome_quality_label=outcome_quality_label(bet.outcome_quality),
        outcome_quality_reason=bet.outcome_quality_reason,
    )


def outcome_quality_label(quality: str | None) -> str | None:
    """``None`` for a row without the column; the brief's words otherwise."""
    if quality is None:
        return None
    return OUTCOME_QUALITY_PT.get(quality, UNKNOWN_QUALITY_LABEL)


def build_totals(
    totals: DayTotalsRow, *, real_rows: int, indeterminate: IndeterminateTotals | None = None
) -> TestsTotalsOut:
    """The day's totals with the indeterminate closes **taken out** of every
    sum of wins/losses/PnL/R and counted apart (T4.16); ``None`` (a database
    below ``0030``) leaves the sums as the repository summed them."""
    out = indeterminate
    if out is None:
        return TestsTotalsOut(
            bets=totals.bets,
            closed=totals.closed,
            open=totals.open,
            wins=totals.wins,
            losses=totals.losses,
            pnl_sol=totals.pnl_sol,
            provisional_pnl_sol=totals.provisional_pnl_sol,
            pnl_usd=totals.pnl_usd,
            unpriced_usd=totals.unpriced_usd,
            r_sum=totals.r_sum,
            real_rows=real_rows,
        )
    pnl_usd = totals.pnl_usd
    if pnl_usd is not None and out.pnl_usd is not None:
        pnl_usd = pnl_usd - out.pnl_usd
    return TestsTotalsOut(
        bets=totals.bets,
        closed=totals.closed,
        open=totals.open,
        wins=totals.wins - out.wins,
        losses=totals.losses - out.losses,
        indeterminate=out.bets,
        pnl_sol=totals.pnl_sol - out.pnl_sol,
        provisional_pnl_sol=totals.provisional_pnl_sol,
        pnl_usd=pnl_usd,
        unpriced_usd=totals.unpriced_usd - out.unpriced_usd,
        r_sum=totals.r_sum - out.r_sum,
        real_rows=real_rows,
    )


def build_sources(wallets: WalletsSource) -> TestsSourcesOut:
    return TestsSourcesOut(wallets=wallets, features_version=PREFERRED_FEATURES_VERSION)
