"""``services/meme_tests*.py`` — the derived record of a test (T4.13): the
Brasília day, entry/exit read from the loop's own JSON keys, PnL in US$ by
the scoreboard's formula, the closed Portuguese vocabulary of exit reasons,
``lab_context``, the REAL rows read tolerantly, and the CSV byte by byte.
No database: rows are built by hand with the keys ``paper_fill.py``/
``paper_engine.py`` write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, get_args

import pytest

from hunter_api.repositories.meme_desk_rows import BetRow, ProposalRow, RuleSetRow, TokenIdentity
from hunter_api.repositories.meme_tests import BetRecord, FeaturesAtMinute
from hunter_api.schemas.meme_desk import ExitReason
from hunter_api.schemas.meme_tests import (
    EXIT_REASON_PT,
    PROVISIONAL_EXIT_LABEL,
    REAL_OBSERVED_LABEL,
    UNKNOWN_EXIT_LABEL,
)
from hunter_api.services.meme_tests import (
    brasilia_day,
    brasilia_day_bounds,
    build_test_row,
    exit_reason_label,
)
from hunter_api.services.meme_tests_csv import CSV_COLUMNS, render_tests_csv
from hunter_api.services.meme_tests_real import real_rows_out

pytestmark = pytest.mark.unit

ENTRY_AT = datetime(2026, 9, 12, 14, 0, 5, tzinfo=UTC)  # 11:00:05 Brasília
EXIT_AT = datetime(2026, 9, 12, 14, 7, 30, tzinfo=UTC)  # 11:07:30 Brasília
MINT = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"
BET_ID = uuid.UUID("01924f6e-0000-7000-8000-000000000001")
PROPOSAL_ID = uuid.UUID("01924f6e-0000-7000-8000-000000000002")
RULE_SET_ID = uuid.UUID("01924f6e-0000-7000-8000-000000000003")


def _rule_set() -> RuleSetRow:
    return RuleSetRow(
        id=RULE_SET_ID,
        name="meme_paper_v0",
        version="1",
        kind="research_only",
        params={"size_sol": "0.2"},
        status="active",
    )


def _proposal(**overrides: Any) -> ProposalRow:
    base: dict[str, Any] = {
        "id": PROPOSAL_ID,
        "mint": MINT,
        "rule_set_id": RULE_SET_ID,
        "origin": "rules",
        "status": "filled",
        "proposed_at": ENTRY_AT - timedelta(seconds=40),
        "expires_at": ENTRY_AT + timedelta(seconds=80),
        "features_end_time": ENTRY_AT - timedelta(seconds=65),
        "quote": {},
        "reasons": ["progress_gate", "age_gate"],
        "suggested": {},
        "decision": {},
        "decided_by": "rules",
        "decided_at": ENTRY_AT - timedelta(seconds=40),
        "bet_id": BET_ID,
        "refusal": None,
    }
    base.update(overrides)
    return ProposalRow(**base)


def _entry_json() -> dict[str, Any]:
    """Exactly the keys ``paper_fill._build_entry`` writes."""
    return {
        "snapshot": {
            "observed_at": ENTRY_AT.isoformat(),
            "source": "solana_rpc",
            "mcap_sol": "31.5",
            "complete": False,
        },
        "decided_at": (ENTRY_AT - timedelta(seconds=40)).isoformat(),
        "decision_to_fill_s": 40,
        "fill_delay_snapshots": 1,
        "marginal_price_before_sol": "0.00000003",
        "marginal_price_after_sol": "0.000000031",
        "average_price_sol": "0.0000000305",
        "curve_cost_sol": "0.1965",
        "fee_sol": "0.0035",
        "fee_pct": "1.75",
        "priority_fee_sol": "0",
        "sol_spent": "0.2",
        "tokens": "6443000",
        "sol_usd_source": "coingecko",
        "leg": "single",
        "parent_bet_id": None,
    }


def _exit_json(reason: str = "target") -> dict[str, Any]:
    """Exactly the keys ``paper_engine.close_bet`` writes."""
    return {
        "reason": reason,
        "snapshot": {
            "observed_at": EXIT_AT.isoformat(),
            "source": "solana_rpc",
            "mcap_sol": "60.1",
        },
        "intent_snapshot_at": (EXIT_AT - timedelta(seconds=30)).isoformat(),
        "curve_proceeds_sol": "0.3866",
        "fee_sol": "0.0066",
        "priority_fee_sol": "0",
        "sol_received": "0.38",
        "marginal_price_after_sol": "0.000000058",
        "sol_usd_source": "coingecko",
        "trigger": "rules",
    }


def _bet(**overrides: Any) -> BetRow:
    base: dict[str, Any] = {
        "id": BET_ID,
        "proposal_id": PROPOSAL_ID,
        "rule_set_id": RULE_SET_ID,
        "mint": MINT,
        "mode": "paper",
        "status": "closed",
        "entry_at": ENTRY_AT,
        "entry": _entry_json(),
        "initial_risk_sol": Decimal("0.2"),
        "params": {"size_sol": "0.2", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900},
        "exit_at": EXIT_AT,
        "exit": _exit_json(),
        "pnl_sol": Decimal("0.18"),
        "r_multiple": Decimal("0.9"),
        "mark_sol": Decimal("0.38"),
        "mark_at": EXIT_AT,
        "high_water_x": Decimal("2.0"),
        "sol_usd_at_entry": Decimal("179"),
        "sol_usd_at_exit": Decimal("181"),
        "leg": "single",
        "parent_bet_id": None,
    }
    base.update(overrides)
    return BetRow(**base)


def _token() -> TokenIdentity:
    return TokenIdentity(
        mint=MINT,
        name="bum bum",
        symbol="BAM",
        creator="s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
        created_at=ENTRY_AT - timedelta(minutes=9),
        mayhem_enabled=None,
        mayhem_state=None,
        completed_at=None,
        migrated_at=None,
    )


def _row(bet: BetRow | None = None, proposal: ProposalRow | None = None) -> BetRecord:
    return BetRecord(
        bet=bet or _bet(),
        proposal=_proposal() if proposal is None else proposal,
        token=_token(),
        rule_set=_rule_set(),
    )


def _features() -> FeaturesAtMinute:
    return FeaturesAtMinute(
        mint=MINT,
        end_time=ENTRY_AT - timedelta(seconds=65),
        features_version="meme_features_v3",
        line_reason=None,
        support_line_sol=Decimal("28.4"),
        distance_to_support_pct=Decimal("0.11"),
        higher_lows=True,
        breakout_15m=True,
        hype_score=Decimal("0.7"),
        hype_reason="partial",
        creator_sold=False,
        creator_sold_reason=None,
        curve_progress_pct=Decimal("0.42"),
        progress_reason=None,
        age_minutes=8,
        unique_buyers=12,
        mcap_sol=Decimal("31.2"),
    )


class TestVocabulary:
    def test_every_exit_reason_has_a_portuguese_label(self) -> None:
        members = set(get_args(ExitReason))
        assert members == set(EXIT_REASON_PT), "a reason without a label broke the build before"
        for reason, label in EXIT_REASON_PT.items():
            assert label != reason and len(label) > 3

    def test_unknown_and_provisional_labels(self) -> None:
        assert exit_reason_label("something_new", provisional=False) == UNKNOWN_EXIT_LABEL
        assert exit_reason_label("target", provisional=True) == PROVISIONAL_EXIT_LABEL
        assert exit_reason_label(None, provisional=False) == "saída sem motivo registrado"


class TestBrasiliaDay:
    def test_bounds_are_utc_minus_three(self) -> None:
        start, end = brasilia_day_bounds(date(2026, 9, 12))
        assert start == datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
        assert end == datetime(2026, 9, 13, 3, 0, tzinfo=UTC)

    def test_an_instant_before_03z_belongs_to_the_previous_day(self) -> None:
        assert brasilia_day(datetime(2026, 9, 12, 2, 59, tzinfo=UTC)) == date(2026, 9, 11)
        assert brasilia_day(datetime(2026, 9, 12, 3, 0, tzinfo=UTC)) == date(2026, 9, 12)


class TestClosedRow:
    def test_entry_and_exit_read_the_loops_keys(self) -> None:
        out = build_test_row(_row(), _features())
        assert out.kind == "paper" and out.status == "closed"
        assert out.rule_set.label == "meme_paper_v0/1"
        assert out.entry.at == ENTRY_AT
        assert out.entry.price_sol_per_token == Decimal("0.00000003")
        assert out.entry.mcap_sol == Decimal("31.5")
        assert out.entry.sol_spent == Decimal("0.2")
        assert out.entry.tokens == Decimal("6443000")
        assert out.entry.fee_sol == Decimal("0.0035")
        assert out.entry.fill_delay_s == 40
        assert out.entry.source == "solana_rpc"
        assert out.exit.at == EXIT_AT and out.exit.provisional is False
        assert out.exit.price_sol_per_token == Decimal("0.000000058")
        assert out.exit.mcap_sol == Decimal("60.1")
        assert out.exit.sol_received == Decimal("0.38")
        assert out.exit.fee_sol == Decimal("0.0066")
        assert out.exit.reason == "target"
        assert out.exit.reason_label == "alvo atingido"
        assert out.exit.trigger == "rules"
        assert out.duration_s == 445

    def test_pnl_usd_is_the_scoreboards_formula(self) -> None:
        out = build_test_row(_row(), None)
        assert out.pnl_sol == Decimal("0.18")
        assert out.r_multiple == Decimal("0.9")
        assert out.pnl_usd == Decimal("0.18") * Decimal("181")
        assert out.pnl_usd_basis == "exit_quote" and out.pnl_usd_reason is None
        assert out.sol_usd_source == "coingecko"

    def test_without_an_exit_quote_the_usd_is_absent_by_name(self) -> None:
        out = build_test_row(_row(_bet(sol_usd_at_exit=None)), None)
        assert out.pnl_usd is None and out.pnl_usd_reason == "no_exit_quote"

    def test_an_unknown_reason_is_not_invented(self) -> None:
        out = build_test_row(_row(_bet(exit=_exit_json("brand_new"))), None)
        assert out.exit.reason == "brand_new"
        assert out.exit.reason_label == UNKNOWN_EXIT_LABEL

    def test_rug_without_snapshot_carries_the_pending_rule(self) -> None:
        exit_ = {
            "reason": "rug_no_snapshot",
            "pending_reason": "time_stop",
            "snapshot": None,
            "sol_received": "0",
        }
        out = build_test_row(
            _row(_bet(exit=exit_, pnl_sol=Decimal("-0.2"), r_multiple=Decimal("-1"))), None
        )
        assert out.exit.reason_label == "rug — sem fotografia"
        assert out.exit.pending_reason == "time_stop"
        assert out.exit.mcap_sol is None and out.exit.sol_received == 0


class TestOpenRow:
    def test_the_mark_is_the_provisional_exit(self) -> None:
        bet = _bet(
            status="open",
            exit_at=None,
            exit=None,
            pnl_sol=None,
            r_multiple=None,
            mark_sol=Decimal("0.25"),
            mark_at=ENTRY_AT + timedelta(minutes=3),
            sol_usd_at_exit=None,
        )
        out = build_test_row(_row(bet), None)
        assert out.status == "open"
        assert out.exit.provisional is True
        assert out.exit.at == ENTRY_AT + timedelta(minutes=3)
        assert out.exit.sol_received == Decimal("0.25")
        assert out.exit.reason is None and out.exit.reason_label == PROVISIONAL_EXIT_LABEL
        assert out.pnl_sol == Decimal("0.05")
        assert out.r_multiple == Decimal("0.25")
        assert out.pnl_usd == Decimal("0.05") * Decimal("179")
        assert out.pnl_usd_basis == "entry_quote_provisional"
        assert out.duration_s == 180

    def test_an_open_bet_without_a_mark_has_no_numbers(self) -> None:
        bet = _bet(
            status="open",
            exit_at=None,
            exit=None,
            pnl_sol=None,
            r_multiple=None,
            mark_sol=None,
            mark_at=None,
        )
        out = build_test_row(_row(bet), None)
        assert out.exit.at is None and out.pnl_sol is None and out.pnl_usd_reason == "no_pnl"
        assert out.duration_s is None


class TestLabContext:
    def test_the_minute_is_read_and_the_line_is_drawn(self) -> None:
        out = build_test_row(_row(), _features())
        lab = out.lab_context
        assert lab.reason is None and lab.features_version == "meme_features_v3"
        assert lab.line_drawn is True and lab.support_line_sol == Decimal("28.4")
        assert lab.hype_score == Decimal("0.7") and lab.hype_reason == "partial"
        assert lab.creator_sold is False and lab.higher_lows is True
        assert lab.curve_progress_pct == Decimal("0.42")
        assert lab.gate_reasons == ["progress_gate", "age_gate"]

    def test_a_manual_proposal_has_no_minute(self) -> None:
        proposal = _proposal(origin="operator", features_end_time=None, reasons=["operator_manual"])
        out = build_test_row(_row(proposal=proposal), None)
        assert out.lab_context.reason == "manual_no_minute"
        assert out.lab_context.gate_reasons == ["operator_manual"]
        assert out.origin == "operator"

    def test_a_minute_without_a_row_says_so(self) -> None:
        out = build_test_row(_row(), None)
        assert out.lab_context.reason == "no_features_row"
        assert out.lab_context.features_end_time == ENTRY_AT - timedelta(seconds=65)
        assert out.lab_context.line_drawn is None


class TestRealRows:
    def test_a_wallet_position_becomes_a_real_row(self) -> None:
        rows = real_rows_out(
            [
                {
                    "id": uuid.UUID("01924f6e-0000-7000-8000-00000000aaaa"),
                    "wallet": "6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F",
                    "mint": MINT,
                    "state": "closed",
                    "first_buy_at": ENTRY_AT,
                    "last_trade_at": EXIT_AT,
                    "sol_spent": Decimal("0.5"),
                    "sol_received": Decimal("0.7"),
                    "realized_pnl_sol": Decimal("0.2"),
                    "tokens": Decimal("0"),
                    "mark_sol": None,
                    "mark_source": "swap_api",
                }
            ]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "real_observed" and row.kind_label == REAL_OBSERVED_LABEL
        assert row.rule_set.label == "wallet:6nAh8drz"
        assert row.wallet == "6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F"
        assert row.entry.sol_spent == Decimal("0.5") and row.exit.sol_received == Decimal("0.7")
        assert row.pnl_sol == Decimal("0.2") and row.r_multiple == Decimal("0.4")
        assert row.duration_s == 445 and row.status == "closed"
        assert row.exit.provisional is False

    def test_a_row_without_identity_is_skipped_not_half_rendered(self) -> None:
        assert real_rows_out([{"mint": MINT, "sol_spent": Decimal("1")}]) == []


class TestCsv:
    def test_header_bom_separator_and_one_closed_row_byte_exact(self) -> None:
        out = build_test_row(_row(), _features())
        body = render_tests_csv([out])
        assert body.startswith(b"\xef\xbb\xbf")
        text = body[3:].decode("utf-8")
        lines = text.split("\r\n")
        assert lines[0] == ";".join(CSV_COLUMNS)
        expected = (
            f"{BET_ID};PAPEL;meme_paper_v0/1;single;bum bum;BAM;{MINT};fechada;"
            "12/09/2026 11:00:05;0,00000003;31,5;0,2;6443000;0,0035;40;"
            "12/09/2026 11:07:30;não;0,000000058;60,1;0,38;0,0066;alvo atingido;445;"
            "0,18;32,58;exit_quote;179;181;coingecko;0,9;"
            "12/09/2026 10:59:00;meme_features_v3;sim;;0,7;não;0,42;progress_gate age_gate;"
        )
        assert lines[1] == expected
        assert lines[2] == ""

    def test_truncation_is_said_in_the_last_row(self) -> None:
        body = render_tests_csv([], truncated=True)
        assert b"limite de 5000 linhas" in body
