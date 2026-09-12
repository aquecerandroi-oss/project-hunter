"""Assembles the "Reais — carteira observada" section (T4.12) from the
repository's rows and one observed SOL/USD quote — pure arithmetic, no number
this module made up.

The dollar figures are ``pnl_sol × price_usd`` with the quote the caller
already had (the Lab's heartbeat/last-bet quote, or the desk's), and they say
which quote; without one every dollar field is ``None`` with
``no_sol_usd_quote``. Nothing here is a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any, cast

from hunter_api.schemas.meme_wallets import (
    LabVerdictOut,
    ObservedSolUsdOut,
    ObservedValueOut,
    RealObservedOut,
    WalletLabContextOut,
    WalletObservedOut,
    WalletPositionOut,
    WalletTradeOut,
)
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hunter_api.repositories.meme_wallets import (
        MemeWalletsRepository,
        WalletPositionRow,
        WalletSummaryRow,
        WalletTradeRow,
    )

__all__ = ["SolUsdQuote", "build_real_observed", "real_observed_out", "short_wallet"]

LAMPORTS_PER_SOL = Decimal(10**9)
NO_QUOTE = "no_sol_usd_quote"
NO_WALLET = "no_wallet_observed"


@dataclass(frozen=True, slots=True)
class SolUsdQuote:
    price_usd: Decimal
    source: str
    observed_at: datetime


def short_wallet(wallet: str) -> str:
    return wallet[:8]


def _usd(
    value: Decimal | None, quote: SolUsdQuote | None, *, reason: str | None
) -> ObservedValueOut:
    if value is None:
        return ObservedValueOut(value=None, reason=reason)
    if quote is None:
        return ObservedValueOut(value=None, reason=NO_QUOTE)
    with localcontext(CONTEXT):
        return ObservedValueOut(value=value * quote.price_usd)


def _dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _lab_context(raw: Mapping[str, Any] | None) -> WalletLabContextOut | None:
    if raw is None:
        return None
    verdicts: dict[str, LabVerdictOut] = {}
    for label, verdict_any in _dict(raw.get("rule_sets")).items():
        verdict = _dict(verdict_any)
        refusals_any: Any = verdict.get("refusals")
        refusals: list[Any] = (
            cast(list[Any], refusals_any) if isinstance(refusals_any, list) else []
        )
        accepted_any: Any = verdict.get("accepted")
        verdicts[label] = LabVerdictOut(
            kind=str(verdict.get("kind", "")),
            accepted=accepted_any if isinstance(accepted_any, bool) else None,
            refusals=[str(r) for r in refusals],
        )
    minute, evaluated = _text(raw.get("minute")), _text(raw.get("evaluated_at"))
    hype: Any = raw.get("hype_score")
    return WalletLabContextOut(
        minute=datetime.fromisoformat(minute) if minute else None,
        features_version=_text(raw.get("features_version")),
        reason=_text(raw.get("reason")),
        rule_sets=verdicts,
        hype_score=None if hype is None else Decimal(str(hype)),
        hype_reason=_text(raw.get("hype_reason")),
        line_reason=_text(raw.get("line_reason")),
        evaluated_at=datetime.fromisoformat(evaluated) if evaluated else None,
    )


def _position_out(row: WalletPositionRow, quote: SolUsdQuote | None) -> WalletPositionOut:
    unrealized_reason = (
        None if row.unrealized_pnl_sol is not None else (row.mark_reason or "no_mark")
    )
    r_reason = (
        None
        if row.r_multiple is not None
        else ("no_sol_spent" if row.sol_spent <= 0 else (row.mark_reason or "no_mark"))
    )
    return WalletPositionOut(
        wallet=row.wallet,
        wallet_short=short_wallet(row.wallet),
        mint=row.mint,
        name=row.name,
        symbol=row.symbol,
        status=row.status,  # type: ignore[arg-type]
        tokens_held=row.tokens_held,
        sol_spent=row.sol_spent,
        sol_received=row.sol_received,
        open_cost_sol=row.open_cost_sol,
        avg_cost_sol_per_token=row.avg_cost_sol_per_token,
        realized_pnl_sol=row.realized_pnl_sol,
        realized_pnl_usd=_usd(row.realized_pnl_sol, quote, reason=None),
        unrealized_pnl_sol=ObservedValueOut(value=row.unrealized_pnl_sol, reason=unrealized_reason),
        unrealized_pnl_usd=_usd(row.unrealized_pnl_sol, quote, reason=unrealized_reason),
        unmatched_sell_tokens=row.unmatched_sell_tokens,
        buys=row.buys,
        sells=row.sells,
        first_buy_at=row.first_buy_at,
        last_trade_at=row.last_trade_at,
        mark_sol=row.mark_sol,
        mark_at=row.mark_at,
        mark_source=row.mark_source,  # type: ignore[arg-type]
        mark_reason=row.mark_reason,
        r_multiple=ObservedValueOut(value=row.r_multiple, reason=r_reason),
        lab_context=_lab_context(row.lab_context),
        hype_score=row.hype_score,
        line_reason=row.line_reason,
    )


def _trade_out(row: WalletTradeRow) -> WalletTradeOut:
    total: ObservedValueOut
    if row.side == "unknown" or row.sol_lamports is None or row.fee_lamports is None:
        total = ObservedValueOut(value=None, reason="not_a_fill")
    else:
        lamports = (
            row.sol_lamports + row.fee_lamports
            if row.side == "buy"
            else row.sol_lamports - row.fee_lamports
        )
        with localcontext(CONTEXT):
            total = ObservedValueOut(value=Decimal(lamports) / LAMPORTS_PER_SOL)
    return WalletTradeOut(
        wallet=row.wallet,
        wallet_short=short_wallet(row.wallet),
        signature=row.signature,
        event_index=row.event_index,
        slot=row.slot,
        block_time=row.block_time,
        received_at=row.received_at,
        mint=row.mint,
        side=row.side,  # type: ignore[arg-type]
        venue=row.venue,  # type: ignore[arg-type]
        sol_lamports=row.sol_lamports,
        fee_lamports=row.fee_lamports,
        sol_total=total,
        token_amount=row.token_amount,
        decode=row.decode,  # type: ignore[arg-type]
        reason=row.reason,
        lab_context=_lab_context(row.lab_context),
        hype_score=row.hype_score,
        line_reason=row.line_reason,
    )


def _wallet_out(row: WalletSummaryRow, quote: SolUsdQuote | None) -> WalletObservedOut:
    return WalletObservedOut(
        wallet=row.wallet,
        wallet_short=short_wallet(row.wallet),
        trades=row.trades,
        fills=row.fills,
        unknown=row.unknown,
        first_seen_at=row.first_seen_at,
        last_trade_at=row.last_trade_at,
        realized_total_sol=row.realized_total_sol,
        realized_total_usd=_usd(row.realized_total_sol, quote, reason=None),
        realized_today_sol=row.realized_today_sol,
        open_positions=row.open_positions,
        closed_positions=row.closed_positions,
        open_cost_sol=row.open_cost_sol,
        open_marks_sol=row.open_marks_sol,
        unmarked_open=row.unmarked_open,
    )


def real_observed_out(
    summaries: Sequence[WalletSummaryRow],
    positions: Sequence[WalletPositionRow],
    trades: Sequence[WalletTradeRow],
    *,
    quote: SolUsdQuote | None,
    watched: int | None,
    watched_reason: str | None = None,
) -> RealObservedOut:
    return RealObservedOut(
        watched=watched,
        watched_reason=watched_reason if watched is None else None,
        wallets=[_wallet_out(s, quote) for s in summaries],
        positions=[_position_out(p, quote) for p in positions],
        trades=[_trade_out(t) for t in trades],
        sol_usd=None
        if quote is None
        else ObservedSolUsdOut(
            price_usd=quote.price_usd, source=quote.source, observed_at=quote.observed_at
        ),
        sol_usd_reason=NO_QUOTE if quote is None else None,
        reason=None if summaries else NO_WALLET,
    )


async def build_real_observed(
    repo: MemeWalletsRepository,
    *,
    day_start: datetime,
    day_end: datetime,
    quote: SolUsdQuote | None,
    watched: int | None,
    watched_reason: str | None = None,
    positions_limit: int = 200,
    trades_limit: int = 100,
) -> RealObservedOut:
    return real_observed_out(
        await repo.summaries(day_start=day_start, day_end=day_end),
        await repo.positions(limit=positions_limit),
        await repo.trades(limit=trades_limit),
        quote=quote,
        watched=watched,
        watched_reason=watched_reason,
    )
