"""``services/meme_wallets.py`` — the "Reais — carteira observada" section is
pure assembly: the label rides on the payload, every dollar figure names the
observed quote it was priced with or says ``no_sol_usd_quote``, a position
without a mark says why, and the Lab's verdict per rule set is read from the
ledger's ``lab_context`` — never made up here (T4.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_api.repositories.meme_wallets import (
    WalletPositionRow,
    WalletSummaryRow,
    WalletTradeRow,
)
from hunter_api.schemas.meme_wallets import MEME_REAL_OBSERVED_LABEL
from hunter_api.services.meme_wallets import SolUsdQuote, real_observed_out

pytestmark = pytest.mark.unit

WALLET = "6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
AT = datetime(2026, 9, 12, 16, 14, 9, tzinfo=UTC)
QUOTE = SolUsdQuote(Decimal("101.4445"), "pumpfun_rest:/sol-price", AT)
CONTEXT: dict[str, Any] = {
    "minute": "2026-09-12T16:14:00+00:00",
    "features_version": "meme_features_v3",
    "reason": None,
    "rule_sets": {
        "meme_paper_v0/1": {
            "kind": "research_only",
            "accepted": False,
            "refusals": ["creator_net_seller_unknown", "curve_volume_1m_unknown"],
        },
        "hype_probe_v0/1": {"kind": "research_only", "accepted": True, "refusals": []},
    },
    "hype_score": "0.7",
    "hype_reason": None,
    "line_reason": "flat",
    "evaluated_at": "2026-09-12T16:15:00+00:00",
}


def _position(**overrides: Any) -> WalletPositionRow:
    base: dict[str, Any] = {
        "wallet": WALLET,
        "mint": MINT,
        "status": "open",
        "tokens_held": Decimal("22628881.309131"),
        "sol_spent": Decimal("0.9900885"),
        "sol_received": Decimal(0),
        "open_cost_sol": Decimal("0.9900885"),
        "avg_cost_sol_per_token": Decimal("0.000000043753"),
        "realized_pnl_sol": Decimal(0),
        "unrealized_pnl_sol": Decimal("0.1"),
        "unmatched_sell_tokens": Decimal(0),
        "buys": 1,
        "sells": 0,
        "first_buy_at": AT,
        "last_trade_at": AT,
        "mark_sol": Decimal("1.0900885"),
        "mark_at": AT,
        "mark_source": "curve_snapshot",
        "mark_reason": None,
        "r_multiple": Decimal("0.101001"),
        "updated_at": AT,
        "name": "Coin",
        "symbol": "COIN",
        "lab_context": CONTEXT,
        "hype_score": Decimal("0.7"),
        "line_reason": "flat",
    }
    base.update(overrides)
    return WalletPositionRow(**base)


def _trade(**overrides: Any) -> WalletTradeRow:
    base: dict[str, Any] = {
        "wallet": WALLET,
        "signature": "SIG",
        "event_index": 0,
        "slot": 446369982,
        "block_time": AT,
        "received_at": AT,
        "mint": MINT,
        "side": "buy",
        "venue": "curve",
        "sol_lamports": 977_777_777,
        "fee_lamports": 12_310_723,
        "token_amount": Decimal("22628881.309131"),
        "decode": "trade_event",
        "reason": None,
        "lab_context": CONTEXT,
        "hype_score": Decimal("0.7"),
        "line_reason": "flat",
    }
    base.update(overrides)
    return WalletTradeRow(**base)


SUMMARY = WalletSummaryRow(
    wallet=WALLET,
    trades=2,
    fills=1,
    unknown=1,
    first_seen_at=AT,
    last_trade_at=AT,
    realized_total_sol=Decimal("0.25"),
    realized_today_sol=Decimal("0.25"),
    open_positions=1,
    closed_positions=1,
    open_cost_sol=Decimal("0.9900885"),
    open_marks_sol=Decimal("1.0900885"),
    unmarked_open=0,
)


def test_the_section_is_labelled_real_and_priced_with_the_named_quote() -> None:
    out = real_observed_out([SUMMARY], [_position()], [_trade()], quote=QUOTE, watched=1)
    assert (
        out.label
        == MEME_REAL_OBSERVED_LABEL
        == ("REAL — observado na cadeia, não executado por este sistema")
    )
    assert out.watched == 1 and out.watched_reason is None and out.reason is None
    assert out.sol_usd is not None and out.sol_usd.source == "pumpfun_rest:/sol-price"
    wallet = out.wallets[0]
    assert wallet.wallet_short == "6nAh8drz"
    assert wallet.realized_total_usd.value == Decimal("0.25") * Decimal("101.4445")
    position = out.positions[0]
    assert position.unrealized_pnl_usd.value == Decimal("0.1") * Decimal("101.4445")
    assert position.r_multiple.value == Decimal("0.101001") and position.r_multiple.reason is None
    trade = out.trades[0]
    assert trade.sol_total.value == Decimal("0.990088500")  # 977 777 777 + 12 310 723 lamports


def test_without_a_quote_every_dollar_is_none_with_the_reason_never_zero() -> None:
    out = real_observed_out([SUMMARY], [_position()], [], quote=None, watched=None)
    assert out.sol_usd is None and out.sol_usd_reason == "no_sol_usd_quote"
    assert out.watched is None and out.watched_reason is None
    assert out.wallets[0].realized_total_usd.value is None
    assert out.wallets[0].realized_total_usd.reason == "no_sol_usd_quote"
    assert out.positions[0].realized_pnl_usd.reason == "no_sol_usd_quote"
    assert out.positions[0].unrealized_pnl_usd.reason == "no_sol_usd_quote"


def test_a_position_without_a_mark_names_why_and_r_is_undefined() -> None:
    row = _position(
        unrealized_pnl_sol=None,
        mark_sol=None,
        mark_at=None,
        mark_source=None,
        mark_reason="no_snapshot_no_tape",
        r_multiple=None,
    )
    (position,) = real_observed_out([SUMMARY], [row], [], quote=QUOTE, watched=1).positions
    assert position.unrealized_pnl_sol.value is None
    assert position.unrealized_pnl_sol.reason == "no_snapshot_no_tape"
    assert position.unrealized_pnl_usd.reason == "no_snapshot_no_tape"
    assert position.r_multiple.reason == "no_snapshot_no_tape"
    closed = _position(
        status="closed",
        tokens_held=Decimal(0),
        unrealized_pnl_sol=None,
        mark_sol=None,
        mark_at=None,
        mark_source=None,
        mark_reason="closed",
        r_multiple=Decimal("-1"),
    )
    (out,) = real_observed_out([SUMMARY], [closed], [], quote=QUOTE, watched=1).positions
    assert out.status == "closed" and out.r_multiple.value == Decimal("-1")


def test_the_labs_verdict_is_read_from_the_ledger_not_invented() -> None:
    (position,) = real_observed_out([SUMMARY], [_position()], [], quote=QUOTE, watched=1).positions
    context = position.lab_context
    assert context is not None and context.reason is None
    assert context.minute == datetime(2026, 9, 12, 16, 14, tzinfo=UTC)
    assert context.rule_sets["meme_paper_v0/1"].accepted is False
    assert context.rule_sets["meme_paper_v0/1"].refusals == [
        "creator_net_seller_unknown",
        "curve_volume_1m_unknown",
    ]
    assert context.rule_sets["hype_probe_v0/1"].accepted is True
    assert context.hype_score == Decimal("0.7") and context.line_reason == "flat"
    unseen = _position(
        lab_context={
            "reason": "no_features_row",
            "rule_sets": {"x/1": {"kind": "operator", "accepted": None, "refusals": []}},
        }
    )
    (row,) = real_observed_out([SUMMARY], [unseen], [], quote=QUOTE, watched=1).positions
    assert row.lab_context is not None and row.lab_context.reason == "no_features_row"
    assert row.lab_context.rule_sets["x/1"].accepted is None
    (bare,) = real_observed_out(
        [SUMMARY], [_position(lab_context=None)], [], quote=QUOTE, watched=1
    ).positions
    assert bare.lab_context is None


def test_an_unknown_trade_has_no_total_and_an_empty_ledger_says_so() -> None:
    unknown = _trade(
        side="unknown",
        venue=None,
        sol_lamports=None,
        fee_lamports=None,
        token_amount=None,
        decode="none",
        reason="no_known_venue",
        lab_context=None,
    )
    sell = _trade(side="sell", sol_lamports=724_716_993, fee_lamports=9_158_963, lab_context=None)
    out = real_observed_out([SUMMARY], [], [unknown, sell], quote=QUOTE, watched=1)
    assert out.trades[0].sol_total.value is None and out.trades[0].sol_total.reason == "not_a_fill"
    assert out.trades[0].reason == "no_known_venue"
    assert out.trades[1].sol_total.value == Decimal("0.715558030")
    empty = real_observed_out([], [], [], quote=None, watched=0)
    assert empty.reason == "no_wallet_observed" and empty.wallets == [] and empty.watched == 0
